"""[2] 抓取 raw HTML。

職責：只做網路 I/O 與路徑三元素解析；不做 HTML->MD 轉換，也不解析導覽 DOM。
URL 真值來源：sitemap.xml（robust 探測，見 docs/adr/ADR-001-sitemap-as-url-source.md）。

設計原則：
- 模組化：每個函式單一職責，main() 只做編排。
- 低語法糖：不使用 walrus、dataclass、裝飾器；顯式迴圈與條件。
- 失敗語意：sitemap 不可用 -> fail-fast；單頁失敗 -> 記錄不中斷。
"""

from __future__ import annotations

import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from slugify import slugify

# ---------------------------------------------------------------------------
# 常數：以本檔位置定位專案根，不依賴 cwd
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = PROJECT_ROOT / "sources.json"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
URLSET_TAG = f"{SITEMAP_NS}urlset"
SITEMAPINDEX_TAG = f"{SITEMAP_NS}sitemapindex"

# 無 Sitemap: 宣告時依序嘗試的慣例路徑（不寫死當前站台的 sitemap 位置）
FALLBACK_SITEMAP_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
)

ENTRY_PAGE_SLUG = "index"          # 入口頁：path 恰為 /{version}/index
DEFAULT_CHAPTER = "other"          # 無 chapter 的頁（路徑只有一段）
FETCH_INTERVAL_SECONDS = 0.5       # 逐頁抓取間隔（契約固定 0.5 秒）
REQUEST_TIMEOUT_SECONDS = 30
HTTP_OK = 200


# ---------------------------------------------------------------------------
# [1] 載入知識來源入口
# ---------------------------------------------------------------------------
def load_sources(path: Path) -> dict:
    """讀 sources.json，只取 version / mod / entry_url 三欄。

    依 AGENTS.md §7，sources.json 為人工維護，本階段不修改、不補值；
    缺欄位即視為格式不符，直接拒絕。
    """
    with path.open(encoding="utf-8") as f:
        sources = json.load(f)

    required = ("version", "mod", "entry_url")
    missing = [k for k in required if not sources.get(k)]
    if missing:
        raise ValueError(f"sources.json 缺少必要欄位：{missing}（不自動補值）")
    return sources


def site_root_from_entry(entry_url: str) -> str:
    """由 entry_url 推導站台根（scheme + host），用來定位 robots.txt 與 sitemap。

    entry_url 本身不抓取，僅取站台根與版本資訊（AGENTS.md §6 [1]）。
    """
    parsed = urlparse(entry_url)
    return f"{parsed.scheme}://{parsed.netloc}"


# ---------------------------------------------------------------------------
# [2] sitemap 探測（robust：robots.txt 宣告優先，慣例路徑其次）
# ---------------------------------------------------------------------------
def _is_sitemap_xml(status_code: int, body: bytes) -> bool:
    """判定標準：HTTP 200 且 body 根節點是 <urlset> 或 <sitemapindex>。"""
    if status_code != HTTP_OK:
        return False
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return False
    return root.tag in (URLSET_TAG, SITEMAPINDEX_TAG)


