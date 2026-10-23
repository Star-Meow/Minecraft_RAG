"""[4] 清理與結構化（去噪）。

職責：讀 [3] 的 extracted JSON（markdown 欄位：text 加上 [3] 標好的標題記號），
過濾 trafilatura 誤留的噪音，輸出含 frontmatter 與 H1 的 cleaned MD
（data/processed/cleaned/<version>/<mod_slug>/<chapter>/<page>.md），
並產生 reports/cleaning_report.md。
規則一律以「去掉標題記號後的行內容」比對；標題行與一般行套用相同規則（docs/03_clean.md）。

「無圖片版本」前提：本站的配方以圖片呈現，trafilatura 抽出後只剩標籤文字空殼。
規則依目前這批資料校準；網站加入圖片相關內容後須重新盤點（見 docs/03_clean.md）。

規則集（有序，AGENTS.md §6 [4]）：
- R2 站名首行警告：首行 == 站名 → 照常輸出，報告列為警告（不排除、不看字數；跳轉頁改由抽取列清單，
  人工複核後再排除，見 docs/03_clean.md）
- R1 首行標題去重：A 首行 == title 刪首行／B title 黏在句首切前綴／C 次行 == title 刪次行
- R4a 整行標籤：整行（去空白）完全等於標籤詞 → 刪該行
- R4b 黏合尾端標籤：行尾黏合的標籤序列，自第一個 Recipe/Recipes 起到行尾
  全為標籤詞才切除；切除後該行必須仍有內容
- R6 標題層級正規化：頁內剩餘標題依相對深度輸出為 ##／###／####
  （整頁只保留 [4] 寫入的 # <title>；多 H1 頁的頁內 H1 → ##、其下 H2 → ###，見 docs/03_clean.md）
- R7 空章節移除：沒有任何內容的標題（R4a 刪光標籤後的殘留）一併刪除（docs/03_clean.md）
- R8 配方輸出：[3] 的 recipes 欄位轉為頁尾的 ## Recipes，每個配方一行「類型: 材料 → 產物」
- 空 body 守衛：規則處理後 body 為空 → 不輸出；不足 200 字元 → 輸出但標示

不處理：孤立 `-`、句子之間的黏合、相鄰表格、段落空行（僅計數與記錄）。

設計原則（同 [3]）：模組化、低語法糖、型別標註、main() 只做編排。
只讀 [3] 的 extracted JSON，不讀 raw HTML 產物；不新增依賴；
_yaml_scalar 複製自 [3]。（相關定位見 AGENTS.md §5）
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = PROJECT_ROOT / "data" / "processed" / "extracted"
CLEANED_DIR = PROJECT_ROOT / "data" / "processed" / "cleaned"
REPORTS_DIR = PROJECT_ROOT / "reports"
SOURCES_PATH = PROJECT_ROOT / "sources.json"
REPORT_PATH = REPORTS_DIR / "cleaning_report.md"

SITE_NAME = "Applied Energistics 2"
SHORT_BODY_THRESHOLD = 200       # body 短於此字元數 → 報告標示（仍輸出）

# 配方標籤白名單。排列順序為「長 token 優先」，是 R4b 貪婪切割的必要條件
# （Recipes 必須早於 Recipe 被嘗試，否則 'RecipesCrafting' 會被誤切成
# 'Recipe' + 'sCrafting…'）。R4a 為整行精確比對，順序不影響。
LABELS = (
    "Crafting (Shapeless)",
    "Throw in Water",
    "Inscriber",
    "Crafting",
    "Smelting",
    "Smithing",
    "Recipes",
    "Charger",
    "Recipe",
)
LABEL_SET = frozenset(LABELS)
GENERIC_LABELS = frozenset({"Recipe", "Recipes", "Crafting", "Crafting (Shapeless)"})
METHOD_LABELS = LABEL_SET - GENERIC_LABELS

# cleaned MD 輸出一律 LF（[4] 是第一個 LF 產物；[3] 的衍生物在 Windows 上為 CRLF）
NEWLINE = "\n"

# [3] markdown 欄位的標題行：'#'×level + 空格 + 標題文字（docs/02_extract.md）
HEADING_RE = re.compile(r"^(#{1,6}) (.*)$")
MIN_SUB_LEVEL = 2                # R6：頁內標題最高只到 ##（# 保留給 <title>）
RECIPES_HEADING = "## Recipes"   # R8：配方段落的標題（自成一個章節）


# ---------------------------------------------------------------------------
# [4.1] 輸入收集
# ---------------------------------------------------------------------------
def load_sources(path: Path) -> dict:
    """讀 sources.json；缺檔代表 [1] 未設定，直接報錯。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}：[1] sources.json 不存在")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def collect_pages(version: str) -> list:
    """收集 [3] 的 extracted JSON，依路徑排序保證輸出順序決定性。

    只 rglob <version>/ 下的 *.json，排除底線開頭的報告檔（_parse_report.json）。
    <mod_slug>/<chapter>/<page_slug>.json 的相對結構直接鏡射到輸出路徑，
    不重新計算 slug（權威來源分離：結構性 metadata 一律由路徑承載）。
    """
    root = EXTRACTED_DIR / version
    if not root.is_dir():
        raise FileNotFoundError(f"找不到 {root}：請先執行 [3] src/extract_pages.py")
    return [p for p in sorted(root.rglob("*.json")) if not p.name.startswith("_")]


