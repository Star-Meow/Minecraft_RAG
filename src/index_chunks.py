"""[7] 入庫（Index）。

職責：把 [5] 的 parents／children 與 [6] 的向量寫入 PostgreSQL + pgvector 的 rag.parents、rag.children
（docs/06_index.md）。

流程（main() 只編排，順序固定）：
  參數（--mode 必填、無預設）→ sources.json 的 version → 讀三份輸入並做入庫前驗證（check_inputs，
  失敗即結束，此時尚未讀 .env、尚未連線）→ 載入連線設定與 URL 斷言（D5-1）→ 連線、資料庫名稱斷言與
  擴充檢查 → 單一交易寫入 → 報告。

- 本程式不驗證自己寫入的結果；驗證由 verify_index.py（測試庫）與 audit_index.py（正式庫，唯讀）執行。
- 不載入任何模型或 tokenizer，不需 GPU。
- 所有 SQL 使用限定名稱（rag.*、public.vector、OPERATOR(public.<=>)），不更動連線的 search_path。
- 程式不刪除資料表、不清空資料表、不自動變更表結構；所有刪除都以 version 為範圍（D5）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import psycopg
from dotenv import load_dotenv
from pgvector import Vector
from pgvector.psycopg.vector import register_vector_info
from psycopg.conninfo import conninfo_to_dict
from psycopg.types import TypeInfo

# ---------------------------------------------------------------------------
# [7.0] 設定
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"
EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "processed" / "embeddings"
REPORTS_DIR = PROJECT_ROOT / "reports"
SOURCES_PATH = PROJECT_ROOT / "sources.json"
ENV_PATH = PROJECT_ROOT / ".env"
REPORT_PATH = REPORTS_DIR / "index_report.md"

EXPECTED_DB = "minecraft_rag"                    # D5-1：正式庫名稱，寫死
ALLOWED_HOSTS = ("127.0.0.1", "localhost")       # D5-1：只能從 URL 判斷
ALLOWED_CONNINFO_KEYS = ("host", "port", "dbname", "user", "password")
ENV_URL_KEY = "DATABASE_URL"
ENV_URL_TEST_KEY = "DATABASE_URL_TEST"

EMBEDDING_DIM = 1024
NORM_TOLERANCE = 1e-4                            # docs/05_embed.md §5 文件化的 norm 容差
MIN_PGVECTOR = (0, 8, 2)                         # D7
MODES = ("update", "rebuild")
CONNECT_TIMEOUT_SECONDS = 10

NEWLINE = "\n"
PARENT_COLS = ["parent_id", "text", "title", "source_url", "version", "mod", "chapter", "page",
               "section", "token_count"]
CHILD_COLS = ["chunk_id", "parent_id", "text", "title", "source_url", "version", "mod", "chapter",
              "page", "section", "token_count", "embedding", "model_name", "model_revision"]
# [5] children.jsonl 的 11 個原欄位（docs/04_chunk.md §1），向量檔原樣帶入
CHILD_FIELDS = ["chunk_id", "parent_id", "text", "title", "source_url", "version", "mod", "chapter",
                "page", "section", "token_count"]
EMBEDDING_FIELDS = CHILD_FIELDS + ["embedding_input", "embedding", "model_name", "model_revision"]
PARENT_STR_FIELDS = [c for c in PARENT_COLS if c != "token_count"]
CHILD_STR_FIELDS = [c for c in CHILD_FIELDS if c != "token_count"]
PROVENANCE_FIELDS = ["source_url", "title", "version", "mod", "chapter", "page", "section"]

MAX_ERRORS_PER_FILE = 20                         # 入庫前驗證每個檔案最多列出的錯誤數


# ---------------------------------------------------------------------------
# [7.1] 例外
# ---------------------------------------------------------------------------
class IndexingError(Exception):
    """[7] 的可預期失敗（結束碼 1）；訊息已不含密碼與完整 URL。"""


class InputError(IndexingError):
    """輸入檔缺失、無法解析，或入庫前驗證失敗。"""


class SettingsError(IndexingError):
    """連線設定缺失或不合規。"""


class TargetError(IndexingError):
    """D5-1 的 URL 斷言失敗。"""


class ConnectionFailed(IndexingError):
    """連線失敗（訊息已遮罩）。"""


class DatabaseAssertionError(IndexingError):
    """D5-1 的伺服器端斷言失敗。"""


class ExtensionError(IndexingError):
    """pgvector 擴充缺少、版本不足或位置不符（D7）。"""


class SchemaMismatch(IndexingError):
    """既有表結構與預期不符；不自動變更，須使用者人工處理。"""


class GuardError(IndexingError):
    """update／rebuild 的防呆中止。"""


class WriteError(IndexingError):
    """寫入流程的安全網失敗（交易會回滾）。"""


# ---------------------------------------------------------------------------
# [7.2] 輸入與入庫前驗證（純資料，不連線；C3、S1、S2）
# ---------------------------------------------------------------------------
def load_sources(path: Path) -> dict:
    """讀 sources.json；缺檔代表 [1] 未設定。"""
    if not path.is_file():
        raise InputError(f"找不到 {path.name}：[1] sources.json 不存在")
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise InputError(f"{path.name} 不是合法 JSON（{exc.msg}）") from None


def valid_version(version: Any) -> bool:
    """version 必須是非空 ASCII 字串，且不含路徑分隔字元或空白。"""
    return (isinstance(version, str) and bool(version) and version.isascii()
            and not any(ch in version for ch in "/\\ \t\r\n") and version not in (".", ".."))


def input_paths(version: str) -> tuple[Path, Path, Path]:
    """N1：由 version 組出三份輸入路徑（不從檔案內容推導 version）。"""
    return (CHUNKS_DIR / version / "parents.jsonl",
            CHUNKS_DIR / version / "children.jsonl",
            EMBEDDINGS_DIR / version / "children_embeddings.jsonl")


def read_jsonl(path: Path) -> list[dict]:
    """讀 JSONL；缺檔、空行、無法解析、非物件、空檔皆報錯。"""
    if not path.is_file():
        raise InputError(f"找不到輸入檔 {path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path.name}")
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                raise InputError(f"{path.name}:{lineno} 為空行")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InputError(f"{path.name}:{lineno} 不是合法 JSON（{exc.msg}）") from None
            if not isinstance(record, dict):
                raise InputError(f"{path.name}:{lineno} 不是 JSON 物件")
            rows.append(record)
    if not rows:
        raise InputError(f"{path.name} 無任何資料")
    return rows


def load_inputs(version: str) -> tuple[list[dict], list[dict], list[dict]]:
    """讀 parents、children 與向量檔（三份皆由 version 組出路徑）。"""
    if not valid_version(version):
        raise InputError(f"sources.json 的 version 不合法：{version!r}")
    parents_path, children_path, embeddings_path = input_paths(version)
    return read_jsonl(parents_path), read_jsonl(children_path), read_jsonl(embeddings_path)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_record_shape(rows: list[dict], fields: list[str], str_fields: list[str],
                        name: str, errors: list[str]) -> None:
    """欄位齊全、型別正確、字串非空且不含 NUL（PostgreSQL text 不可含 NUL）。"""
    count = 0
    for i, row in enumerate(rows, start=1):
        problems: list[str] = []
        missing = [k for k in fields if k not in row]
        if missing:
            problems.append(f"缺欄位 {missing}")
        else:
            for k in str_fields:
                v = row[k]
                if not isinstance(v, str):
                    problems.append(f"{k} 不是字串")
                elif v == "":
                    problems.append(f"{k} 為空")
                elif "\x00" in v:
                    problems.append(f"{k} 含 NUL 字元")
            if not _is_int(row["token_count"]) or row["token_count"] <= 0:
                problems.append("token_count 不是正整數")
        if problems:
            count += 1
            if count <= MAX_ERRORS_PER_FILE:
                errors.append(f"{name} 第 {i} 筆：" + "；".join(problems))
    if count > MAX_ERRORS_PER_FILE:
        errors.append(f"{name}：另有 {count - MAX_ERRORS_PER_FILE} 筆欄位錯誤未列出")


def check_inputs(parents: list[dict], children: list[dict], embeddings: list[dict],
                 version: str) -> list[str]:
    """入庫前驗證（C3、S1、S2）。只依賴已文件化的契約（docs/04_chunk.md、docs/05_embed.md）。

    回傳錯誤清單，空清單表示通過。S1 的限制：向量檔與 children.jsonl 的逐筆欄位比對只能偵測
    欄位不一致，不等於來源指紋，無法證明兩者為同一批。
    """
    errors: list[str] = []
    # S2：三份輸入每一列的 version 都必須等於 sources.json 的值
    for name, rows in (("parents", parents), ("children", children), ("embeddings", embeddings)):
        found = {r.get("version") for r in rows}
        if found != {version}:
            errors.append(f"{name} 的 version 值集合為 {sorted(map(str, found))}，應只有 {version!r}（version 混雜或不符）")

    _check_record_shape(parents, PARENT_COLS, PARENT_STR_FIELDS, "parents", errors)
    _check_record_shape(children, CHILD_FIELDS, CHILD_STR_FIELDS, "children", errors)
    _check_record_shape(embeddings, EMBEDDING_FIELDS, CHILD_STR_FIELDS + ["embedding_input", "model_name",
                                                                           "model_revision"],
                        "embeddings", errors)
    if errors:
        return errors   # 後續檢查依賴欄位齊全

    # ID 唯一
    parent_ids = [p["parent_id"] for p in parents]
    child_ids = [c["chunk_id"] for c in children]
    for label, ids in (("parent_id", parent_ids), ("chunk_id", child_ids)):
        dup = sorted({i for i in ids if ids.count(i) > 1}) if len(ids) != len(set(ids)) else []
        if dup:
            errors.append(f"{label} 重複：{dup[:5]}")

    # 親子關係（docs/04_chunk.md）
    parent_by_id = {p["parent_id"]: p for p in parents}
    orphans = [c["chunk_id"] for c in children if c["parent_id"] not in parent_by_id]
    if orphans:
        errors.append(f"孤兒 child（找不到 parent）{len(orphans)} 筆：{orphans[:5]}")
    childless = sorted(set(parent_by_id) - {c["parent_id"] for c in children})
    if childless:
        errors.append(f"沒有 child 的 parent {len(childless)} 筆：{childless[:5]}")
    bad_id = [c["chunk_id"] for c in children if not c["chunk_id"].startswith(c["parent_id"] + ":c")]
    if bad_id:
        errors.append(f"chunk_id 不是以 parent_id + ':c' 開頭 {len(bad_id)} 筆：{bad_id[:5]}")
    not_sub = [c["chunk_id"] for c in children
               if c["parent_id"] in parent_by_id and c["text"] not in parent_by_id[c["parent_id"]]["text"]]
    if not_sub:
        errors.append(f"child.text 不是所屬 parent.text 的子字串 {len(not_sub)} 筆：{not_sub[:5]}")

    # 向量檔（docs/05_embed.md §1、§5）
    if len(embeddings) != len(children):
        errors.append(f"向量檔筆數 {len(embeddings)} ≠ children 筆數 {len(children)}")
    else:
        bad_pair = 0
        for i, (e, c) in enumerate(zip(embeddings, children), start=1):
            diff = [f for f in CHILD_FIELDS if e[f] != c[f]]
            if diff:
                bad_pair += 1
                if bad_pair <= MAX_ERRORS_PER_FILE:
                    errors.append(f"向量檔第 {i} 筆與 children 第 {i} 筆的原欄位不一致（順序或內容）：{diff}")
        if bad_pair > MAX_ERRORS_PER_FILE:
            errors.append(f"另有 {bad_pair - MAX_ERRORS_PER_FILE} 筆原欄位不一致未列出")
    vec_errors = 0
    for i, e in enumerate(embeddings, start=1):
        vec = e["embedding"]
        problem = ""
        if e["embedding_input"] != f"{e['section']}\n\n{e['text']}":
            problem = "embedding_input 不等於 section + 兩個換行 + text"
        elif not isinstance(vec, list) or len(vec) != EMBEDDING_DIM:
            problem = f"向量維度不是 {EMBEDDING_DIM}（實際 {len(vec) if isinstance(vec, list) else '非 list'}）"
        elif any((not isinstance(x, (int, float))) or isinstance(x, bool) or not math.isfinite(x) for x in vec):
            problem = "向量含非有限數（NaN／Inf）或非數值"
        else:
            norm = math.sqrt(sum(float(x) * float(x) for x in vec))
            if abs(norm - 1.0) > NORM_TOLERANCE:
                problem = f"向量 norm = {norm} 偏離 1 超過 {NORM_TOLERANCE}"
        if problem:
            vec_errors += 1
            if vec_errors <= MAX_ERRORS_PER_FILE:
                errors.append(f"向量檔第 {i} 筆：{problem}")
    if vec_errors > MAX_ERRORS_PER_FILE:
        errors.append(f"另有 {vec_errors - MAX_ERRORS_PER_FILE} 筆向量檢查失敗未列出")
    pairs = {(e["model_name"], e["model_revision"]) for e in embeddings}
    if len(pairs) != 1:
        errors.append(f"向量檔的 (model_name, model_revision) 不是單一一組：共 {len(pairs)} 組（model 組混雜）")
    return errors


def build_rows(parents: list[dict], embeddings: list[dict]) -> tuple[list[dict], list[dict]]:
    """組出寫入用的列：parents 取 PARENT_COLS；children 取 CHILD_COLS（含向量與 model 欄位）。"""
    parent_rows = [{k: p[k] for k in PARENT_COLS} for p in parents]
    child_rows = [{k: e[k] for k in CHILD_COLS} for e in embeddings]
    return parent_rows, child_rows


# ---------------------------------------------------------------------------
# [7.3] 內容指紋（產物端；僅供報告對照，不是驗證）
# ---------------------------------------------------------------------------
def _serialize(value: Any) -> bytes:
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return struct.pack("<Q", len(raw)) + raw
    if isinstance(value, bool):
        raise TypeError("不接受 bool")
    if isinstance(value, int):
        return b"I" + struct.pack("<q", value)
    arr = np.asarray(value, dtype="<f4")
    return b"V" + struct.pack("<I", arr.shape[0]) + arr.tobytes()


def table_fingerprint(rows: Iterable[dict], columns: list[str], key: str) -> str:
    """每表按主鍵（UTF-8 位元組序）排序，欄位依 columns 序列化，SHA-256 串流累加。"""
    h = hashlib.sha256()
    for row in sorted(rows, key=lambda r: r[key].encode("utf-8")):
        for col in columns:
            h.update(_serialize(row[col]))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# [7.4] 連線設定、遮罩與目標斷言（M3、N6、D5-1）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    """連線設定；__repr__ 不含 URL，避免被誤印。"""
    database_url: str = field(repr=False)
    database_url_test: str = field(repr=False)
    sources: dict = field(default_factory=dict)    # 各 key 的來源：'shell' 或 '.env'


def load_settings(env_path: Path) -> Settings:
    """以 load_dotenv(env_path)（不 override）載入；shell 變數優先。缺 key 的訊息只含 key 名稱。"""
    preset = {k for k in (ENV_URL_KEY, ENV_URL_TEST_KEY) if k in os.environ}
    load_dotenv(env_path)
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key in (ENV_URL_KEY, ENV_URL_TEST_KEY):
        value = os.environ.get(key, "")
        if not value.strip():
            raise SettingsError(f"缺少設定 {key}：請在 .env 或 shell 環境變數設定（不會顯示任何現有值）")
        if "${" in value:
            raise SettingsError(f"{key} 含 ${{ 變數展開語法：載入器是否展開未定，請寫完整字串")
        values[key] = value
        sources[key] = "shell" if key in preset else ".env"
    return Settings(values[ENV_URL_KEY], values[ENV_URL_TEST_KEY], sources)


def _parse_conninfo(url: str, label: str) -> dict:
    """以 libpq 自己的解析器取得「libpq 實際會用的」連線參數；失敗不顯示 URL 內容。"""
    try:
        parsed = conninfo_to_dict(url)
    except Exception:   # noqa: BLE001  解析器的訊息可能含 URL 片段，一律不顯示
        raise TargetError(f"{label} 無法解析為連線字串（內容不顯示）") from None
    return parsed


def parse_target(url: str, label: str = ENV_URL_KEY) -> dict:
    """D5-1：解析並驗證 DATABASE_URL；回傳 {host, port, dbname}（不含密碼）。

    規則：只允許 host／port／dbname／user／password 這幾個 key（避免用查詢字串覆蓋主機）；host 單一值
    且為 127.0.0.1 或 localhost；dbname 必須存在。任何不符即 TargetError（連線前）。
    """
    parsed = _parse_conninfo(url, label)
    extra = sorted(set(parsed) - set(ALLOWED_CONNINFO_KEYS))
    if extra:
        raise TargetError(f"{label} 含不允許的連線參數 {extra}（只允許 {list(ALLOWED_CONNINFO_KEYS)}）")
    host = str(parsed.get("host", ""))
    if not host or "," in host:
        raise TargetError(f"{label} 的主機必須是單一值（不可為空、不可多主機）")
    if host.lower() not in ALLOWED_HOSTS:
        raise TargetError(f"{label} 的主機 {host!r} 不在允許清單 {list(ALLOWED_HOSTS)}（D5-1）")
    port = str(parsed.get("port", ""))
    if port and not port.isdigit():
        raise TargetError(f"{label} 的 port 不合法")
    dbname = str(parsed.get("dbname", ""))
    if not dbname:
        raise TargetError(f"{label} 缺少庫名")
    return {"host": host.lower(), "port": port or "5432", "dbname": dbname}


def assert_target_urls(url: str, url_test: str) -> dict:
    """D5-1 連線前斷言：主機、參數、庫名存在，且與 DATABASE_URL_TEST 的庫名不同。回傳遮罩後的目標描述。"""
    target = parse_target(url, ENV_URL_KEY)
    test_parsed = _parse_conninfo(url_test, ENV_URL_TEST_KEY)
    test_db = str(test_parsed.get("dbname", ""))
    if not test_db:
        raise TargetError(f"{ENV_URL_TEST_KEY} 缺少庫名")
    if test_db == target["dbname"]:
        raise TargetError(f"{ENV_URL_KEY} 與 {ENV_URL_TEST_KEY} 指向同一個庫名 {test_db!r}（D5-1 要求不同）")
    return target


def secrets_of(*urls: str) -> list[str]:
    """取出 URL 中的密碼（解析後與 percent 編碼前兩種形式），供遮罩使用。"""
    out: list[str] = []
    for url in urls:
        try:
            pw = conninfo_to_dict(url).get("password")
        except Exception:   # noqa: BLE001
            pw = None
        if pw:
            out.append(str(pw))
    return out


def mask_text(text: str, secrets: list[str]) -> str:
    """把文字中的密碼與 URL 內嵌的帳密樣式以 *** 取代。"""
    for s in secrets:
        text = text.replace(s, "***")
    return re.sub(r"://[^/\s:@]+:[^@\s]+@", "://***:***@", text)


def connect(url: str, secrets: list[str]) -> psycopg.Connection:
    """唯一呼叫 psycopg.connect 的地方；autocommit 模式，失敗訊息經遮罩且不串接原例外。"""
    try:
        return psycopg.connect(url, autocommit=True, connect_timeout=CONNECT_TIMEOUT_SECONDS)
    except psycopg.Error as exc:
        raise ConnectionFailed(f"連線失敗（{type(exc).__name__}）：{mask_text(str(exc).strip(), secrets)}") from None


def assert_server_database(conn: Any, expected: str) -> str:
    """D5-1：以伺服器的回答為準，current_database() 必須等於預期庫名。"""
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        actual = cur.fetchone()[0]
    if actual != expected:
        raise DatabaseAssertionError(f"目標資料庫是 {actual!r}，預期 {expected!r}；中止，不動任何資料（D5-1）")
    return actual


# ---------------------------------------------------------------------------
# [7.5] 擴充檢查（D7）
# ---------------------------------------------------------------------------
def evaluate_extension_version(found: Optional[str]) -> tuple[int, int, int]:
    """D7：extversion 必須是 x.y.z 且以整數 tuple 比較 >= (0, 8, 2)；None 表示查無擴充。"""
    hint = "請使用者手動執行 CREATE EXTENSION IF NOT EXISTS vector;（兩個庫各一次）"
    if found is None:
        raise ExtensionError(f"查無 vector 擴充。{hint}")
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", found)
    if not m:
        raise ExtensionError(f"無法解析 vector 擴充版本 {found!r}")
    version = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if version < MIN_PGVECTOR:
        need = ".".join(map(str, MIN_PGVECTOR))
        raise ExtensionError(f"vector 擴充版本 {found} 過舊，需要 >= {need}（避開 CVE-2026-3172）")
    return version


def check_extension(conn: Any) -> tuple[str, str]:
    """查 pg_extension：存在、所在 schema 必須是 public（限定名稱的前提）、版本 >= 0.8.2。"""
    with conn.cursor() as cur:
        cur.execute("SELECT e.extversion, n.nspname FROM pg_extension e "
                    "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'")
        row = cur.fetchone()
    evaluate_extension_version(row[0] if row else None)
    if row[1] != "public":
        raise ExtensionError(f"vector 擴充在 schema {row[1]!r}，本程式的限定名稱要求 public")
    return row[0], row[1]


def register_vector_public(conn: Any) -> None:
    """以限定名稱 public.vector 取得型別並註冊 pgvector 轉接器（不依賴 search_path）。"""
    info = TypeInfo.fetch(conn, "public.vector")
    register_vector_info(conn, info)


# ---------------------------------------------------------------------------
# [7.6] Schema（DDL 與核對；M2、N13）
# ---------------------------------------------------------------------------
DDL_STATEMENTS = [
    "CREATE SCHEMA IF NOT EXISTS rag",
    """CREATE TABLE IF NOT EXISTS rag.parents (
    parent_id   text    NOT NULL,
    text        text    NOT NULL,
    title       text    NOT NULL,
    source_url  text    NOT NULL,
    version     text    NOT NULL,
    mod         text    NOT NULL,
    chapter     text    NOT NULL,
    page        text    NOT NULL,
    section     text    NOT NULL,
    token_count integer NOT NULL,
    CONSTRAINT parents_pkey PRIMARY KEY (parent_id),
    CONSTRAINT parents_nonempty_chk CHECK (
        parent_id <> '' AND text <> '' AND title <> '' AND source_url <> ''
        AND version <> '' AND mod <> '' AND chapter <> '' AND page <> '' AND section <> ''),
    CONSTRAINT parents_token_count_chk CHECK (token_count > 0)
)""",
    """CREATE TABLE IF NOT EXISTS rag.children (
    chunk_id       text                NOT NULL,
    parent_id      text                NOT NULL,
    text           text                NOT NULL,
    title          text                NOT NULL,
    source_url     text                NOT NULL,
    version        text                NOT NULL,
    mod            text                NOT NULL,
    chapter        text                NOT NULL,
    page           text                NOT NULL,
    section        text                NOT NULL,
    token_count    integer             NOT NULL,
    embedding      public.vector(1024) NOT NULL,
    model_name     text                NOT NULL,
    model_revision text                NOT NULL,
    CONSTRAINT children_pkey PRIMARY KEY (chunk_id),
    CONSTRAINT children_parent_id_fkey FOREIGN KEY (parent_id)
        REFERENCES rag.parents (parent_id) ON DELETE NO ACTION ON UPDATE NO ACTION,
    CONSTRAINT children_nonempty_chk CHECK (
        chunk_id <> '' AND parent_id <> '' AND text <> '' AND title <> '' AND source_url <> ''
        AND version <> '' AND mod <> '' AND chapter <> '' AND page <> '' AND section <> ''
        AND model_name <> '' AND model_revision <> ''),
    CONSTRAINT children_token_count_chk CHECK (token_count > 0)
)""",
    "CREATE INDEX IF NOT EXISTS children_parent_id_idx ON rag.children USING btree (parent_id)",
]

_TEXT_COLS = ["text", "title", "source_url", "version", "mod", "chapter", "page", "section"]

# 預期表結構；以純 dict 表示，供 check_table_schema 參數化（可對 TEMP 表使用）
PARENTS_SPEC: dict = {
    "columns": [("parent_id", "text", True)] + [(c, "text", True) for c in _TEXT_COLS]
               + [("token_count", "integer", True)],
    "pk": ["parent_id"],
    "fk": None,
    "checks": ["parents_nonempty_chk", "parents_token_count_chk"],
    "index": None,
}
CHILDREN_SPEC: dict = {
    "columns": [("chunk_id", "text", True), ("parent_id", "text", True)]
               + [(c, "text", True) for c in _TEXT_COLS] + [("token_count", "integer", True),
                                                             ("embedding", "vector(1024)", True),
                                                             ("model_name", "text", True),
                                                             ("model_revision", "text", True)],
    "pk": ["chunk_id"],
    "fk": {"column": "parent_id", "target": "rag.parents", "target_column": "parent_id"},
    "checks": ["children_nonempty_chk", "children_token_count_chk"],
    "index": ("children_parent_id_idx", "parent_id"),
}


def check_table_schema(conn: Any, relation: str, spec: dict) -> list[str]:
    """核對 relation（完整名稱或 pg_temp.xxx）的欄位、型別、NOT NULL、主鍵、外鍵、CHECK 與索引。

    回傳不符項清單（空清單表示相符）；不修改任何東西。欄位不得多也不得少；外鍵須存在且為 NO ACTION。
    """
    problems: list[str] = []
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)::oid", (relation,))
        oid = cur.fetchone()[0]
        if oid is None:
            return [f"{relation}：表不存在"]
        cur.execute(
            "SELECT a.attname, a.attnotnull, t.typname, tn.nspname, "
            "format_type(a.atttypid, a.atttypmod), a.atttypmod "
            "FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid "
            "JOIN pg_namespace tn ON tn.oid = t.typnamespace "
            "WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped", (oid,))
        actual: dict[str, tuple] = {}
        for name, notnull, typname, typns, fmt, typmod in cur.fetchall():
            if typname == "vector":
                type_str = f"vector({typmod})"
                if typns != "public":
                    problems.append(f"{relation}.{name}：vector 型別在 schema {typns!r}，應為 public")
            else:
                type_str = fmt
            actual[name] = (type_str, notnull)
        expected = {name: (type_str, notnull) for name, type_str, notnull in spec["columns"]}
        for name in sorted(set(expected) - set(actual)):
            problems.append(f"{relation}：缺少欄位 {name}")
        for name in sorted(set(actual) - set(expected)):
            problems.append(f"{relation}：多出未預期的欄位 {name}")
        for name in sorted(set(expected) & set(actual)):
            if actual[name][0] != expected[name][0]:
                problems.append(f"{relation}.{name}：型別 {actual[name][0]}，預期 {expected[name][0]}")
            if actual[name][1] != expected[name][1]:
                problems.append(f"{relation}.{name}：NOT NULL 為 {actual[name][1]}，預期 {expected[name][1]}")
        # 主鍵
        cur.execute("SELECT a.attname FROM pg_index i JOIN pg_attribute a "
                    "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = %s AND i.indisprimary", (oid,))
        pk = sorted(r[0] for r in cur.fetchall())
        if pk != sorted(spec["pk"]):
            problems.append(f"{relation}：主鍵欄位 {pk}，預期 {sorted(spec['pk'])}")
        # 外鍵（N13：CREATE TABLE IF NOT EXISTS 不會替既有表補外鍵）
        cur.execute(
            "SELECT con.confdeltype, con.confupdtype, con.confrelid = to_regclass(%s)::oid, "
            "(SELECT array_agg(att.attname ORDER BY att.attname) FROM pg_attribute att "
            " WHERE att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)), "
            "(SELECT array_agg(att.attname ORDER BY att.attname) FROM pg_attribute att "
            " WHERE att.attrelid = con.confrelid AND att.attnum = ANY(con.confkey)) "
            "FROM pg_constraint con WHERE con.conrelid = %s AND con.contype = 'f'",
            (spec["fk"]["target"] if spec["fk"] else relation, oid))
        fks = cur.fetchall()
        if spec["fk"] is None:
            if fks:
                problems.append(f"{relation}：不應有外鍵")
        elif not fks:
            problems.append(f"{relation}：缺少外鍵 {spec['fk']['column']} → {spec['fk']['target']}")
        else:
            if len(fks) != 1:
                problems.append(f"{relation}：外鍵數量 {len(fks)}，預期 1")
            deltype, updtype, same_target, cols, refcols = fks[0]
            if not same_target:
                problems.append(f"{relation}：外鍵未指向 {spec['fk']['target']}")
            if cols != [spec["fk"]["column"]] or refcols != [spec["fk"]["target_column"]]:
                problems.append(f"{relation}：外鍵欄位為 {cols} → {refcols}")
            if deltype != "a":
                problems.append(f"{relation}：外鍵 ON DELETE 動作碼 {deltype!r}，預期 NO ACTION（'a'）")
            if updtype != "a":
                problems.append(f"{relation}：外鍵 ON UPDATE 動作碼 {updtype!r}，預期 NO ACTION（'a'）")
        # CHECK 約束
        cur.execute("SELECT conname FROM pg_constraint WHERE conrelid = %s AND contype = 'c'", (oid,))
        have = {r[0] for r in cur.fetchall()}
        for name in spec["checks"]:
            if name not in have:
                problems.append(f"{relation}：缺少 CHECK 約束 {name}")
        # 索引
        if spec["index"] is not None:
            idx_name, idx_col = spec["index"]
            cur.execute(
                "SELECT ic.relname, am.amname, "
                "(SELECT array_agg(att.attname) FROM pg_attribute att "
                " WHERE att.attrelid = i.indrelid AND att.attnum = ANY(i.indkey)) "
                "FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid "
                "JOIN pg_am am ON am.oid = ic.relam WHERE i.indrelid = %s", (oid,))
            idx = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
            if idx_name not in idx:
                problems.append(f"{relation}：缺少索引 {idx_name}")
            elif idx[idx_name][0] != "btree" or idx[idx_name][1] != [idx_col]:
                problems.append(f"{relation}：索引 {idx_name} 不是 {idx_col} 上的 btree")
    return problems


def ensure_schema(conn: Any) -> None:
    """建表（CREATE ... IF NOT EXISTS）並核對；不符即 SchemaMismatch，不自動變更表結構。"""
    with conn.cursor() as cur:
        for statement in DDL_STATEMENTS:
            cur.execute(statement)
    problems = (check_table_schema(conn, "rag.parents", PARENTS_SPEC)
                + check_table_schema(conn, "rag.children", CHILDREN_SPEC))
    if problems:
        raise SchemaMismatch("既有表結構與預期不符，不自動變更，須使用者授權後人工重建：" + NEWLINE
                             + NEWLINE.join("  - " + p for p in problems))


# ---------------------------------------------------------------------------
# [7.7] 寫入（D5、N4、S2、S3）
# ---------------------------------------------------------------------------
@dataclass
class TableCounts:
    """單表的寫入統計（S3：供對帳）。"""
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    deleted_before: int = 0     # rebuild：刪除前該 version 的列數


@dataclass
class WriteCounts:
    mode: str
    parents: TableCounts = field(default_factory=TableCounts)
    children: TableCounts = field(default_factory=TableCounts)


def _require_ready(conn: Any, version: str, parents: list[dict], children: list[dict]) -> None:
    """寫入前置：連線須 autocommit 且無進行中交易（才能確保只有一個交易）；所有輸入列的 version 一致。"""
    if not conn.autocommit or conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        raise WriteError("寫入函式要求 autocommit 連線且沒有進行中的交易")
    if not valid_version(version):
        raise WriteError(f"version 不合法：{version!r}")
    bad = [r for r in parents + children if r.get("version") != version]
    if bad:
        raise WriteError(f"輸入列的 version 與 {version!r} 不一致 {len(bad)} 筆（S2）")


def _params(row: dict, cols: list[str]) -> list[Any]:
    """把一列轉成 SQL 參數；向量以 float32 的 pgvector Vector 傳入。"""
    return [Vector(np.asarray(row[c], dtype=np.float32)) if c == "embedding" else row[c] for c in cols]


def _model_pair(children: list[dict]) -> tuple[str, str]:
    pairs = {(c["model_name"], c["model_revision"]) for c in children}
    if len(pairs) != 1:
        raise WriteError(f"輸入的 (model_name, model_revision) 不是單一一組（{len(pairs)} 組）")
    return next(iter(pairs))


def guard_update(conn: Any, pair: tuple[str, str]) -> None:
    """update 防呆（D5、Q1、Q2）：整張 rag.children 的 model 組與維度須與新產物相同；空表視為通過。"""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT model_name, model_revision FROM rag.children")
        found = {tuple(r) for r in cur.fetchall()}
        cur.execute("SELECT DISTINCT public.vector_dims(embedding) FROM rag.children")
        dims = {r[0] for r in cur.fetchall()}
    if found - {pair} or (dims - {EMBEDDING_DIM}):
        raise GuardError("資料庫內的 (model_name, model_revision) 或向量維度與新產物不同；update 中止，"
                         "請使用者確認後改用 --mode rebuild（D5）")


def check_other_versions(conn: Any, version: str, pair: tuple[str, str]) -> None:
    """rebuild 防呆（Q2）：其他 version 的 model 組須與新產物相同，否則中止（本程式只可刪除一個 version）。"""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT model_name, model_revision FROM rag.children WHERE version <> %s",
                    (version,))
        found = {tuple(r) for r in cur.fetchall()}
    if found - {pair}:
        raise GuardError("其他 version 的 (model_name, model_revision) 與新產物不同；rebuild 中止，"
                         "否則表內會出現兩組 model（違反單一 model 組）。其他 version 須由使用者另行處理")


def _upsert_sql(table: str, cols: list[str], key: str) -> str:
    """INSERT ... ON CONFLICT DO UPDATE；只在內容有差異時才更新，RETURNING 主鍵（新增或實際變動者）。"""
    non_key = [c for c in cols if c != key]
    placeholders = ", ".join(["%s"] * len(cols))
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_key)
    old = ", ".join(f"t.{c}" for c in non_key)
    new = ", ".join(f"EXCLUDED.{c}" for c in non_key)
    return (f"INSERT INTO {table} AS t ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({key}) DO UPDATE SET {sets} WHERE ({old}) IS DISTINCT FROM ({new}) "
            f"RETURNING {key}")


def _insert_sql(table: str, cols: list[str]) -> str:
    return f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"


def _existing_ids(cur: Any, table: str, key: str, version: str) -> set[str]:
    cur.execute(f"SELECT {key} FROM {table} WHERE version = %s", (version,))
    return {r[0] for r in cur.fetchall()}


def _upsert_rows(cur: Any, table: str, cols: list[str], key: str, rows: list[dict],
                 existing: set[str]) -> TableCounts:
    counts = TableCounts()
    sql = _upsert_sql(table, cols, key)
    for row in rows:
        cur.execute(sql, _params(row, cols))
        if cur.fetchone() is None:
            counts.unchanged += 1
        elif row[key] in existing:
            counts.updated += 1
        else:
            counts.inserted += 1
    return counts


def _assert_counts(cur: Any, version: str, n_parents: int, n_children: int) -> None:
    """寫入安全網：資料庫內該 version 的列數必須等於輸入筆數，否則丟例外讓交易回滾（不是驗收）。"""
    cur.execute("SELECT count(*) FROM rag.parents WHERE version = %s", (version,))
    got_p = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM rag.children WHERE version = %s", (version,))
    got_c = cur.fetchone()[0]
    if (got_p, got_c) != (n_parents, n_children):
        raise WriteError(f"寫入後筆數不符：parents {got_p}/{n_parents}、children {got_c}/{n_children}；交易回滾")


def write_update(conn: Any, version: str, parents: list[dict], children: list[dict]) -> WriteCounts:
    """更新模式（D5、N4）：單一交易內就地更新、新增，並刪除該 version 中新產物已不存在的列。

    順序：parents 先、children 後；刪除 children 先、parents 後。呼叫端須已註冊 pgvector 轉接器。
    """
    _require_ready(conn, version, parents, children)
    pair = _model_pair(children)
    counts = WriteCounts("update")
    with conn.transaction():
        ensure_schema(conn)
        guard_update(conn, pair)
        with conn.cursor() as cur:
            existing_p = _existing_ids(cur, "rag.parents", "parent_id", version)
            existing_c = _existing_ids(cur, "rag.children", "chunk_id", version)
            counts.parents = _upsert_rows(cur, "rag.parents", PARENT_COLS, "parent_id", parents, existing_p)
            counts.children = _upsert_rows(cur, "rag.children", CHILD_COLS, "chunk_id", children, existing_c)
            stale_c = sorted(existing_c - {c["chunk_id"] for c in children})
            stale_p = sorted(existing_p - {p["parent_id"] for p in parents})
            if stale_c:
                cur.execute("DELETE FROM rag.children WHERE version = %s AND chunk_id = ANY(%s)", (version, stale_c))
                counts.children.deleted = cur.rowcount
            if stale_p:
                cur.execute("DELETE FROM rag.parents WHERE version = %s AND parent_id = ANY(%s)", (version, stale_p))
                counts.parents.deleted = cur.rowcount
            _assert_counts(cur, version, len(parents), len(children))
    return counts


def write_rebuild(conn: Any, version: str, parents: list[dict], children: list[dict]) -> WriteCounts:
    """重做模式（D5）：單一交易內刪除該 version 兩表的資料（先 children 後 parents），再全部寫入。"""
    _require_ready(conn, version, parents, children)
    pair = _model_pair(children)
    counts = WriteCounts("rebuild")
    with conn.transaction():
        ensure_schema(conn)
        check_other_versions(conn, version, pair)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag.children WHERE version = %s", (version,))
            counts.children.deleted = counts.children.deleted_before = cur.rowcount
            cur.execute("DELETE FROM rag.parents WHERE version = %s", (version,))
            counts.parents.deleted = counts.parents.deleted_before = cur.rowcount
            sql_p, sql_c = _insert_sql("rag.parents", PARENT_COLS), _insert_sql("rag.children", CHILD_COLS)
            for row in parents:
                cur.execute(sql_p, _params(row, PARENT_COLS))
            counts.parents.inserted = len(parents)
            for row in children:
                cur.execute(sql_c, _params(row, CHILD_COLS))
            counts.children.inserted = len(children)
            _assert_counts(cur, version, len(parents), len(children))
    return counts


# ---------------------------------------------------------------------------
# [7.8] 報告（N9：單次、整份覆寫；不含密碼、完整 URL 或憑證）
# ---------------------------------------------------------------------------
@dataclass
class RunInfo:
    mode: str
    started: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    version: str = "—"
    host: str = "—"
    port: str = "—"
    dbname: str = "—"
    loopback: str = "—"
    setting_source: str = "—"
    ext_version: str = "—"
    ext_schema: str = "—"
    n_parents: Optional[int] = None
    n_children: Optional[int] = None
    model: str = "—"
    fp_parents: str = "—"
    fp_children: str = "—"
    counts: Optional[WriteCounts] = None
    exit_code: int = 1
    reason: str = "—"


def write_report(path: Path, info: RunInfo) -> None:
    """寫 reports/index_report.md（整份覆寫）。"""
    def table_line(name: str, c: Optional[TableCounts]) -> str:
        if c is None:
            return f"| {name} | — | — | — | — | — |"
        return f"| {name} | {c.inserted} | {c.updated} | {c.unchanged} | {c.deleted} | {c.deleted_before} |"

    cnt = info.counts
    lines = [
        "# 入庫報告（[7] index_chunks.py）",
        "",
        "## 1. 執行",
        "",
        f"- 時間：{info.started}",
        f"- 模式：`{info.mode}`",
        f"- version：`{info.version}`",
        f"- 結束碼：{info.exit_code}",
        f"- 結果：{'成功' if info.exit_code == 0 else '中止'}；原因：{info.reason}",
        "",
        "## 2. 目標",
        "",
        f"- 主機：`{info.host}`；port：`{info.port}`；庫名：`{info.dbname}`",
        f"- 是否 loopback：{info.loopback}",
        f"- 設定來源：{info.setting_source}",
        f"- vector 擴充：`{info.ext_version}`（schema `{info.ext_schema}`）",
        "",
        "## 3. 輸入",
        "",
        f"- parents：{info.n_parents if info.n_parents is not None else '—'}；"
        f"children：{info.n_children if info.n_children is not None else '—'}",
        f"- model：{info.model}",
        "",
        "## 4. 寫入統計",
        "",
        "| 表 | 新增 | 更新 | 未變 | 刪除 | 刪除前列數（rebuild） |",
        "| --- | --- | --- | --- | --- | --- |",
        table_line("rag.parents", cnt.parents if cnt else None),
        table_line("rag.children", cnt.children if cnt else None),
        "",
        "## 5. 內容指紋",
        "",
        "- 寫入前產物端指紋（本程式自行計算，僅供對照，不是驗證）：",
        f"  - parents：`{info.fp_parents}`",
        f"  - children：`{info.fp_children}`",
        "- 指紋比對結果：本程式不自行比對；由 `verify_index.py`、`audit_index.py` 獨立比對，結果見 "
        "`reports/verify_index_report.md`、`reports/audit_index_report.md`。",
        "",
        "## 6. 限制（S1）",
        "",
        "- 向量檔與 children.jsonl 的逐筆欄位比對只能偵測欄位不一致，不等於來源指紋；無法證明兩者為同一批。",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline=NEWLINE) as f:
        f.write(NEWLINE.join(lines))


# ---------------------------------------------------------------------------
# [7.9] 主流程（只編排；不自行判斷通過與否）
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """只有 --mode（必填、無預設）；未傳入由 argparse 以結束碼 2 中止，此時沒有任何連線。"""
    parser = argparse.ArgumentParser(description="[7] 入庫", add_help=False)
    parser.add_argument("--mode", required=True, choices=list(MODES),
                        help="update：就地更新；rebuild：刪除該 version 後重寫（由使用者確認後明確傳入）")
    return parser.parse_args(argv)


def run(mode: str, info: RunInfo) -> None:
    """依固定順序執行各步驟；任何步驟失敗都以例外中止。"""
    sources = load_sources(SOURCES_PATH)
    info.version = version = sources.get("version", "")
    parents, children, embeddings = load_inputs(version)
    errors = check_inputs(parents, children, embeddings, version)
    if errors:
        raise InputError("入庫前驗證失敗（尚未讀 .env、未連線）：" + NEWLINE + NEWLINE.join("  - " + e for e in errors))
    parent_rows, child_rows = build_rows(parents, embeddings)
    info.n_parents, info.n_children = len(parent_rows), len(child_rows)
    info.model = f"{child_rows[0]['model_name']} @ {child_rows[0]['model_revision']}"
    info.fp_parents = table_fingerprint(parent_rows, PARENT_COLS, "parent_id")
    info.fp_children = table_fingerprint(child_rows, CHILD_COLS, "chunk_id")
    print(f"[7] 輸入：parents {info.n_parents}、children {info.n_children}；入庫前驗證通過（version={version}）")

    settings = load_settings(ENV_PATH)
    target = assert_target_urls(settings.database_url, settings.database_url_test)
    info.host, info.port, info.dbname = target["host"], target["port"], target["dbname"]
    info.loopback = "是"
    info.setting_source = ", ".join(f"{k}：{v}" for k, v in settings.sources.items())
    print(f"[7] 目標：host={info.host} port={info.port} db={info.dbname}（設定來源 {info.setting_source}）")

    secrets = secrets_of(settings.database_url, settings.database_url_test)
    conn = connect(settings.database_url, secrets)
    try:
        assert_server_database(conn, EXPECTED_DB)
        info.ext_version, info.ext_schema = check_extension(conn)
        register_vector_public(conn)
        writer = write_update if mode == "update" else write_rebuild
        try:
            info.counts = writer(conn, version, parent_rows, child_rows)
        except psycopg.Error as exc:
            raise IndexingError(f"資料庫錯誤（{type(exc).__name__}），交易已回滾：{mask_text(str(exc).strip(), secrets)}") from None
    finally:
        conn.close()
    c = info.counts
    print(f"[7] 完成（{mode}）：parents 新增 {c.parents.inserted}／更新 {c.parents.updated}／未變 {c.parents.unchanged}"
          f"／刪除 {c.parents.deleted}；children 新增 {c.children.inserted}／更新 {c.children.updated}"
          f"／未變 {c.children.unchanged}／刪除 {c.children.deleted}")


def main(argv: Optional[list[str]] = None) -> int:
    """[7] 主流程。結束碼：0 成功；1 任何中止；2 用法錯誤（argparse）。"""
    args = parse_args(argv)
    info = RunInfo(mode=args.mode)
    try:
        run(args.mode, info)
        info.exit_code, info.reason = 0, "—"
    except IndexingError as exc:
        info.reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        print(f"[7] 中止：{exc}", file=sys.stderr)
    except psycopg.Error as exc:
        message = mask_text(f"資料庫錯誤（{type(exc).__name__}）：{str(exc).strip()}", [])
        info.reason = message.splitlines()[0]
        print(f"[7] 中止：{message}", file=sys.stderr)
    try:
        write_report(REPORT_PATH, info)
        print(f"     報告：{REPORT_PATH.relative_to(PROJECT_ROOT)}")
    except OSError as exc:
        print(f"[7] 警告：無法寫報告（{type(exc).__name__}）", file=sys.stderr)
    return info.exit_code


if __name__ == "__main__":
    sys.exit(main())
