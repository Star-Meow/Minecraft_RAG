"""[5] 切分（子母分層）。

職責：讀 [4] 的 cleaned MD（data/processed/cleaned/<version>/<mod_slug>/<chapter>/<page>.md），
依章節切成 parent，再在 parent 內切出 child，輸出
data/processed/chunks/<version>/parents.jsonl 與 children.jsonl，
並產生 reports/chunking_report.md（docs/04_chunk.md）。

方法：
- parent：MarkdownHeaderTextSplitter 依 #／## 切；### 併入所屬的 ## parent。
  標題行保留在正文（strip_headers=False），標題路徑另存 section。
  第一個 ## 之前的開頭段落獨立成 parent，section = 頁面 title；極短 parent 不合併。
- child：RecursiveCharacterTextSplitter 在 parent 內切（overlap 32，切分點 \n → ". " → " " → ""）；
  section 取 child 起點所在的標題路徑（細到 ###）。
- token 以 BGE-M3 tokenizer 計算（鎖定 revision、add_special_tokens=False、含標題行）。
  parent > 2048 或 child > 256 → 不寫任何產出，exit 1。

只讀 cleaned MD，不讀 extracted JSON 或 manifest；結構性 metadata 讀路徑、
內容性 metadata（title／source_url）讀 frontmatter，原封傳遞。
設計原則（同 [3]／[4]）：模組化、低語法糖、型別標註、main() 只做編排。
"""

from __future__ import annotations

import json
import re
import shutil
import statistics
import sys
from pathlib import Path

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

# ---------------------------------------------------------------------------
# [5.0] 設定
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLEANED_DIR = PROJECT_ROOT / "data" / "processed" / "cleaned"
CHUNKS_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"
REPORTS_DIR = PROJECT_ROOT / "reports"
SOURCES_PATH = PROJECT_ROOT / "sources.json"
REPORT_PATH = REPORTS_DIR / "chunking_report.md"

TOKENIZER_NAME = "BAAI/bge-m3"
TOKENIZER_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"   # 與 [6] 使用同一 revision

PARENT_MAX_TOKENS = 2048
CHILD_MAX_TOKENS = 256
CHILD_OVERLAP_TOKENS = 32
CHILD_SEPARATORS = ["\n", ". ", " ", ""]
HEADERS_TO_SPLIT_ON = [("#", "h1"), ("##", "h2")]   # ### 不切，併入所屬的 ## parent
SHORT_PARENT_TOKENS = 50                            # 報告標示用，不合併
SECTION_SEP = " > "

NEWLINE = "\n"
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
SUB_HEADING_RE = re.compile(r"^(#{3,6}) (.*)$")


# ---------------------------------------------------------------------------
# [5.1] 輸入
# ---------------------------------------------------------------------------
def load_sources(path: Path) -> dict:
    """讀 sources.json；缺檔代表 [1] 未設定，直接報錯。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}：[1] sources.json 不存在")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def collect_pages(version: str) -> list:
    """收集 [4] 的 cleaned MD，依路徑排序保證輸出順序決定性。"""
    root = CLEANED_DIR / version
    if not root.is_dir():
        raise FileNotFoundError(f"找不到 {root}：請先執行 [4] src/clean_pages.py")
    return sorted(root.rglob("*.md"))


def path_metadata(md_file: Path) -> dict:
    """結構性 metadata 一律由目錄路徑承載（<version>/<mod_slug>/<chapter>/<page>.md）。"""
    return {
        "version": md_file.parent.parent.parent.name,
        "mod": md_file.parent.parent.name,
        "chapter": md_file.parent.name,
        "page": md_file.stem,
    }


def _yaml_unscalar(raw: str) -> str:
    """還原 [4] _yaml_scalar 輸出的字串（雙引號包裹時解開跳脫）。"""
    value = raw.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        return re.sub(r'\\(["\\])', r"\1", inner)
    return value


def parse_cleaned_md(text: str) -> tuple:
    """拆出 frontmatter（title／source_url）與正文；正文以 # <title> 開頭。"""
    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise ValueError("缺少 frontmatter")
    meta = {}
    for line in match.group(1).split(NEWLINE):
        key, sep, raw = line.partition(":")
        if sep:
            meta[key.strip()] = _yaml_unscalar(raw)
    body = text[match.end():].lstrip(NEWLINE)
    return meta.get("title", ""), meta.get("source_url", ""), body


# ---------------------------------------------------------------------------
# [5.2] 切分
# ---------------------------------------------------------------------------
def build_splitters(count_tokens) -> tuple:
    """parent 依 #／## 切（保留標題行）；child 依 token 數切。"""
    parent_splitter = MarkdownHeaderTextSplitter(HEADERS_TO_SPLIT_ON, strip_headers=False)
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHILD_MAX_TOKENS,
        chunk_overlap=CHILD_OVERLAP_TOKENS,
        length_function=count_tokens,
        separators=CHILD_SEPARATORS,
        keep_separator="end",
        add_start_index=True,
    )
    return parent_splitter, child_splitter