def cleaned_output_path(extracted_path: Path) -> Path:
    """extracted/<version>/<mod>/<chapter>/<page>.json → cleaned/同結構 .md。"""
    rel = extracted_path.relative_to(EXTRACTED_DIR)
    return CLEANED_DIR / rel.with_suffix(".md")


# ---------------------------------------------------------------------------
# [4.2] 規則
# ---------------------------------------------------------------------------
def split_heading(line: str) -> tuple:
    """拆出標題記號：回傳 (level, 內容)；非標題行 level 為 0、內容為原行。"""
    m = HEADING_RE.match(line)
    if m is None:
        return 0, line
    return len(m.group(1)), m.group(2)


def content_of(line: str) -> str:
    """去掉標題記號後的行內容（規則比對一律用它）。"""
    return split_heading(line)[1]


def starts_with_site_name(text: str) -> bool:
    """R2：首行等於站名，供報告警告（可能是跳轉頁；不排除）。"""
    lines = text.split("\n")
    first = lines[0].strip() if lines else ""
    return first == SITE_NAME


def dedup_title(title: str, lines: list) -> tuple:
    """R1 首行標題去重。只動第一行或第二行；回傳 (新行清單, 型別或 None, 附註)。

    A：第一行 == title → 刪第一行
    B：第一行以 title 開頭且更長 → 切前綴；守衛：剩餘首字元須為大寫英文字母，
       否則不切（附註記錄，供報告警告）
    C：第二行 == title 且第一行不是站名 → 刪第二行，保留第一行
    頁內其他位置的同名文字一律不動。
    """
    if not title:
        return lines, None, ""

    # 比對用去掉標題記號的內容（[3] 已把頁面 H1 標成 '# <title>'）
    l0 = content_of(lines[0]) if lines else ""
    l1 = content_of(lines[1]) if len(lines) > 1 else None

    if l0 == title:
        return lines[1:], "A", ""
    if l0.startswith(title) and len(l0) > len(title):
        rest = l0[len(title):]
        if len(rest) >= 1 and "A" <= rest[0] <= "Z":
            return [rest] + lines[1:], "B", ""
        # 守衛未過：不切，附註供報告警示（本批 21/21 通過）
        return lines, None, f"r1_b_guard: 前綴切除後首字元非大寫英文，剩餘={rest[:40]!r}"
    if l1 is not None and l1 == title and l0.strip() != SITE_NAME:
        return [lines[0]] + lines[2:], "C", ""

    return lines, None, ""


def strip_label_lines(lines: list) -> tuple:
    """R4a：刪除整行（去標題記號與前後空白）完全等於標籤詞的行。

    標題行一併適用（如 [3] 標成 '## Recipe' 的配方區塊標題）。
    回傳 (新行清單, 已刪標籤清單)。
    """
    kept = []
    removed = []
    for ln in lines:
        s = content_of(ln).strip()
        if s in LABEL_SET:
            removed.append(s)
        else:
            kept.append(ln)
    return kept, removed


def _tokenize_label_run(s: str) -> tuple:
    """把字串貪婪切成標籤 token；容許 token 之間單一空格，區分大小寫。

    長 token 優先（LABELS 的排列順序）。回傳 (是否全為標籤, token 清單)。
    """
    tokens = []
    i = 0
    space_allowed = False
    while i < len(s):
        if s[i] == " ":
            if not space_allowed:
                return False, []
            i += 1
            space_allowed = False
            continue
        matched = None
        for lab in LABELS:
            if s.startswith(lab, i):
                matched = lab
                break
        if matched is None:
            return False, []
        tokens.append(matched)
        i += len(matched)
        space_allowed = True
    return True, tokens


def find_label_tail_cut(line: str) -> tuple:
    """R4b：尋找行尾黏合的標籤序列切點。

    自第一個可完整切割到行尾的 Recipe/Recipes 起，到行尾全為標籤詞，
    且該位置黏在前文之後（前一字元非空白）→ 回傳 (切割後前段, token 清單)。
    前一段為空（整行皆標籤）也回傳，由呼叫端依「切除後須有內容」守衛處理。
    找不到回傳 (None, None)。
    """
    for i in range(len(line)):
        if not line.startswith("Recipe", i):
            continue
        if i > 0 and line[i - 1] == " ":
            continue
        ok, tokens = _tokenize_label_run(line[i:])
        if ok:
            return line[:i], tokens
    return None, None


