"""[3] 抽取主文（trafilatura）。

職責：從 [2] 抓回的 raw HTML 抽出主文，輸出含 title/text/source/hostname/http_status
的 JSON；navigation_only 頁（導覽索引頁）跳過不輸出。
另產出人類可讀的 .md 衍生物（data/processed/extracted_readable/），供驗收閱讀；
真值仍以 JSON 為準，.md 寫入失敗只記 warning，不影響 exit code。

設計原則：
- 模組化：抽出、判定、寫檔、報告各自獨立，main() 只做編排。
- 低語法糖：顯式迴圈與條件，不使用裝飾器或 walrus。
- navigation_only 判定（AGENTS.md §6 [3]）：
  * URL path 以 '-index' 結尾，或
  * 抽出文字長度 < 閾值 且 連結密度 > 閾值
  預期 3 頁 *-index 命中（ae2/example/items 三個章節索引頁）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import trafilatura
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "processed" / "extracted"
REPORTS_DIR = PROJECT_ROOT / "reports"

MANIFEST_PATH = RAW_DIR / "_manifest.json"
PARSE_REPORT_PATH = EXTRACTED_DIR / "_parse_report.json"
EXTRACTION_REPORT_PATH = REPORTS_DIR / "extraction_report.md"

# 人類可讀衍生物：與 extracted JSON 同批生成，路徑鏡像、僅副檔名不同
# 真值仍是 JSON；.md 僅供驗收閱讀，寫入失敗只記 warning（不影響 exit code）
READABLE_DIR = PROJECT_ROOT / "data" / "processed" / "extracted_readable"
READABLE_INDEX_PATH = READABLE_DIR / "_index.md"

# navigation_only 判定閾值（依第一波資料校準）
# - text_len 上限：導覽索引頁的 trafilatura 抽出通常 < 500 字元（純標題拼接）
# - density 下限：實測 <article> 內連結密度——導覽索引頁 0.93/0.97，
#   短內容頁（物品/配方頁）最高 0.44，正常內容頁 0.0~0.05。
#   0.5 可明確切開兩群（0.44 < 0.5 < 0.93）。
NAV_MIN_TEXT_LENGTH = 200     # 抽出文字少於此字元數 → 疑似導覽頁
NAV_MAX_LINK_DENSITY = 0.5    # <article> 內連結密度高於此 → 疑似導覽頁

# extracted JSON 欄位：只保留 trafilatura 原始輸出 + http_status（AGENTS.md §7）
EXTRACTED_FIELDS = ("title", "text", "source", "hostname")


# ---------------------------------------------------------------------------
# [3.1] 讀取輸入
# ---------------------------------------------------------------------------
def load_manifest(path: Path) -> dict:
    """讀 [2] 的 _manifest.json；缺檔代表 [2] 未執行，直接報錯。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}：請先執行 [2] src/fetch_pages.py")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def collected_html_files(manifest: dict) -> list:
    """從 manifest 收集成功抓取的頁面（local_path 非 None），按檔案路徑排序。

    只處理 [2] 記錄的成功頁；失敗頁（local_path=None）已在 [2] 報告，此處不重複處理。
    """
    entries = manifest.get("urls", [])
    kept = [e for e in entries if e.get("local_path")]
    kept.sort(key=lambda e: e["local_path"])
    return kept


# ---------------------------------------------------------------------------
# [3.2] trafilatura 抽取
# ---------------------------------------------------------------------------
def extract_page(html: str) -> dict:
    """呼叫 trafilatura 抽取主文，回傳 dict 或 None（無法抽取）。

    參數固定（AGENTS.md §8）：output_format=json, with_metadata=True, include_tables=True
    """
    raw = trafilatura.extract(
        html,
        output_format="json",
        with_metadata=True,
        include_tables=True,
    )
    if raw is None:
        return None
    return json.loads(raw)


# ---------------------------------------------------------------------------
# [3.3] navigation_only 判定
# ---------------------------------------------------------------------------
def is_index_page(url: str) -> bool:
    """規則一：URL path 以 '-index' 結尾（如 .../ae2-mechanics/ae2-mechanics-index）。"""
    path = urlparse(url).path
    return path.endswith("-index")