def parent_section(title: str, metadata: dict) -> str:
    """parent 的標題路徑：開頭段落 = 頁面 title；## 章節 = title > ##。"""
    h2 = metadata.get("h2")
    if h2:
        return title + SECTION_SEP + h2
    return title


def child_section(parent_sec: str, parent_text: str, start_index: int) -> str:
    """child 的標題路徑：parent 路徑 + child 起點之前最近的 ###（以下）標題。"""
    stack = []          # [(level, text)]
    offset = 0
    for line in parent_text.split(NEWLINE):
        if offset > start_index:
            break
        match = SUB_HEADING_RE.match(line.strip())
        if match:
            level = len(match.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, match.group(2).strip()))
        offset += len(line) + 1
    return SECTION_SEP.join([parent_sec] + [text for _, text in stack])


def chunk_page(md_file: Path, splitters: tuple, count_tokens) -> tuple:
    """切一頁：回傳 (parents, children, log)。source_url 為空 → 不產出、記錯誤。"""
    parent_splitter, child_splitter = splitters
    base = path_metadata(md_file)
    title, source_url, body = parse_cleaned_md(md_file.read_text(encoding="utf-8"))
    log = {"page": md_file, "error": None, "n_parents": 0, "n_children": 0}
    if not title or not source_url:
        log["error"] = "frontmatter 的 title 或 source_url 為空"
        return [], [], log

    id_prefix = ":".join([base["version"], base["mod"], base["chapter"], base["page"]])
    parents = []
    children = []
    for p_idx, doc in enumerate(parent_splitter.split_text(body), start=1):
        parent_id = f"{id_prefix}:p{p_idx:02d}"
        p_sec = parent_section(title, doc.metadata)
        p_text = doc.page_content
        common = {"title": title, "source_url": source_url, **base}
        parents.append({
            "parent_id": parent_id,
            "text": p_text,
            **common,
            "section": p_sec,
            "token_count": count_tokens(p_text),
        })
        for c_idx, c_doc in enumerate(child_splitter.create_documents([p_text]), start=1):
            c_text = c_doc.page_content
            children.append({
                "chunk_id": f"{parent_id}:c{c_idx:02d}",
                "parent_id": parent_id,
                "text": c_text,
                **common,
                "section": child_section(p_sec, p_text, c_doc.metadata["start_index"]),
                "token_count": count_tokens(c_text),
            })
    log["n_parents"] = len(parents)
    log["n_children"] = len(children)
    return parents, children, log


def find_over_limit(parents: list, children: list) -> list:
    """上限斷言：parent ≤ 2048、child ≤ 256（含標題行）。回傳違規清單。"""
    over = []
    for p in parents:
        if p["token_count"] > PARENT_MAX_TOKENS:
            over.append(f"parent {p['parent_id']}：{p['token_count']} > {PARENT_MAX_TOKENS}")
    for c in children:
        if c["token_count"] > CHILD_MAX_TOKENS:
            over.append(f"child {c['chunk_id']}：{c['token_count']} > {CHILD_MAX_TOKENS}")
    return over


# ---------------------------------------------------------------------------
# [5.3] 輸出（chunks/<version>/ 重建：人工已授權的敏感操作）
# ---------------------------------------------------------------------------
def assert_rebuild_target(version: str) -> Path:
    """斷言重建目標合法：必須是 CHUNKS_DIR 的直接版本子目錄，且 CHUNKS_DIR 位置正確。"""
    if CHUNKS_DIR != PROJECT_ROOT / "data" / "processed" / "chunks":
        raise RuntimeError(f"CHUNKS_DIR 位置異常：{CHUNKS_DIR}")
    if not version or not version.isascii() or "/" in version or "\\" in version:
        raise ValueError(f"version 不合法：{version!r}")
    return CHUNKS_DIR / version


def rebuild_chunks_dir(version_dir: Path) -> None:
    """清空 chunks/<version>/ 並重建。呼叫前須先通過 assert_rebuild_target。"""
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Path, records: list) -> None:
    """一行一筆 JSON（UTF-8、不跳脫非 ASCII、強制 LF）。"""
    with path.open("w", encoding="utf-8", newline=NEWLINE) as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + NEWLINE)


# ---------------------------------------------------------------------------
# [5.4] 報告
# ---------------------------------------------------------------------------
def _md_cell(value) -> str:
    """Markdown 表格 cell：跳脫 pipe 與換行。"""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _distribution(values: list) -> str:
    """數量／中位數／p95／最大。"""
    if not values:
        return "| 0 | — | — | — |"
    ordered = sorted(values)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    return f"| {len(values)} | {statistics.median(values)} | {p95} | {max(values)} |"