def sitemap_urls_from_robots(site_root: str, session: requests.Session) -> list:
    """解析 robots.txt 的所有 'Sitemap:' 行；無宣告或抓取失敗回空 list。"""
    robots_url = site_root + "/robots.txt"
    try:
        resp = session.get(robots_url, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException:
        return []

    if resp.status_code != HTTP_OK:
        return []

    found = []
    for line in resp.text.splitlines():
        # Sitemap 協定：行首大小寫不敏感的 'Sitemap:'，其後為 URL
        stripped = line.strip()
        if stripped[:9].lower() == "sitemap:":
            candidate = stripped[9:].strip()
            if candidate:
                found.append(candidate)
    return found


def discover_sitemap(site_root: str, session: requests.Session) -> str:
    """回傳可用的 sitemap URL；找不到 -> RuntimeError（fail-fast，不回退導覽爬取）。

    順序：robots.txt 的 Sitemap: 宣告 -> 慣例路徑 -> 放棄。
    多個宣告時取第一個可解析者。
    """
    # (a) robots.txt 宣告
    for declared in sitemap_urls_from_robots(site_root, session):
        try:
            resp = session.get(declared, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException:
            continue
        if _is_sitemap_xml(resp.status_code, resp.content):
            return declared

    # (b) 慣例路徑
    for relative in FALLBACK_SITEMAP_PATHS:
        candidate = site_root + relative
        try:
            resp = session.get(candidate, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException:
            continue
        if _is_sitemap_xml(resp.status_code, resp.content):
            return candidate

    # (c) 都失敗：明確報錯，不 fallback 到任何 DOM 爬取
    raise RuntimeError(
        f"此站台無可用 sitemap（嘗試過 robots.txt 宣告與 {FALLBACK_SITEMAP_PATHS}）。"
        "不回退導覽爬取——請人工確認站台結構。"
    )


# ---------------------------------------------------------------------------
# [3] sitemap 解析（<sitemapindex> 遞迴，<urlset> 直接取 <loc>）
# ---------------------------------------------------------------------------
def extract_locs_from_sitemap(sitemap_url: str, session: requests.Session) -> list:
    """解析單一 sitemap：<urlset> 取所有 <loc>；<sitemapindex> 遞迴合併子 sitemap。"""
    resp = session.get(sitemap_url, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code != HTTP_OK:
        raise RuntimeError(f"sitemap 抓取失敗：{sitemap_url} (HTTP {resp.status_code})")

    root = ET.fromstring(resp.content)
    if root.tag == URLSET_TAG:
        return [el.text.strip() for el in root.iter(f"{SITEMAP_NS}loc") if el.text]

    if root.tag == SITEMAPINDEX_TAG:
        # 索引式 sitemap：每個 <loc> 指向子 sitemap，逐一抓取後合併
        child_urls = [el.text.strip() for el in root.iter(f"{SITEMAP_NS}loc") if el.text]
        all_locs = []
        for child in child_urls:
            all_locs.extend(extract_locs_from_sitemap(child, session))
        return all_locs

    raise RuntimeError(f"未預期的 sitemap 根節點：{root.tag}")


# ---------------------------------------------------------------------------
# [4] 版本過濾（嚴格前綴比對，避免 1.21.10 誤判）
# ---------------------------------------------------------------------------
def filter_version_urls(urls: list, version: str) -> list:
    """過濾指定版本並排除入口頁。

    - 版本比對用 path.startswith(f"/{version}/")：帶尾斜槓可避免 '1.21.1'
      命中 '1.21.10' 這類前綋誤判（不可用 '1.21.1' in url）。
    - 排除入口頁：path == f"/{version}/index"（入口僅推導站台根與版本，不抓取）。
    """
    prefix = f"/{version}/"
    entry_path = f"/{version}/{ENTRY_PAGE_SLUG}"

    kept = []
    for url in urls:
        path = urlparse(url).path
        if not path.startswith(prefix):
            continue
        if path == entry_path:
            continue
        kept.append(url)
    return kept


# ---------------------------------------------------------------------------
# [5] 路徑三元素解析（[2] 是唯一計算來源，下游一律從路徑讀）
# ---------------------------------------------------------------------------
def parse_path_elements(url: str, version: str) -> dict:
    """解析 chapter 與 page_slug；mod_slug 另由 sources.json 的 mod 產生。

    規則（ARCHITECTURE.md §4 [2]）：
    - 去掉 /{version}/ 前綴後，1 段 -> chapter='other'，page_slug=該段
    - >=2 段 -> chapter=倒數第二段，page_slug=最後一段
    - URL 本身已是 slug，不另行 slug 化（只用在路徑與命名）
    """
    prefix = f"/{version}/"
    path = urlparse(url).path
    relative = path[len(prefix):] if path.startswith(prefix) else path.lstrip("/")

    segments = [seg for seg in relative.split("/") if seg]

    if len(segments) == 1:
        chapter, page_slug = DEFAULT_CHAPTER, segments[0]
    elif len(segments) >= 2:
        chapter, page_slug = segments[-2], segments[-1]
    else:
        # 空路徑（理論上已被 filter_version_urls 濾掉，防禦性處理）
        chapter, page_slug = DEFAULT_CHAPTER, ""

    return {"chapter": chapter, "page_slug": page_slug}


def raw_html_path(version: str, mod_slug: str, chapter: str, page_slug: str) -> Path:
    """組 data/raw/<version>/<mod_slug>/<chapter>/<page_slug>.html 的完整路徑。"""
    return RAW_DIR / version / mod_slug / chapter / f"{page_slug}.html"


# ---------------------------------------------------------------------------
# [6] 逐頁抓取（間隔 0.5 秒；單頁失敗記錄不中斷）
# ---------------------------------------------------------------------------
def fetch_page(url: str, session: requests.Session) -> tuple:
    """抓單頁 raw HTML。回傳 (http_status, body_or_None)。

    不重試（契約 [2] 失敗處理）：例外或非 2xx 都記錄，交給人工查驗後重跑。
    """
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        # 連線錯誤、逾時等：狀態碼未知，以 None 表示
        return None, None, str(exc)

    if resp.status_code != HTTP_OK:
        return resp.status_code, None, f"HTTP {resp.status_code}"
    return resp.status_code, resp.text, ""


def fetch_all(urls: list, session: requests.Session, log_file,
              version: str, mod_slug: str) -> list:
    """逐頁抓取，每頁間隔 FETCH_INTERVAL_SECONDS；回傳 manifest entries。

    version / mod_slug 明確以參數傳入，不使用模組級全域狀態（保持可獨立測試）。
    """
    entries = []
    for index, url in enumerate(urls, start=1):
        # 間隔放在抓取「之前」：首頁不等待，其餘每頁等待 0.5 秒
        if index > 1:
            time.sleep(FETCH_INTERVAL_SECONDS)

        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status, body, error = fetch_page(url, session)

        if error:
            log_file.write(f"[{index:>3}/{len(urls)}] FAIL {url} -> {error}\n")
            entries.append({
                "url": url,
                "chapter": None,
                "page_slug": None,
                "local_path": None,
                "http_status": status,
                "fetched_at": ts,
                "error": error,
            })
            continue

        # 成功：解析路徑三元素並寫檔
        elements = parse_path_elements(url, version)
        out_path = raw_html_path(version, mod_slug, elements["chapter"], elements["page_slug"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")

        log_file.write(f"[{index:>3}/{len(urls)}] OK   {url} -> {out_path.relative_to(PROJECT_ROOT)}\n")
        entries.append({
            "url": url,
            "chapter": elements["chapter"],
            "page_slug": elements["page_slug"],
            "local_path": str(out_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "http_status": status,
            "fetched_at": ts,
        })
    return entries


# ---------------------------------------------------------------------------
# [7] manifest 寫入（覆寫式，單次記錄）
# ---------------------------------------------------------------------------
def write_manifest(path: Path, sources: dict, mod_slug: str, entries: list) -> None:
    """寫 data/raw/_manifest.json；整份覆寫，不做 history（AGENTS.md §3.3）。"""
    manifest = {
        "version": sources["version"],
        "mod": sources["mod"],        # 原名，與 mod_slug 並存以便追溯
        "mod_slug": mod_slug,
        "source": "sitemap",          # URL 發現來源（ADR-001）
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "urls": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 編排
# ---------------------------------------------------------------------------
def main() -> int:
    """[2] 主流程。回傳 exit code：0 成功；1 表設定或 sitemap 層級錯誤。"""
    sources = load_sources(SOURCES_PATH)
    version = sources["version"]
    mod_slug = slugify(sources["mod"])   # mod 原名 -> mod_slug，只用於路徑與命名
    site_root = site_root_from_entry(sources["entry_url"])

    print(f"version      : {version}")
    print(f"mod          : {sources['mod']}")
    print(f"mod_slug     : {mod_slug}")
    print(f"site_root    : {site_root}")

    session = requests.Session()
    session.headers.update({"User-Agent": "Minecraft-RAG/0.1 (pipeline stage [2])"})

    # 探測 sitemap：fail-fast，不回退導覽爬取
    sitemap_url = discover_sitemap(site_root, session)
    print(f"sitemap      : {sitemap_url}")

    # 解析 + 版本過濾
    all_locs = extract_locs_from_sitemap(sitemap_url, session)
    print(f"sitemap locs : {len(all_locs)} (全部版本)")
    target_urls = filter_version_urls(all_locs, version)
    print(f"version urls : {len(target_urls)} (排除入口頁 /{version}/index)")

    if not target_urls:
        print("抓到 0 頁：版本過濾後無任何 URL，停止後續 [3]", file=sys.stderr)
        return 1

    # 逐頁抓取（記錄間隔與成敗，供驗證）
    with open(RAW_DIR / "_fetch_log.txt", "w", encoding="utf-8") as log_file:
        log_file.write(f"# fetch log @ {datetime.now(timezone.utc).isoformat()}\n")
        log_file.write(f"# sitemap: {sitemap_url}\n")
        entries = fetch_all(target_urls, session, log_file, version, mod_slug)

    # manifest（覆寫）
    write_manifest(RAW_DIR / "_manifest.json", sources, mod_slug, entries)

    ok = sum(1 for e in entries if e["local_path"] is not None)
    failed = [e for e in entries if e["local_path"] is None]
    print(f"fetched      : {ok} ok / {len(failed)} failed")
    for e in failed:
        print(f"  FAIL {e['url']} -> {e.get('error')}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