def strip_glued_label_tail(lines: list) -> tuple:
    """R4b：逐行處理行尾黏合標籤。回傳 (新行清單, 每筆 token 清單, 異常附註)。

    切除後該行必須仍有內容；若會切空則不切，記異常附註供報告警告。
    """
    new_lines = []
    removed_seqs = []
    notes = []
    for ln in lines:
        head, tokens = find_label_tail_cut(ln)
        if tokens is None:
            new_lines.append(ln)
            continue
        if head.strip() == "":
            notes.append(f"r4b 切除後該行無內容，未切除：{ln!r}")
            new_lines.append(ln)
            continue
        new_lines.append(head)
        removed_seqs.append(tokens)
    return new_lines, removed_seqs, notes


def find_suspect_labels(lines: list) -> list:
    """疑似新標籤：長度 ≤ 40、不在白名單、不以 '- ' 開頭，且與白名單行相鄰。

    僅列出供人工判斷，不自動刪除（清單與門檻依本批校準，見 docs/03_clean.md）。
    須在 R4a 刪除前行算「相鄰」關係，故只由 process_page 在 R1 之後呼叫。
    """
    label_idx = {i for i, ln in enumerate(lines) if content_of(ln).strip() in LABEL_SET}
    suspects = []
    for i, ln in enumerate(lines):
        s = content_of(ln).strip()
        if not s or len(s) > 40:
            continue
        if s in LABEL_SET or s.startswith("- "):
            continue
        if i in label_idx:
            continue
        if (i - 1) in label_idx or (i + 1) in label_idx:
            suspects.append(s)
    return suspects


def normalize_heading_levels(lines: list) -> tuple:
    """R6：頁內標題依相對深度輸出為 ##、###、####（# 保留給 <title>）。

    以堆疊追蹤祖先標題：遇到原層級 L 時，先彈出原層級 >= L 的祖先，
    輸出層級 = 2 + 剩餘祖先數。效果：
    - 一般頁：h2 → ##、其下 h3 → ###；只有 h3 的頁 → ##
    - 多 H1 頁：頁內 H1 → ##、其下 H2 → ###；出現在第一個頁內 H1 之前、
      直屬頁面標題的 H2 仍為 ##（不產生沒有上層的 ###）
    回傳 (新行清單, {輸出層級: 數量})。
    """
    stack = []
    new_lines = []
    counts = {}
    for ln in lines:
        level, content = split_heading(ln)
        if level == 0:
            new_lines.append(ln)
            continue
        while stack and stack[-1] >= level:
            stack.pop()
        out_level = MIN_SUB_LEVEL + len(stack)
        stack.append(level)
        new_lines.append("#" * out_level + " " + content)
        counts[out_level] = counts.get(out_level, 0) + 1
    return new_lines, counts


def render_recipe(recipe: dict) -> str:
    """R8：配方轉為一行文字，順序為「類型: 材料 → 產物」。

    類型 = 頁面上的類型文字 + [類型圖示名稱]（保留 Furnace／Blast Furnace 等差異）。
    材料：一般配方為「數量 × 名稱」；Inscriber／Smithing 為「槽位 名稱」。產物不寫數量（HTML 無此資訊）。
    """
    kind = f"{recipe['label']} [{recipe['station']}]"
    if recipe.get("slots"):
        inputs = ", ".join(f"{slot} {name}" for slot, name in recipe["slots"])
    else:
        inputs = ", ".join(f"{i['count']} × {i['name']}" for i in recipe["ingredients"])
    return f"- {kind}: {inputs} → {recipe['result']}"


def drop_empty_sections(lines: list) -> tuple:
    """R7：刪除沒有任何內容的標題（R4a 刪光標籤後留下的空章節，見 docs/03_clean.md）。

    標題的範圍到下一個「同層或更高層」標題為止；範圍內只要有一行非空白的
    非標題行，就不算空。由深到淺判定，所以只含空子章節的章節也一併刪除。
    回傳 (新行清單, 已刪標題清單)。
    """
    removed = []
    changed = True
    while changed:
        changed = False
        for i, ln in enumerate(lines):
            level, content = split_heading(ln)
            if level == 0:
                continue
            has_content = False
            j = i + 1
            while j < len(lines):
                sub_level = split_heading(lines[j])[0]
                if sub_level and sub_level <= level:
                    break
                if sub_level == 0 and lines[j].strip():
                    has_content = True
                    break
                j += 1
            if not has_content:
                removed.append(ln)
                lines = lines[:i] + lines[i + 1:]
                changed = True
                break
    return lines, removed