def link_density(html: str) -> float:
    """規則二前置：計算 <article> 內容區中，<a> 文字佔該區可見文字的比例。

    為何只算 <article>：本站台每頁都帶情境式展開的側邊欄（最多 91 個連結），
    若對整頁 HTML 計算，短內容頁（如物品/配方頁）會被側邊欄連結拖高密度而
    被誤判為導覽頁。<article> 才是真正的主文區，側邊欄與頁首導覽都在它之外。

    BeautifulSoup 在此只用於 leaf page 內容的連結密度計算，不用於導覽發現
    （見 ADR-001 與 AGENTS.md §8）。
    """
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article")
    if article is None:
        # 無 article 區域：無法判定內容區，保守視為非導覽頁（不命中）
        return 0.0

    total_text = article.get_text(separator="", strip=True)
    if not total_text:
        return 0.0

    link_text = ""
    for anchor in article.find_all("a"):
        link_text += anchor.get_text(separator="", strip=True)

    return len(link_text) / len(total_text)


def is_navigation_only(url: str, extracted: dict, html: str) -> tuple:
    """綜合判定是否為 navigation_only 頁。回傳 (是否命中, 原因字串)。"""
    if is_index_page(url):
        return True, "url_ends_with_index"

    text = extracted.get("text") or ""
    density = link_density(html)
    if len(text) < NAV_MIN_TEXT_LENGTH and density > NAV_MAX_LINK_DENSITY:
        return True, "short_text_high_link_density"

    return False, ""


# ---------------------------------------------------------------------------
# [3.4] 輸出
# ---------------------------------------------------------------------------
def extracted_output_path(local_path: str) -> Path:
    """把 data/raw/.../*.html 映射到 data/processed/extracted/.../*.json。

    路徑結構沿用 [2] 寫入的 <version>/<mod_slug>/<chapter>/<page_slug> 分層；
    chapter/page_slug 不重新計算，完全由 [2] 的路徑決定（權威來源分離）。
    """
    rel = local_path[len("data/raw/"):]               # 去掉 data/raw/ 前綴
    rel_json = rel[:-len(".html")] + ".json"          # .html -> .json
    return EXTRACTED_DIR / rel_json


def build_extracted_record(extracted: dict, http_status) -> dict:
    """組 extracted JSON：只放 trafilatura 原始欄位 + http_status。

    不加 page_slug/chapter（[5] 從路徑讀）；hostname 保留 trafilatura 原值不修正。
    """
    record = {field: extracted.get(field) for field in EXTRACTED_FIELDS}
    record["http_status"] = http_status
    return record


def write_json(path: Path, record: dict) -> None:
    """寫單一 extracted JSON（UTF-8，確保中文內容正確）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def _yaml_scalar(value) -> str:
    """把值輸出為安全的 YAML scalar。

    字串含特殊字元（冒號、引號、逗號、# 等，如 'Import, Export, and Storage'、
    'An Example "Main Network"'）時以雙引號包裹並跳脫內部引號；整數原樣輸出。
    採用顯式判斷而不引入 pyyaml 依賴（AGENTS.md §8：新增依賴須先詢問）。
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return '""'
    text = str(value)
    needs_quote = any(ch in text for ch in [':', '#', '"', "'", ",", "{", "}", "[", "]", "&", "*", "!", "|", ">", "%", "@", "`"])
    needs_quote = needs_quote or text != text.strip() or text == ""
    if not needs_quote:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def readable_output_path(local_path: str) -> Path:
    """把 data/raw/.../*.html 映射到 data/processed/extracted_readable/.../*.md。

    與 extracted JSON 完全同構（路徑鏡像，僅頂層目錄與副檔名不同）。
    """
    rel = local_path[len("data/raw/"):]               # 去掉 data/raw/ 前綴
    rel_md = rel[:-len(".html")] + ".md"              # .html -> .md
    return READABLE_DIR / rel_md