def write_chunking_report(path: Path, version: str, n_input: int, logs: list,
                          parents: list, children: list) -> None:
    """寫 reports/chunking_report.md（單次報告，整份覆寫）。"""
    n_out = sum(1 for log in logs if log["error"] is None)
    errors = [log for log in logs if log["error"] is not None]
    multi = {}
    for c in children:
        multi[c["parent_id"]] = multi.get(c["parent_id"], 0) + 1
    multi_parents = [p for p in parents if multi.get(p["parent_id"], 0) > 1]
    short = [p for p in parents if p["token_count"] < SHORT_PARENT_TOKENS]

    lines = [
        "# 切分報告（[5] chunk_pages.py）",
        "",
        "## 1. 設定",
        "",
        f"- version：`{version}`",
        f"- tokenizer：`{TOKENIZER_NAME}` @ `{TOKENIZER_REVISION}`（`add_special_tokens=False`，含標題行）",
        f"- parent：依 `#`／`##` 切（`strip_headers=False`），上限 {PARENT_MAX_TOKENS}",
        f"- child：上限 {CHILD_MAX_TOKENS}、overlap {CHILD_OVERLAP_TOKENS}、切分點 `{CHILD_SEPARATORS}`",
        "",
        "## 2. 對帳",
        "",
        f"- 輸入頁數：{n_input}",
        f"- 有產出的頁數：{n_out}",
        f"- 錯誤（未產出）頁數：{len(errors)}",
        f"- 合計：{n_out} + {len(errors)} = {n_out + len(errors)}",
        "",
        "## 3. 分布（tokens）",
        "",
        "| 對象 | 數量 | 中位數 | p95 | 最大 |",
        "| --- | --- | --- | --- | --- |",
        "| parent " + _distribution([p["token_count"] for p in parents]),
        "| child " + _distribution([c["token_count"] for c in children]),
        "",
        f"- 被切成多個 child 的 parent：{len(multi_parents)}",
        f"- 有多個 parent 的頁：{sum(1 for log in logs if log['n_parents'] > 1)}",
        "",
        f"## 4. 短 parent（< {SHORT_PARENT_TOKENS} tokens，僅列出，不合併）",
        "",
        f"- 數量：{len(short)}",
        "",
        "| parent_id | tokens | section |",
        "| --- | --- | --- |",
    ]
    for p in short:
        lines.append(f"| `{p['parent_id']}` | {p['token_count']} | {_md_cell(p['section'])} |")
    lines += ["", "## 5. 錯誤（未產出）", ""]
    if errors:
        for log in errors:
            rel = log["page"].relative_to(CLEANED_DIR).as_posix()
            lines.append(f"- `{rel}`：{log['error']}")
    else:
        lines.append("- 無")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline=NEWLINE) as f:
        f.write(NEWLINE.join(lines))


# ---------------------------------------------------------------------------
# [5.5] 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    """[5] 主流程。回傳 exit code：0 成功；1 表輸入錯誤、有頁未產出或超過上限。"""
    sources = load_sources(SOURCES_PATH)
    version = sources["version"]
    print(f"[1] sources.json：version={version} mod={sources['mod']}")

    try:
        page_paths = collect_pages(version)
    except FileNotFoundError as exc:
        print(f"[5] 中止：{exc}", file=sys.stderr)
        return 1
    if not page_paths:
        print(f"[5] 中止：{version} 下無 cleaned MD，不刪除現有輸出", file=sys.stderr)
        return 1
    print(f"[4] cleaned MD：{len(page_paths)} 頁")

    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME, revision=TOKENIZER_REVISION)

    def count_tokens(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    splitters = build_splitters(count_tokens)

    # 全部先在記憶體處理；確認沒有超限、且有產出，才清空並寫入
    parents = []
    children = []
    logs = []
    for md_file in page_paths:
        rel = md_file.relative_to(CLEANED_DIR / version).as_posix()
        try:
            page_parents, page_children, log = chunk_page(md_file, splitters, count_tokens)
        except Exception as exc:                    # noqa: BLE001 - 逐頁隔離，不中斷全批
            log = {"page": md_file, "error": f"處理例外：{type(exc).__name__}: {exc}",
                   "n_parents": 0, "n_children": 0}
            page_parents, page_children = [], []
        logs.append(log)
        if log["error"] is not None:
            print(f"  ERR  {rel} -> {log['error']}", file=sys.stderr)
            continue
        parents.extend(page_parents)
        children.extend(page_children)
        print(f"  OK   {rel}  parents={log['n_parents']} children={log['n_children']}")

    over = find_over_limit(parents, children)
    if over:
        for item in over:
            print(f"  OVER {item}", file=sys.stderr)
        print("[5] 中止：超過 token 上限，不寫任何產出（需人工處理）", file=sys.stderr)
        return 1
    if not parents:
        print("[5] 中止：無任何頁產出，不刪除現有輸出", file=sys.stderr)
        return 1

    version_dir = assert_rebuild_target(version)
    rebuild_chunks_dir(version_dir)
    print(f"[5] 已重建 {version_dir.relative_to(PROJECT_ROOT)}")
    write_jsonl(version_dir / "parents.jsonl", parents)
    write_jsonl(version_dir / "children.jsonl", children)
    write_chunking_report(REPORT_PATH, version, len(page_paths), logs, parents, children)

    n_errors = sum(1 for log in logs if log["error"] is not None)
    print(f"\n[5] 結果：pages={len(page_paths) - n_errors} errors={n_errors} "
          f"parents={len(parents)} children={len(children)}")
    print(f"     報告：{REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 1 if n_errors else 0


if __name__ == "__main__":
    sys.exit(main())