# ---------------------------------------------------------------------------
# [4.3] 單頁處理
# ---------------------------------------------------------------------------
def process_page(record: dict) -> tuple:
    """對單頁施規則集（R2 → R1 → R4a → R4b → R6 → R7 → R8 → 空 body 守衛）。

    輸入為 [3] 的 markdown 欄位（缺欄位 → ValueError，由呼叫端逐頁隔離）。
    回傳 (body 或 None（不輸出）, 判定紀錄 dict)。
    判定紀錄供 cleaning_report.md 逐項記帳，並承載寫檔所需的 title／source。
    """
    if "markdown" not in record:
        raise ValueError("extracted JSON 缺 markdown 欄位，請先重跑 [3] src/extract_pages.py")
    title = record.get("title") or ""
    source = record.get("source") or ""
    markdown = record.get("markdown") or ""
    # R2 判定與字元統計使用不含標題記號的純文字
    text = "\n".join(content_of(ln) for ln in markdown.split("\n"))
    log = {
        "title": title,
        "source": source,
        "title_empty": not title,
        "source_empty": not source,
        "redirect": False,
        "site_name_not_excluded": False,
        "r1_type": None,
        "r1_note": "",
        "labels_removed": [],
        "r4b_seqs": [],
        "suspect_lines": [],
        "notes": [],
        "orphan_dashes": 0,
        "heading_counts": {},
        "empty_sections": [],
        "recipes_added": 0,
        "chars_before": len(text),
        "chars_after": 0,
        "short_body": False,
        "skip_reason": None,
    }

    # 前置條件：title 或 source 為空 → 不輸出（AGENTS.md §7：無來源 URL 的內容
    # 不得進入知識庫；title 為空則 frontmatter 與 H1 無法寫）
    if log["title_empty"] or log["source_empty"]:
        log["skip_reason"] = "missing_title_or_source"
        return None, log

    # R2 站名首行警告：不排除、不看字數（跳轉頁由抽取列清單，人工複核後再排除）
    if starts_with_site_name(text):
        log["site_name_not_excluded"] = True      # 報告附錄列為警告（見 write_cleaning_report）

    lines = markdown.split("\n")

    # 孤立 `-`：只計數，不處理（人工裁定：不還原、不接回）
    log["orphan_dashes"] = sum(1 for ln in lines if content_of(ln).strip() == "-")

    # R1
    lines, log["r1_type"], log["r1_note"] = dedup_title(title, lines)
    if log["r1_note"]:
        log["notes"].append(log["r1_note"])

    # 疑似新標籤：R1 之後、R4a 之前計算（此時標籤行尚未刪除，「相鄰」關係才看得到）
    log["suspect_lines"] = find_suspect_labels(lines)

    # R4a
    lines, log["labels_removed"] = strip_label_lines(lines)

    # R4b：僅適用「整頁黏成單行」的頁（人工裁定：R4b 處理整頁黏成單行時
    # 黏在行尾的標籤）。多行頁的行尾標籤序列可能是合法標題——全庫僅一例：
    # condenser 的 'Settings/Recipes'（'Settings/' + 'Recipes'）。
    if "\n" not in text:
        lines, log["r4b_seqs"], r4b_notes = strip_glued_label_tail(lines)
        log["notes"].extend(r4b_notes)

    # R6 標題層級正規化（頁面 H1 已由 R1 移除；整頁只保留寫檔時的 # <title>）
    lines, log["heading_counts"] = normalize_heading_levels(lines)

    # R7 空章節移除（R4a 刪光內容後只剩標題的章節）
    lines, log["empty_sections"] = drop_empty_sections(lines)
    for ln in log["empty_sections"]:
        level = split_heading(ln)[0]
        log["heading_counts"][level] -= 1
        if log["heading_counts"][level] == 0:
            del log["heading_counts"][level]

    log["chars_after"] = len("\n".join(content_of(ln) for ln in lines))

    # R8 配方輸出：所有規則之後，於頁尾加上 ## Recipes（來自 [3] 的 recipes 欄位，不受前述規則影響）
    recipes = record.get("recipes") or []
    if recipes:
        lines = lines + [RECIPES_HEADING] + [render_recipe(r) for r in recipes]
    log["recipes_added"] = len(recipes)

    body = "\n".join(lines)

    # 空 body 守衛
    if body.strip() == "":
        log["skip_reason"] = "empty_body"
        return None, log

    log["short_body"] = log["chars_after"] < SHORT_BODY_THRESHOLD
    return body, log