def build_readable_md(record: dict) -> str:
    """組人類可讀 .md：YAML front matter + 空行 + # {title} + 空行 + text 原文。

    text 直接寫，不加工、不清理、不做換行處理（真值以 JSON 為準）。
    """
    title = record.get("title") or ""
    text = record.get("text") or ""

    lines = []
    lines.append("---")
    lines.append(f"title: {_yaml_scalar(record.get('title'))}")
    lines.append(f"source: {_yaml_scalar(record.get('source'))}")
    lines.append(f"hostname: {_yaml_scalar(record.get('hostname'))}")
    lines.append(f"http_status: {_yaml_scalar(record.get('http_status'))}")
    lines.append(f"text_length: {_yaml_scalar(len(text))}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(text)
    return "\n".join(lines) + "\n"


def write_readable_md(path: Path, record: dict) -> None:
    """寫單一 readable .md（UTF-8）。路徑可能含中文，由 OS 處理。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_readable_md(record), encoding="utf-8")


def write_readable_index(path: Path, manifest: dict, rows: list) -> None:
    """寫 data/processed/extracted_readable/_index.md：列出所有已輸出頁面。

    rows 每項含 title / chapter / page_slug / text_length / source。
    chapter 與 page_slug 取自 manifest（[2] 解析），不從 .md 路徑重推。
    """
    lines = []
    lines.append(f"# [3] 抽取結果索引 — {manifest['version']} / {manifest['mod']}")
    lines.append("")
    lines.append(f"- 真值：`data/processed/extracted/<version>/<mod_slug>/<chapter>/*.json`")
    lines.append(f"- 本表與 `.md` 副檔為人類驗收用，**內容以 JSON 為準**")
    lines.append(f"- 已輸出頁數：{len(rows)}（navigation_only 頁不列入）")
    lines.append("")
    lines.append("| title | chapter | page_slug | text_length | source |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in rows:
        title = (r.get("title") or "").replace("|", "\\|")
        lines.append(
            f"| {title} | {r.get('chapter')} | {r.get('page_slug')} "
            f"| {r.get('text_length')} | {r.get('source')} |"
        )
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_parse_report(path: Path, parsed_count: int, skipped: list,
                       errors: list, warnings: list) -> None:
    """寫 _parse_report.json：{ parsed_count, skipped, warnings, errors }（覆寫式）。

    warnings 記非致命問題（.md 衍生物寫入失敗等），不影響 [3] 的 exit code。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "parsed_count": parsed_count,
        "skipped": skipped,
        "warnings": warnings,
        "errors": errors,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def write_extraction_report(path: Path, manifest: dict, stats: dict) -> None:
    """寫 reports/extraction_report.md（人類閱讀用，覆蓋更新）。"""
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# [3] 抽取報告 — {manifest['version']} / {manifest['mod']}")
    lines.append("")
    lines.append(f"- URL 真值來源：{manifest.get('source', 'sitemap')}（sitemap.xml）")
    lines.append(f"- 處理頁數（成功抓取）：{stats['total']}")
    lines.append(f"- parsed（已輸出 extracted JSON）：{stats['parsed_count']}")
    lines.append(f"- skipped（navigation_only）：{len(stats['skipped'])}")
    lines.append(f"- errors：{len(stats['errors'])}")
    lines.append("")

    if stats["skipped"]:
        lines.append("## Skipped（navigation_only）")
        lines.append("")
        lines.append("| URL | reason |")
        lines.append("| --- | --- |")
        for s in stats["skipped"]:
            lines.append(f"| {s['url']} | {s['reason']} |")
        lines.append("")

    if stats["errors"]:
        lines.append("## Errors")
        lines.append("")
        lines.append("| URL | error |")
        lines.append("| --- | --- |")
        for e in stats["errors"]:
            lines.append(f"| {e['url']} | {e['error']} |")
        lines.append("")

    # 空欄位標記（AGENTS.md §6 [3]：報告記錄 source/title 為空的頁）
    empty_source = [p for p in stats.get("parsed_detail", []) if not p.get("source")]
    empty_title = [p for p in stats.get("parsed_detail", []) if not p.get("title")]
    if empty_source or empty_title:
        lines.append("## 空欄位警示（供人工查驗）")
        lines.append("")
        for p in empty_source:
            lines.append(f"- source 為空：{p['url']}")
        for p in empty_title:
            lines.append(f"- title 為空：{p['url']}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 編排
# ---------------------------------------------------------------------------
def main() -> int:
    """[3] 主流程。回傳 exit code：0 成功；1 表輸入或設定層級錯誤。"""
    manifest = load_manifest(MANIFEST_PATH)
    html_entries = collected_html_files(manifest)
    print(f"[2] manifest 成功頁數：{len(html_entries)}")

    if not html_entries:
        print("[2] 無可用 HTML（0 頁成功），停止 [3]", file=sys.stderr)
        return 1

    skipped = []
    errors = []
    warnings = []          # .md 衍生物寫入失敗等非致命問題（不影響 exit code）
    index_rows = []        # _index.md 的資料列（只列成功輸出 JSON 的頁）
    parsed_detail = []
    parsed_count = 0

    for entry in html_entries:
        url = entry["url"]
        html_path = PROJECT_ROOT / entry["local_path"]
        html = html_path.read_text(encoding="utf-8")

        # 抽取：trafilatura 無法抽出 -> 記錄錯誤，繼續其他頁（不中斷）
        extracted = extract_page(html)
        if extracted is None:
            errors.append({"url": url, "error": "trafilatura_extract_returned_none"})
            print(f"  ERR  {url} -> extract 回傳 None", file=sys.stderr)
            continue

        # navigation_only 判定：命中即跳過，不輸出 extracted 檔
        nav, reason = is_navigation_only(url, extracted, html)
        if nav:
            skipped.append({"url": url, "reason": reason})
            print(f"  SKIP {url} -> {reason}")
            continue

        record = build_extracted_record(extracted, entry.get("http_status"))
        out_path = extracted_output_path(entry["local_path"])
        write_json(out_path, record)
        parsed_count += 1
        parsed_detail.append({"url": url, "source": record.get("source"),
                              "title": record.get("title")})
        print(f"  OK   {url} -> {out_path.relative_to(PROJECT_ROOT)}")

        # 人類可讀 .md：JSON 成功後才寫；失敗只記 warning，不影響 exit code
        md_path = readable_output_path(entry["local_path"])
        try:
            write_readable_md(md_path, record)
            print(f"       -> {md_path.relative_to(PROJECT_ROOT)}")
        except OSError as exc:
            warnings.append({
                "url": url,
                "phase": "readable_md",
                "error": f"{type(exc).__name__}: {exc}",
            })
            print(f"  WARN {url} -> .md 寫入失敗：{exc}", file=sys.stderr)

        # _index.md 資料列（chapter／page_slug 取自 manifest，非 .md 路徑）
        index_rows.append({
            "title": record.get("title"),
            "chapter": entry.get("chapter"),
            "page_slug": entry.get("page_slug"),
            "text_length": len(record.get("text") or ""),
            "source": record.get("source"),
        })

    # _index.md：列全部已輸出頁。失敗只記 warning，不影響 exit code
    try:
        write_readable_index(READABLE_INDEX_PATH, manifest, index_rows)
    except OSError as exc:
        warnings.append({
            "phase": "readable_index",
            "error": f"{type(exc).__name__}: {exc}",
        })
        print(f"  WARN _index.md 寫入失敗：{exc}", file=sys.stderr)

    # 報告
    stats = {
        "total": len(html_entries),
        "parsed_count": parsed_count,
        "skipped": skipped,
        "warnings": warnings,
        "errors": errors,
        "parsed_detail": parsed_detail,
    }
    write_parse_report(PARSE_REPORT_PATH, parsed_count, skipped, errors, warnings)
    write_extraction_report(EXTRACTION_REPORT_PATH, manifest, stats)

    print(f"\n[3] 結果：parsed={parsed_count} skipped={len(skipped)} "
          f"warnings={len(warnings)} errors={len(errors)}")
    print(f"     合計 {parsed_count + len(skipped) + len(errors)} / {len(html_entries)} 頁")
    return 0


if __name__ == "__main__":
    sys.exit(main())
