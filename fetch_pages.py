"""受控資料擷取器：下載 AE2 官方 1.21.1 指南指定頁面並轉存為乾淨 Markdown。

此工具不是全站爬蟲。它只會依 sources.json 內的 URL 依序下載、解析與轉檔；
不會發現、追蹤或自動下載頁面內的其他連結。

職責：
    - 讀取 sources.json
    - 檢查網域是否屬於 guide.appliedenergistics.org
    - 以 requests 下載指定 URL（合理 User-Agent 與 timeout）
    - 原始 HTML 存至 data/raw/
    - 以 BeautifulSoup 提取主要文章內容並轉成 Markdown，存至 data/processed/
    - 每份 Markdown 開頭寫入 YAML metadata
    - 單頁失敗不影響其他頁處理，結束時統計成功 / 失敗 / 略過
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

# -------------------------------------------------------------------- 常數
ALLOWED_DOMAIN = "guide.appliedenergistics.org"
USER_AGENT = (
    "Minecraft-AE2-RAG-Assistant/0.1 (educational; reading official guide; "
    "+contact via project README)"
)
REQUEST_TIMEOUT = 25  # 秒

YAML_KEYS = (
    "title",
    "source_url",
    "minecraft_version",
    "mod",
    "source_type",
    "fetched_at",
)

# 這類元素通常是導覽、頁尾或側欄，不屬於文章主體，應予排除
EXCLUDED_TAG_NAMES = {"nav", "footer", "aside", "script", "style"}

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCES_PATH = PROJECT_ROOT / "sources.json"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# 檔名安全化：保留 slug 風格的英數字與連字號 / 底線
_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")
# -------------------------------------------------------------------- 工具函式
def load_sources(path: Path) -> list[dict[str, Any]]:
    """讀取 sources.json，回傳來源清單（依出現順序）。"""
    if not path.is_file():
        raise FileNotFoundError(f"找不到資料來源清單：{path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"{path} 中缺少非空的 sources 清單")
    return sources


def resolve_title(source: dict[str, Any], soup: BeautifulSoup, raw_html: str) -> str:
    """決定標題：source 的 title 欄位 > HTML <title> > 空白字串。"""
    title = str(source.get("title", "")).strip()
    if title:
        return title
    tag_title = soup.find("title") if soup else None
    if tag_title and tag_title.string and tag_title.string.strip():
        return tag_title.string.strip()
    match_title = re.search(
        r"<title[^>]*>(.*?)</title>", raw_html, flags=re.IGNORECASE | re.DOTALL
    )
    if match_title:
        return match_title.group(1).strip()
    return ""


def derive_slug(url: str) -> str:
    """從 URL 取得檔案基底名（不含 .html），避免重複覆寫並保持可重複。"""
    path_part = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if not path_part:
        return "index"
    name = path_part.rsplit("/", 1)[-1]
    if not name or name.lower() in {"index", "index.html"}:
        return path_part.rsplit("/", 1)[-1] if "/" in path_part else "index"
    return name


def derive_safe_path(url: str, dest_dir: Path) -> Path:
    """依 URL 產生存檔路徑：data/<dest>/<主機>/<slug>.md。

    以主機與 slug 組成份層目錄，避免不同的 URL 覆寫同一檔案。
    """
    host = "unknown"
    if "://" in url:
        host = url.split("://", 1)[1].split("/", 1)[0]
    slug = derive_slug(url)[:80] if url else ""
    slug = _SAFE_FILENAME_RE.sub("-", slug).strip("-")
    if not slug:
        slug = "index"
    return dest_dir / host / f"{slug}.md"


def find_main_content(soup: BeautifulSoup) -> Tag | None:
    """嘗試定位主要文章內容節點；無法判斷時回傳 None（交由呼叫端處理）。"""
    candidates: list[Tag] = []

    if soup.main is not None:
        candidates.append(soup.main)

    for node in soup.find_all(["div", "section", "article"]):
        attr_ids = node.get("id") or ""
        classes = " ".join(node.get("class") or [])
        token = f"{attr_ids} {classes}".lower()
        if any(k in token for k in ("article-content", "content-area", "main-content", "entry-content")):
            candidates.append(node)
            break

    if soup.article is not None:
        candidates.append(soup.article)

    if soup.body is not None:
        candidates.append(soup.body)

    scored = [(count_text_units(c), c) for c in candidates if c is not None]
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


def count_text_units(node: Tag) -> int:
    """粗略估算節點文字量，避免以空白長度誤判主要區塊。"""
    text = " ".join(node.get_text(separator=" ", strip=True).split())
    if "©" in text or "copyright" in text.lower():
        # 含版權的區塊通常較不可能是主文；仍回傳長度但伴隨較小權重
        return len(text) // 2
    return len(text)
# -------------------------------------------------------------------- Markdown 轉換
_BLOCK_NAMES = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "pre", "table", "blockquote", "hr",
}


def render_inline(node: Tag) -> str:
    """把節點內的內文節點（含連結、粗斜體、行內 code）轉成單一 Markdown 字串。"""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name == "br":
            parts.append("  \n")
        elif name == "code":
            parts.append("`" + child.get_text("", strip=True) + "`")
        elif name in ("strong", "b"):
            inner = render_inline(child)
            parts.append(f"**{inner}**" if inner.strip() else "")
        elif name in ("em", "i"):
            inner = render_inline(child)
            parts.append(f"*{inner}*" if inner.strip() else "")
        elif name == "a":
            href = child.get("href") or ""
            inner = render_inline(child).strip()
            if href and inner:
                parts.append(f"[{inner}]({href})")
            else:
                parts.append(inner)
        elif name == "img":
            src = child.get("src") or ""
            alt = child.get("alt") or ""
            parts.append(f"![{alt}]({src})" if src else alt)
        else:
            parts.append(render_inline(child))
    return "".join(parts)


def render_children_html(node: Tag) -> str:
    """完整 HTML 節點所用的內文 render 輔助（配合 render_block 於需要處）。"""
    return render(node)


def render(node: Tag) -> str:
    """通用 render：若是容器節點以 block 方式輸出，否則回傳 inline。"""
    if not isinstance(node, Tag):
        return "".join(str(c) for c in node.children)
    if node.name.lower() in _BLOCK_NAMES:
        return render_block(node)
    return render_inline(node)


def render_list(node: Tag, ordered: bool, depth: int) -> list[str]:
    """把 ul/ol 與其巢狀子清單轉成 Markdown 列表。"""
    lines: list[str] = []
    items = [c for c in node.children if isinstance(c, Tag) and c.name.lower() == "li"]
    marker_style = "ordered"
    counter = 0
    for li in items:
        counter += 1 if ordered else 0
        indent = "    " * depth
        marker = f"{counter}. " if ordered else "- "
        text = render_inline(li).strip()
        if text:
            lines.append(indent + marker + text)
        for child in li.children:
            if isinstance(child, Tag) and child.name.lower() in ("ul", "ol"):
                lines.extend(render_list(child, child.name.lower() == "ol", depth + 1))
    return lines


def render_block(node: Tag) -> str:
    """把單一 block 層級元素轉成對應 Markdown 區塊字串。"""
    if not isinstance(node, Tag):
        return ""
    name = node.name.lower()
    if name in EXCLUDED_TAG_NAMES:
        return ""

    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(name[1])
        text = render_inline(node).strip()
        return f"{'#' * level} {text}\n\n" if text else ""

    if name == "p":
        text = render_inline(node).strip()
        return f"{text}\n\n" if text else ""

    if name == "ul":
        return "\n".join(render_list(node, False, 0)) + "\n\n"
    if name == "ol":
        return "\n".join(render_list(node, True, 0)) + "\n\n"

    if name == "pre":
        code = node.get_text("\n", strip=False).strip("\n")
        return f"```\n{code}\n```\n\n"

    if name == "blockquote":
        inner = render_children(node)
        quoted = "\n".join(f"> {ln}" for ln in inner.split("\n") if ln.strip())
        return f"{quoted}\n\n" if quoted.strip() else ""

    if name == "table":
        return render_table(node)

    if name == "hr":
        return "---\n\n"

    # 其他容器：遞迴 render 子 block
    return render_block_children(node)


def render_block_children(parent: Tag) -> str:
    """把容器節點內的所有 block / inline 子元素串接成 Markdown。"""
    out: list[str] = []
    for child in parent.children:
        if isinstance(child, str):
            text = " ".join(child.split())
            if text:
                out.append(text)
            continue
        if not isinstance(child, Tag):
            continue
        if child.name.lower() in EXCLUDED_TAG_NAMES:
            continue
        if child.name.lower() in _BLOCK_NAMES:
            out.append(render_block(child))
        else:
            text = render_inline(child).strip()
            if text:
                out.append(text + "\n\n")
    return "".join(out)


def render_table(node: Tag) -> str:
    """把 <table> 轉成簡易 Markdown 表格（第一列視為表頭）。"""
    rows: list[list[str]] = []
    for tr in node.find_all("tr"):
        cells = [render_inline(c).strip() for c in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    out: list[str] = ["| " + " | ".join(rows[0]) + " |"]
    out.append("| " + " | ".join("---" for _ in rows[0]) + " |")
    for row in rows[1:]:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out) + "\n\n"


def to_markdown(soup: BeautifulSoup) -> str:
    """從已取出的主文節點序列化為 Markdown 正文。"""
    main = find_main_content(soup)
    if main is None:
        # 找不到明確主文時，對全部 body 內內容做防呆擷取
        body = soup.body
        if body is None:
            return ""
        main = body
    # 於副本中移除導覽類元素，避免寫入導覽列
    for bad in list(main.find_all(EXCLUDED_TAG_NAMES)):
        bad.decompose()
    return render_block(main).strip() + "\n"
# -------------------------------------------------------------------- 下載與檔案
def is_allowed_url(url: str) -> bool:
    """僅允許 ALLOWED_DOMAIN；其他網域一律拒絕。"""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
    except Exception:  # noqa: BLE001 - 網址格式錯誤一律拒絕
        return False
    return (parsed.scheme in ("http", "https")) and parsed.netloc == ALLOWED_DOMAIN


def fetch_page(url: str) -> str:
    """使用 requests 下載指定 URL，成功回傳 HTML 文字；失敗時拋出例外。"""
    if not is_allowed_url(url):
        raise ValueError(f"拒絕非 {ALLOWED_DOMAIN} 網域的網址：{url}")
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def save_raw(html: str, url: str) -> Path:
    """將原始 HTML 存至 data/raw/<host>/<slug>.html。"""
    target = derive_safe_path(url, RAW_DIR).with_suffix(".html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


def make_metadata(source: dict[str, Any], title: str) -> dict[str, str]:
    """產出與 README 規範一致的 YAML metadata。"""
    return {
        "title": title,
        "source_url": source.get("url", ""),
        "minecraft_version": str(source.get("minecraft_version", "")),
        "mod": str(source.get("mod", "")),
        "source_type": str(source.get("source_type", "")),
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def render_yaml(meta: dict[str, str]) -> str:
    """把 metadata dict 序列化為 Markdown 檔首的 YAML 前端區塊。"""
    lines = ["---"]
    for key in YAML_KEYS:
        value = meta.get(key, "")
        escaped = value.replace('"', '\\"')
        lines.append(f'{key}: "{escaped}"')
    lines.append("---\n")
    return "\n".join(lines)


def write_processed(markdown: str, meta: dict[str, str], url: str) -> Path:
    """將含 YAML 前端的 Markdown 存至 data/processed/。"""
    target = derive_safe_path(url, PROCESSED_DIR)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = render_yaml(meta) + markdown
    target.write_text(content, encoding="utf-8")
    return target


def process_source(source: dict[str, Any]) -> str:
    """處理單一來源：下載 → 存 raw → 轉 Markdown → 存 processed。傳回成功訊息。"""
    url = str(source.get("url", "")).strip()
    raw_rel = ""
    try:
        title = str(source.get("title", "")).strip()
        html = fetch_page(url)
        raw_path = save_raw(html, url)
        soup = BeautifulSoup(html, "html.parser")
        if not title:
            title = resolve_title(source, soup, html)
        markdown = to_markdown(soup)
        meta = make_metadata(source, title)
        proc_path = write_processed(markdown, meta, url)
        return f"OK      {url}\n        raw={raw_path}  processed={proc_path}"
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"下載失敗 {url}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 單頁失敗不影響其他頁
        raise RuntimeError(f"解析失敗 {url}: {exc}") from exc


def run_fetcher() -> int:
    """主流程：逐筆處理並統計成功 / 失敗 / 略過。"""
    sources = load_sources(SOURCES_PATH)
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []
    skipped: list[str] = []

    for source in sources:
        url = str(source.get("url", "")).strip()
        if not url:
            skipped.append("(缺少 url)")
            continue
        if not is_allowed_url(url):
            skipped.append(url)
            continue
        try:
            message = process_source(source)
            succeeded.append(url)
            print(message, flush=True)
        except RuntimeError as exc:
            failed.append((url, str(exc)))
            print(f"FAIL    {url}: {exc}", file=sys.stderr, flush=True)

    print("\n=== 擷取摘要 ===")
    print(f"成功 {len(succeeded)} 頁、失敗 {len(failed)} 頁、略過 {len(skipped)} 頁", flush=True)
    for url, reason in failed:
        print(f"  失敗 {url}：{reason}", flush=True)
    for url in skipped:
        print(f"  略過 {url}", flush=True)
    return 0 if not failed else 1


def main() -> int:
    """命令列進入點。"""
    try:
        return run_fetcher()
    except Exception as exc:  # noqa: BLE001
        print(f"結束失敗：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