# ---------------------------------------------------------------------------
# [4.4] 輸出
# ---------------------------------------------------------------------------
def _yaml_scalar(value) -> str:
    """把值輸出為安全的 YAML scalar（複製自 [3] src/extract_pages.py，不跨模組 import）。

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


def build_cleaned_md(title: str, source: str, body: str) -> str:
    """組 cleaned MD：frontmatter（title／source_url）→ 空行 → # <title> → 空行 → body。

    title 與 source 只能原封傳遞（資料不異動）；frontmatter 與 H1 之間、
    H1 與 body 之間各有一空行（避免影響 Markdown 解析與 [5] 的 splitter）。
    """
    lines = [
        "---",
        f"title: {_yaml_scalar(title)}",
        f"source_url: {_yaml_scalar(source)}",
        "---",
        "",
        f"# {title}",
        "",
        body,
    ]
    return "\n".join(lines) + NEWLINE


def write_md(path: Path, content: str) -> None:
    """寫單一 cleaned MD（UTF-8，強制 LF，檔尾單一換行）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline=NEWLINE) as f:
        f.write(content)


# ---------------------------------------------------------------------------
# [4.5] cleaned 目錄重建（人工已授權的敏感操作）
# ---------------------------------------------------------------------------
def assert_rebuild_target(version: str) -> Path:
    """斷言重建目標合法：必須是 CLEANED_DIR 的直接版本子目錄，且 CLEANED_DIR 位置正確。

    斷言失敗即中止，不得刪除任何檔案。範圍限定於 cleaned/<version>/，
    不動 cleaned/ 根目錄的 .gitkeep，也不動其他階段的目錄。
    """
    if CLEANED_DIR != PROJECT_ROOT / "data" / "processed" / "cleaned":
        raise RuntimeError(f"CLEANED_DIR 位置異常：{CLEANED_DIR}")
    if not version or not version.isascii() or "/" in version or "\\" in version:
        raise ValueError(f"version 不合法：{version!r}")
    return CLEANED_DIR / version


def rebuild_cleaned_dir(version_dir: Path) -> None:
    """清空 cleaned/<version>/ 並重建。呼叫前須先通過 assert_rebuild_target。"""
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# [4.6] 報告
# ---------------------------------------------------------------------------
def _md_cell(value) -> str:
    """Markdown 表格 cell：跳脫 pipe 與換行。"""
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_cleaning_report(path: Path, sources: dict, pages: list) -> None:
    """寫 reports/cleaning_report.md（人類閱讀用，覆蓋更新）。

    pages 每項為 (rel, log, body 或 None)，依處理順序排列。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []

    total = len(pages)
    outputs = [p for p in pages if p[2] is not None]
    skipped = [p for p in pages if p[1]["skip_reason"] is not None]
    errored = [p for p in pages if p[2] is None and p[1]["skip_reason"] is None]

    lines.append(f"# [4] 清理報告 — {sources['version']} / {sources['mod']}")
    lines.append("")
    lines.append("- 規則依「無圖片版本」的抽取結果校準；定義與決策見 `docs/03_clean.md`")
    lines.append("- 前提：配方以圖片呈現，本批只清圖片被拿掉後留下的標籤空殼")
    lines.append("")

    # 1. 統計
    lines.append("## 1. 統計")
    lines.append("")
    lines.append(f"- 輸入頁數（extracted JSON）：{total}")
    lines.append(f"- 輸出頁數（cleaned MD）：{len(outputs)}")
    lines.append(f"- 跳過頁數：{len(skipped)}")
    for reason, label in [
        ("missing_title_or_source", "title 或 source 為空"),
        ("empty_body", "規則處理後 body 為空"),
    ]:
        n = sum(1 for p in pages if p[1]["skip_reason"] == reason)
        lines.append(f"  - {label}：{n}")
    if errored:
        lines.append(f"- 例外（讀取或處理失敗，未輸出）：{len(errored)}")
    lines.append(
        f"- 對帳：輸出 {len(outputs)} + 跳過 {len(skipped)} + 例外 {len(errored)} "
        f"= {len(outputs) + len(skipped) + len(errored)}（輸入 {total}）"
    )
    lines.append("")

    # 2. 各規則命中
    lines.append("## 2. 各規則命中")
    lines.append("")
    r1_counts = {"A": 0, "B": 0, "C": 0}
    for _, log, _ in pages:
        if log["r1_type"] in r1_counts:
            r1_counts[log["r1_type"]] += 1
    r4a_pages = sum(1 for _, log, _ in pages if log["labels_removed"])
    r4a_lines = sum(len(log["labels_removed"]) for _, log, _ in pages)
    r4a_chars = sum(len(ln) for _, log, _ in pages for ln in log["labels_removed"])
    r4b_pages = sum(1 for _, log, _ in pages if log["r4b_seqs"])
    r4b_occ = sum(len(log["r4b_seqs"]) for _, log, _ in pages)
    r4b_chars = sum(sum(len(t) for t in seq) for _, log, _ in pages for seq in log["r4b_seqs"])
    lines.append(f"- R1 首行標題去重：A={r1_counts['A']} B={r1_counts['B']} C={r1_counts['C']}")
    lines.append(f"- R4a 整行標籤：{r4a_pages} 頁，{r4a_lines} 行，{r4a_chars} 字元")
    lines.append(f"- R4b 黏合尾端標籤：{r4b_pages} 頁，{r4b_occ} 處，{r4b_chars} 字元")
    lines.append(f"- R2 站名首行警告（未排除）：{sum(1 for _, log, _ in pages if log['site_name_not_excluded'])} 頁")
    level_totals = {}
    for _, log, _ in outputs:
        for level, n in log["heading_counts"].items():
            level_totals[level] = level_totals.get(level, 0) + n
    heading_pages = sum(1 for _, log, _ in outputs if log["heading_counts"])
    level_text = "、".join(f"{'#' * lv} {level_totals[lv]}" for lv in sorted(level_totals)) or "無"
    lines.append(f"- R6 標題層級正規化：{heading_pages} 頁含小標題；{level_text}")
    r7 = [(rel, h) for rel, log, _ in pages for h in log["empty_sections"]]
    lines.append(f"- R7 空章節移除：{len(r7)} 個")
    r8_pages = sum(1 for _, log, _ in outputs if log["recipes_added"])
    r8_total = sum(log["recipes_added"] for _, log, _ in outputs)
    lines.append(f"- R8 配方輸出：{r8_pages} 頁，{r8_total} 個配方")
    for rel, h in r7:
        lines.append(f"  - `{_md_cell(rel)}`：`{_md_cell(h)}`")
    lines.append("")

    # 3. 跳過頁清單（對帳用：輸出頁數 + 本表頁數 = 輸入頁數）
    lines.append("## 3. 跳過頁（契約排除，未輸出）")
    lines.append("")
    if skipped:
        lines.append("| 頁 | 原因 |")
        lines.append("| --- | --- |")
        for rel, log, _ in skipped:
            lines.append(f"| {_md_cell(rel)} | {log['skip_reason']} |")
    else:
        lines.append("（無）")
    lines.append("")

    # 4. 標籤刪除摘要
    lines.append("## 4. 標籤刪除摘要（R4a + R4b）")
    lines.append("")
    counts = {}
    for _, log, _ in pages:
        for lab in log["labels_removed"]:
            counts[lab] = counts.get(lab, 0) + 1
        for seq in log["r4b_seqs"]:
            for lab in seq:
                counts[lab] = counts.get(lab, 0) + 1
    generic_total = sum(v for k, v in counts.items() if k in GENERIC_LABELS)
    method_total = sum(v for k, v in counts.items() if k in METHOD_LABELS)
    lines.append(f"- 通用標籤（Recipe／Recipes／Crafting／Crafting (Shapeless)）：{generic_total}")
    for lab in sorted(GENERIC_LABELS, key=lambda x: (-counts.get(x, 0), x)):
        if counts.get(lab):
            lines.append(f"  - `{lab}`：{counts[lab]}")
    lines.append(f"- 製法標籤（其餘五個）：{method_total}")
    for lab in sorted(METHOD_LABELS, key=lambda x: (-counts.get(x, 0), x)):
        if counts.get(lab):
            lines.append(f"  - `{lab}`：{counts[lab]}")
    lines.append("")

    # 5. 含圖片說明區塊的頁
    lines.append("## 5. 含圖片說明區塊的頁（刪除的標籤）")
    lines.append("")
    block_pages = [(rel, log) for rel, log, _ in pages
                   if log["labels_removed"] or log["r4b_seqs"]]
    if block_pages:
        lines.append("| 頁 | 製法標籤 | 通用標籤 |")
        lines.append("| --- | --- | --- |")
        for rel, log in block_pages:
            method_labels = [lab for lab in log["labels_removed"] if lab in METHOD_LABELS]
            method_labels += [lab for seq in log["r4b_seqs"] for lab in seq if lab in METHOD_LABELS]
            generic_labels = [lab for lab in log["labels_removed"] if lab in GENERIC_LABELS]
            generic_labels += [lab for seq in log["r4b_seqs"] for lab in seq if lab in GENERIC_LABELS]
            method_cell = ", ".join(sorted(set(method_labels))) if method_labels else "—"
            generic_cell = ", ".join(sorted(set(generic_labels))) if generic_labels else "—"
            lines.append(f"| {_md_cell(rel)} | {_md_cell(method_cell)} | {_md_cell(generic_cell)} |")
    else:
        lines.append("（無）")
    lines.append("")

    # 6. 孤立 `-` 計數
    dash_pages = sum(1 for _, log, _ in pages if log["orphan_dashes"])
    dash_total = sum(log["orphan_dashes"] for _, log, _ in pages)
    lines.append("## 6. 孤立 `-`（未處理，僅計數）")
    lines.append("")
    lines.append(f"- 頁數：{dash_pages}，處數：{dash_total}")
    lines.append("- 依人工裁定不還原編號、不接回內容；保留原樣於輸出")
    if dash_pages:
        lines.append("")
        lines.append("| 頁 | 處數 |")
        lines.append("| --- | --- |")
        for rel, log, _ in pages:
            if log["orphan_dashes"]:
                lines.append(f"| {_md_cell(rel)} | {log['orphan_dashes']} |")
    lines.append("")

    # 7. 字元數變化最大前 10 頁
    lines.append("## 7. 清理前後字元數變化最大前 10 頁")
    lines.append("")
    deltas = sorted(
        ((log["chars_before"] - log["chars_after"], rel, log)
         for rel, log, _ in outputs),
        key=lambda x: -x[0],
    )
    if deltas:
        lines.append("| 頁 | 清理前 | 清理後 | Δ |")
        lines.append("| --- | --- | --- | --- |")
        for delta, rel, log in deltas[:10]:
            lines.append(
                f"| {_md_cell(rel)} | {log['chars_before']} | {log['chars_after']} | {delta} |"
            )
    lines.append("")

    # 8. 不足 200 字元的頁
    lines.append("## 8. 內容不足 200 字元的頁（仍輸出，標示）")
    lines.append("")
    short_pages = [(rel, log) for rel, log, _ in outputs if log["short_body"]]
    if short_pages:
        lines.append("| 頁 | 清理後字元數 |")
        lines.append("| --- | --- |")
        for rel, log in short_pages:
            lines.append(f"| {_md_cell(rel)} | {log['chars_after']} |")
    else:
        lines.append("（無）")
    lines.append("")

    # 9. 疑似新標籤
    lines.append("## 9. 疑似新標籤（僅列出，不自動刪）")
    lines.append("")
    lines.append("條件：長度 ≤ 40、不在白名單、不以 `- ` 開頭，且與白名單行相鄰。")
    lines.append("供人工判斷是否擴充白名單；現行規則一律保留這些行。")
    lines.append("")
    suspects = []
    for rel, log, _ in pages:
        for s in log.get("suspect_lines", []):
            suspects.append((rel, s))
    lines.append(f"- 命中數：{len(suspects)}")
    for rel, s in suspects[:40]:
        lines.append(f"  - `{_md_cell(rel)}`：`{_md_cell(s)}`")
    if len(suspects) > 40:
        lines.append(f"  - …其餘 {len(suspects) - 40} 筆省略")
    lines.append("")

    # 10. 空欄位
    lines.append("## 10. title 或 source 為空的頁（未輸出）")
    lines.append("")
    empty_pages = [(rel, log) for rel, log, _ in pages
                   if log["title_empty"] or log["source_empty"]]
    if empty_pages:
        lines.append("| 頁 | title 空 | source 空 |")
        lines.append("| --- | --- | --- |")
        for rel, log in empty_pages:
            lines.append(f"| {_md_cell(rel)} | {log['title_empty']} | {log['source_empty']} |")
    else:
        lines.append("（無）")
    lines.append("")

    # 11. Known Limitations 與 Risks
    lines.append("## 11. Known Limitations 與 Risks")
    lines.append("")
    lines.append("**Limitations（只記錄，不處理）**")
    lines.append("")
    lines.append("- 小標題來自 [3] 的標題對應（docs/02_extract.md）；[3] 對應不到的標題不會出現在輸出")
    lines.append("- 無段落空行（trafilatura json 模式不保留）")
    lines.append("- 配方材料資訊在目前資料中缺失（材料在原網頁的圖片／屬性裡，[3] 未抽出）")
    lines.append("- 孤立 `-` 未處理（見第 6 節）")
    lines.append("- 句子之間黏合（如 `...affected.Each continuous line...`）未處理")
    lines.append("- 相鄰表格（upgrade_cards 多段表格無空行相鄰，渲染時合併）未處理")
    lines.append("- 製法標籤刪除後，製法資訊僅存在於本報告與 [3] 的 extracted JSON")
    lines.append("")
    lines.append("**Risks**")
    lines.append("")
    lines.append("- 標籤白名單與 R4b 的前提皆依本批資料校準；新頁或站方改版需重驗")
    lines.append("- 跳轉頁不在本階段排除；由抽取報告列出候選，人工複核後再決定")
    lines.append("- R1-B 前綴切割與 R4b 尾端切除會改變 `text` 的字元內容；`title`／`source` 欄位全程不動")
    lines.append("")

    # 附錄：安全網與異常警告
    warnings = []
    for rel, log, _ in pages:
        if log["site_name_not_excluded"]:
            warnings.append((rel, "首行為站名（可能是跳轉頁，見抽取報告的跳轉頁候選），已輸出，請人工查驗"))
        for note in log["notes"]:
            warnings.append((rel, note))
        if log.get("error"):
            warnings.append((rel, log["error"]))
    if warnings:
        lines.append("## 附錄：警告與例外")
        lines.append("")
        lines.append("| 頁 | 訊息 |")
        lines.append("| --- | --- |")
        for rel, msg in warnings:
            lines.append(f"| {_md_cell(rel)} | {_md_cell(msg)} |")
        lines.append("")

    path.write_text("\n".join(lines) + NEWLINE, encoding="utf-8", newline=NEWLINE)


# ---------------------------------------------------------------------------
# 編排
# ---------------------------------------------------------------------------
def _error_log(message: str, chars_before: int = 0) -> dict:
    """組例外頁的判定紀錄（讀取或處理失敗；未輸出，且非契約定義的跳過）。"""
    return {
        "title": "",
        "source": "",
        "title_empty": False,
        "source_empty": False,
        "redirect": False,
        "site_name_not_excluded": False,
        "r1_type": None,
        "r1_note": "",
        "labels_removed": [],
        "r4b_seqs": [],
        "suspect_lines": [],
        "notes": [],
        "orphan_dashes": 0,
        "heading_counts": {},
        "empty_sections": [],
        "recipes_added": 0,
        "chars_before": chars_before,
        "chars_after": 0,
        "short_body": False,
        "skip_reason": None,
        "error": message,
    }


def main() -> int:
    """[4] 主流程。回傳 exit code：0 成功；1 表輸入或設定層級錯誤。"""
    sources = load_sources(SOURCES_PATH)
    version = sources["version"]
    print(f"[1] sources.json：version={version} mod={sources['mod']}")

    try:
        page_paths = collect_pages(version)
    except FileNotFoundError as exc:
        print(f"[4] 中止：{exc}", file=sys.stderr)
        return 1

    if not page_paths:
        print(f"[4] 中止：{version} 下無 extracted JSON，不刪除現有輸出", file=sys.stderr)
        return 1

    print(f"[3] extracted JSON：{len(page_paths)} 頁")

    # 全部先在記憶體處理；確認沒有系統性失敗，才清空並寫入（人工授權的敏感操作）
    results = []          # (rel, log, body 或 None)
    n_errors = 0
    for path in page_paths:
        rel = path.relative_to(EXTRACTED_DIR / version).as_posix()
        try:
            with path.open(encoding="utf-8") as f:
                record = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            results.append((rel, _error_log(f"讀取失敗：{type(exc).__name__}: {exc}"), None))
            n_errors += 1
            print(f"  ERR  {rel} -> {exc}", file=sys.stderr)
            continue

        try:
            body, log = process_page(record)
        except Exception as exc:                    # noqa: BLE001 - 逐頁隔離，不中斷全批
            results.append((rel, _error_log(
                f"處理例外：{type(exc).__name__}: {exc}", len(record.get("text") or "")), None))
            n_errors += 1
            print(f"  ERR  {rel} -> {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        results.append((rel, log, body))
        if body is None:
            print(f"  SKIP {rel} -> {log['skip_reason']}")
        else:
            print(f"  OK   {rel}")

    # 系統性失敗：完全沒有產出任何頁 → 中止，不清空
    produced = [r for r in results if r[2] is not None]
    if not produced:
        print("[4] 中止：無任何頁產出，不刪除現有輸出", file=sys.stderr)
        return 1

    # 清空並重建 cleaned/<version>/（範圍限定，先做路徑斷言）
    version_dir = assert_rebuild_target(version)
    rebuild_cleaned_dir(version_dir)
    print(f"[4] 已重建 {version_dir.relative_to(PROJECT_ROOT)}")

    for path, (rel, log, body) in zip(page_paths, results):
        if body is None:
            continue
        write_md(cleaned_output_path(path), build_cleaned_md(log["title"], log["source"], body))

    write_cleaning_report(REPORT_PATH, sources, results)

    n_out = len(produced)
    n_skip = sum(1 for _, log, _ in results if log["skip_reason"] is not None)
    print(f"\n[4] 結果：output={n_out} skipped={n_skip} errors={n_errors}")
    print(f"     合計 {n_out + n_skip + n_errors} / {len(page_paths)} 頁")
    print(f"     報告：{REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 1 if n_errors else 0


if __name__ == "__main__":
    sys.exit(main())
