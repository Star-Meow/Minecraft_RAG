"""[7] 入庫後的正式庫唯讀核對（只連 minecraft_rag；只做 SELECT）。

- 連線後立即設為唯讀（conn.read_only = True，並檢查 transaction_read_only = on）；本腳本不嘗試任何寫入。
- 不 import index_chunks.py：URL 解析、斷言、schema 核對、指紋與暴力 cosine 都由本腳本（與
  index_check_utils.py 的純工具）自己計算。
- 核對項目 A1～A12（計畫 §7.3）。結果寫入 reports/audit_index_report.md（單次、整份覆寫，不含密碼與完整 URL）。
- 由使用者在 `index_chunks.py --mode ...` 完成後執行（會讀 .env）。
- V5 只證明資料庫排序等於暴力計算，不證明檢索品質（D6）；A11 同。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import numpy as np
from pgvector import Vector

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))

from index_check_utils import (CHILD_FP_COLUMNS, D6_SENTENCE, NN_ATTENTION, NN_TOLERANCE, NN_TOP_K,  # noqa: E402
                               PARENT_FP_COLUMNS, PROJECT_ROOT, ResultLog, artifact_paths,
                               cosine_distance_matrix, f32, f32_bytes, fingerprint, first_line,
                               mask_secrets, read_jsonl, tie_set, write_text)

REPORT_PATH = PROJECT_ROOT / "reports" / "audit_index_report.md"
PROD_DB = "minecraft_rag"
LOOPBACK = ("127.0.0.1", "localhost")
MIN_PGVECTOR = (0, 8, 2)
PARENT_NAMES = [c for c, _ in PARENT_FP_COLUMNS]
CHILD_NAMES = [c for c, _ in CHILD_FP_COLUMNS]
# 寫入類關鍵字（拆開寫，避免本檔原始碼自己命中）；只比對大寫（SQL 寫法）
WRITE_WORDS = ["INS" + "ERT", "UPD" + "ATE", "DEL" + "ETE", "CRE" + "ATE", "ALT" + "ER", "DR" + "OP", "TRUNC" + "ATE"]
WRITE_RE = re.compile(r"\b(" + "|".join(WRITE_WORDS) + r")\b")

LOG = ResultLog()
SECRETS: list[str] = []

# 預期結構（本腳本自己的期望值，不 import 程式的 spec）
TEXT_COLS = ["text", "title", "source_url", "version", "mod", "chapter", "page", "section"]
EXPECTED = {
    "parents": {"columns": {"parent_id": ("text", True), **{c: ("text", True) for c in TEXT_COLS},
                            "token_count": ("integer", True)},
                "pk": ["parent_id"], "checks": {"parents_nonempty_chk", "parents_token_count_chk"}},
    "children": {"columns": {"chunk_id": ("text", True), "parent_id": ("text", True),
                             **{c: ("text", True) for c in TEXT_COLS}, "token_count": ("integer", True),
                             "embedding": ("vector(1024)", True), "model_name": ("text", True),
                             "model_revision": ("text", True)},
                 "pk": ["chunk_id"], "checks": {"children_nonempty_chk", "children_token_count_chk"}},
}


def strict_parse(url: str) -> dict:
    """自己的 URL 解析；拒絕查詢字串與多主機。"""
    sp = urlsplit(url)
    if sp.scheme not in ("postgresql", "postgres"):
        raise ValueError("scheme 不是 postgresql")
    if sp.query or sp.fragment:
        raise ValueError("URL 帶有查詢字串或 fragment")
    if "," in sp.netloc:
        raise ValueError("多主機")
    dbname = unquote(sp.path.lstrip("/"))
    if not dbname or "/" in dbname:
        raise ValueError("缺少庫名")
    host = (sp.hostname or "").lower()
    if not host:
        raise ValueError("缺少主機")
    return {"host": host, "port": sp.port, "dbname": dbname, "password": unquote(sp.password) if sp.password else None}


def mask(text: str) -> str:
    return mask_secrets(text, SECRETS)


class VectorTypeError(TypeError):
    """embedding 欄位讀回的不是 pgvector 的 Vector（例如 vector loader 未註冊而讀到 str）；訊息為實際型別名稱。"""


def scalar(cur: Any, sql: str, params: tuple = ()) -> Any:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def db_rows(cur: Any, table: str, columns: list[str], key: str, version: str | None) -> list[dict]:
    """讀某表所有列（version 為 None 表示全表）；依主鍵位元組序排序；向量轉 float32 numpy。"""
    where, params = ("WHERE version = %s", (version,)) if version is not None else ("", ())
    cur.execute(f'SELECT {", ".join(columns)} FROM rag.{table} {where} ORDER BY {key} COLLATE "C"', params)
    rows = []
    for values in cur.fetchall():
        row = dict(zip(columns, values))
        if "embedding" in row:
            if not isinstance(row["embedding"], Vector):
                raise VectorTypeError(type(row["embedding"]).__name__)
            row["embedding"] = row["embedding"].to_numpy()
        rows.append(row)
    return rows


def schema_problems(cur: Any, table: str) -> list[str]:
    """A3：以 pg_catalog 核對欄位、型別、NOT NULL、主鍵、外鍵（NO ACTION）、CHECK 與索引。"""
    spec = EXPECTED[table]
    rel = f"rag.{table}"
    problems: list[str] = []
    oid = scalar(cur, "SELECT to_regclass(%s)::oid", (rel,))
    if oid is None:
        return [f"{rel} 不存在"]
    cur.execute("SELECT a.attname, a.attnotnull, t.typname, tn.nspname, format_type(a.atttypid, a.atttypmod), a.atttypmod "
                "FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid JOIN pg_namespace tn ON tn.oid = t.typnamespace "
                "WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped", (oid,))
    actual = {}
    for name, notnull, typname, typns, fmt, typmod in cur.fetchall():
        if typname == "vector":
            actual[name] = (f"vector({typmod})", notnull)
            if typns != "public":
                problems.append(f"{rel}.{name} 的 vector 型別在 {typns}")
        else:
            actual[name] = (fmt, notnull)
    if actual != spec["columns"]:
        missing = sorted(set(spec["columns"]) - set(actual))
        extra = sorted(set(actual) - set(spec["columns"]))
        wrong = sorted(k for k in set(actual) & set(spec["columns"]) if actual[k] != spec["columns"][k])
        problems.append(f"{rel} 欄位不符：缺 {missing}、多 {extra}、型別或 NOT NULL 不符 {wrong}")
    cur.execute("SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                "WHERE i.indrelid = %s AND i.indisprimary", (oid,))
    if sorted(r[0] for r in cur.fetchall()) != spec["pk"]:
        problems.append(f"{rel} 主鍵不符")
    cur.execute("SELECT con.confdeltype, con.confupdtype, con.confrelid::regclass::text, "
                "(SELECT array_agg(att.attname) FROM pg_attribute att WHERE att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)), "
                "(SELECT array_agg(att.attname) FROM pg_attribute att WHERE att.attrelid = con.confrelid AND att.attnum = ANY(con.confkey)) "
                "FROM pg_constraint con WHERE con.conrelid = %s AND con.contype = 'f'", (oid,))
    fks = cur.fetchall()
    if table == "children":
        if len(fks) != 1:
            problems.append(f"{rel} 外鍵數量 {len(fks)}，預期 1（既有表缺外鍵時建表語句（IF NOT EXISTS）不會補，須人工處理）")
        else:
            d, u, target, cols, refcols = fks[0]
            if (d, u) != ("a", "a"):
                problems.append(f"{rel} 外鍵動作碼 ({d}, {u})，預期 NO ACTION（不得 CASCADE）")
            if target != "rag.parents" or cols != ["parent_id"] or refcols != ["parent_id"]:
                problems.append(f"{rel} 外鍵指向 {target}、欄位 {cols} → {refcols}")
    elif fks:
        problems.append(f"{rel} 不應有外鍵")
    cur.execute("SELECT conname FROM pg_constraint WHERE conrelid = %s AND contype = 'c'", (oid,))
    missing_checks = sorted(spec["checks"] - {r[0] for r in cur.fetchall()})
    if missing_checks:
        problems.append(f"{rel} 缺少 CHECK 約束 {missing_checks}")
    if table == "children":
        cur.execute("SELECT ic.relname, am.amname FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid "
                    "JOIN pg_am am ON am.oid = ic.relam WHERE i.indrelid = %s", (oid,))
        idx = dict(cur.fetchall())
        if idx.get("children_parent_id_idx") != "btree":
            problems.append(f"{rel} 缺少 btree 索引 children_parent_id_idx")
    return problems


def main() -> int:
    import psycopg
    from dotenv import load_dotenv
    from pgvector.psycopg.vector import register_vector_info
    from psycopg.types import TypeInfo

    sys.stdout.reconfigure(errors="replace")
    load_dotenv(PROJECT_ROOT / ".env")
    url, url_test = os.environ.get("DATABASE_URL", ""), os.environ.get("DATABASE_URL_TEST", "")
    if not url or not url_test:
        print("缺少 DATABASE_URL 或 DATABASE_URL_TEST（只顯示 key 名稱；請在 .env 或 shell 設定）", file=sys.stderr)
        return 1
    intro: list[str] = []
    # A1：斷言（連線前）
    try:
        main_t, test_t = strict_parse(url), strict_parse(url_test)
    except ValueError as exc:
        print(f"URL 不合規：{exc}", file=sys.stderr)
        return 1
    SECRETS.extend([s for s in (main_t["password"], test_t["password"]) if s])
    if main_t["host"] not in LOOPBACK or main_t["dbname"] != PROD_DB or test_t["dbname"] == main_t["dbname"]:
        print(f"目標斷言失敗：主機須為 loopback、庫名須為 {PROD_DB}、且與測試庫庫名不同；拒絕執行", file=sys.stderr)
        return 1
    try:
        conn = psycopg.connect(url, autocommit=False, connect_timeout=10)
    except psycopg.Error as exc:
        print(f"無法連線（{type(exc).__name__}）：{mask(first_line(str(exc)))}", file=sys.stderr)
        return 1
    try:
        conn.read_only = True
        with conn.cursor() as cur:
            db = scalar(cur, "SELECT current_database()")
            ro = scalar(cur, "SHOW transaction_read_only")
            LOG.add("A1", "目標斷言（loopback 主機、URL 庫名、current_database() = 正式庫、與測試庫庫名不同）並設為唯讀",
                    db == PROD_DB and ro == "on", f"host={main_t['host']} port={main_t['port']} db={db} transaction_read_only={ro}")
            if db != PROD_DB or ro != "on":
                return finish(intro)
            # A2：擴充
            cur.execute("SELECT e.extversion, n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'")
            ext = cur.fetchone()
            ext_ok = False
            if ext:
                m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", ext[0])
                ext_ok = bool(m) and tuple(map(int, m.groups())) >= MIN_PGVECTOR and ext[1] == "public"
                intro.append(f"vector 擴充 {ext[0]}（schema {ext[1]}）")
            LOG.add("A2", "vector 擴充存在、在 public、extversion >= 0.8.2（整數 tuple 比較）", ext_ok, f"{ext}")
            # A3：schema
            problems = schema_problems(cur, "parents") + schema_problems(cur, "children")
            LOG.add("A3", "兩表 schema 與外鍵（NO ACTION）、CHECK、索引核對", not problems, "；".join(problems)[:300])
            if problems:
                return finish(intro)
            # psycopg 3 的 cursor 在建立時複製連線當下的 adapters：註冊 vector 之後必須另開 cursor，
            # 舊的 cur 讀到的 embedding 會是字串。A4 以後（含讀向量的 A5、A10、A11）都在新 cursor 上執行。
            register_vector_info(conn, TypeInfo.fetch(conn, "public.vector"))
            with conn.cursor() as cur:
                version =json.loads((PROJECT_ROOT / "sources.json").read_text(encoding="utf-8"))["version"]
                p_path, c_path, e_path = artifact_paths(version)
                P, E = read_jsonl(p_path), read_jsonl(e_path)
                Crows = [{k: e[k] for k in CHILD_NAMES} for e in E]
                pair = (E[0]["model_name"], E[0]["model_revision"])
                intro.append(f"version {version}；產物 parents {len(P)}、children {len(Crows)}")

                # A4：筆數
                n_p = scalar(cur, "SELECT count(*) FROM rag.parents WHERE version = %s", (version,))
                n_c = scalar(cur, "SELECT count(*) FROM rag.children WHERE version = %s", (version,))
                t_p, t_c = scalar(cur, "SELECT count(*) FROM rag.parents"), scalar(cur, "SELECT count(*) FROM rag.children")
                LOG.add("A4", "筆數等於產物即時計算（不硬寫）", (n_p, n_c) == (len(P), len(Crows)),
                        f"parents {n_p}/{len(P)}、children {n_c}/{len(Crows)}；全表 {t_p}、{t_c}")
                if (t_p, t_c) != (n_p, n_c):
                    LOG.note(f"全表列數（{t_p}、{t_c}）多於 version {version} 的列數：資料庫內另有其他 version，指紋以 version 範圍為準")

                # A5：指紋
                vector_type_err = ""
                try:
                    prows = db_rows(cur, "parents", PARENT_NAMES, "parent_id", version)
                    crows = db_rows(cur, "children", CHILD_NAMES, "chunk_id", version)
                except VectorTypeError as exc:
                    vector_type_err = f"embedding 讀回型別 {exc}，預期 pgvector Vector（vector loader 未生效）"
                    crows = []
                if vector_type_err:
                    LOG.add("A5", "內容指紋：資料庫端（該 version）對產物端（parents、children）", False, vector_type_err)
                else:
                    fp_db = (fingerprint(prows, PARENT_FP_COLUMNS, "parent_id", True), fingerprint(crows, CHILD_FP_COLUMNS, "chunk_id", True))
                    fp_art = (fingerprint(P, PARENT_FP_COLUMNS, "parent_id"), fingerprint(Crows, CHILD_FP_COLUMNS, "chunk_id"))
                    LOG.add("A5", "內容指紋：資料庫端（該 version）對產物端（parents、children）", fp_db == fp_art,
                            f"parents {fp_db[0][:16]} / {fp_art[0][:16]}；children {fp_db[1][:16]} / {fp_art[1][:16]}")
                # A6：model 組
                cur.execute("SELECT count(DISTINCT (model_name, model_revision)), min(model_name), min(model_revision), "
                            "bool_and(model_name <> '' AND model_revision <> '') FROM rag.children")
                n, name, rev, nonempty = cur.fetchone()
                LOG.add("A6", "全表只有一組非空 (model_name, model_revision)，且等於向量檔的唯一組", n == 1 and bool(nonempty) and (name, rev) == pair, f"組數 {n}")
                # A7：完整性
                orphans = scalar(cur, "SELECT count(*) FROM rag.children c LEFT JOIN rag.parents p ON p.parent_id = c.parent_id WHERE p.parent_id IS NULL")
                childless = scalar(cur, "SELECT count(*) FROM rag.parents p WHERE NOT EXISTS (SELECT 1 FROM rag.children c WHERE c.parent_id = p.parent_id)")
                sub = scalar(cur, "SELECT count(*) FROM rag.children c JOIN rag.parents p ON p.parent_id = c.parent_id WHERE position(c.text in p.text) > 0")
                LOG.add("A7", "孤兒 child 0、無 child 的 parent 0、child.text 皆為 parent.text 的子字串",
                        (orphans, childless, sub) == (0, 0, t_c), f"孤兒 {orphans}、無 child 的 parent {childless}、子字串 {sub}/{t_c}")
                # A8：version
                versions = sorted(r[0] for r in (cur.execute("SELECT DISTINCT version FROM rag.parents UNION SELECT DISTINCT version FROM rag.children") or cur).fetchall())
                LOG.add("A8", "資料庫內的 version 單一且等於 sources.json 的值", versions == [version], f"{versions}")
                # A9：text 往返
                bad = 0
                for table, rows, key in (("parents", P, "parent_id"), ("children", Crows, "chunk_id")):
                    cur.execute(f"SELECT {key}, text, length(text), octet_length(text) FROM rag.{table} WHERE version = %s", (version,))
                    got = {r[0]: r[1:] for r in cur.fetchall()}
                    bad += sum(1 for r in rows if got.get(r[key]) != (r["text"], len(r["text"]), len(r["text"].encode("utf-8"))))
                LOG.add("A9", "text 往返：內容、字元長度、位元組長度逐列相等", bad == 0, f"不符 {bad} 列")
                # A10：向量往返
                got_v = {r["chunk_id"]: r["embedding"] for r in crows}
                bad = sum(1 for r in Crows if r["chunk_id"] not in got_v or got_v[r["chunk_id"]].astype("<f4").tobytes() != f32_bytes(r["embedding"]))
                LOG.add("A10", "向量往返（float32 位元組相等，全部 child）", bad == 0 and not vector_type_err,
                        vector_type_err or f"不符 {bad}/{len(Crows)}")
                # A11：最近鄰
                if vector_type_err:
                    LOG.add("A11", f"最近鄰排序（同 V5；{D6_SENTENCE}）且沒有向量索引", False, "未執行：" + vector_type_err)
                else:
                    ids = [r["chunk_id"] for r in Crows]
                    D = cosine_distance_matrix(np.array([r["embedding"] for r in Crows]), np.array([r["embedding"] for r in Crows]))
                    bad_top = bad_rank = 0
                    max_dev = 0.0
                    for i, r in enumerate(Crows):
                        cur.execute("SELECT chunk_id, embedding OPERATOR(public.<=>) %s AS d FROM rag.children WHERE version = %s ORDER BY d LIMIT %s",
                                    (Vector(f32(r["embedding"])), version, NN_TOP_K))
                        got = cur.fetchall()
                        if ids.index(got[0][0]) not in tie_set(D[i]):
                            bad_top += 1
                        ref = np.sort(D[i])[:NN_TOP_K]
                        devs = [abs(float(gd) - float(rd)) for (_, gd), rd in zip(got, ref)]
                        max_dev = max(max_dev, *devs)
                        bad_rank += any(d > NN_TOLERANCE for d in devs)
                    cur.execute("SELECT indexdef FROM pg_indexes WHERE schemaname = 'rag' AND tablename = 'children'")
                    defs = " ".join(r[0].lower() for r in cur.fetchall())
                    LOG.add("A11", f"最近鄰排序（同 V5；{D6_SENTENCE}）且沒有向量索引", bad_top == 0 and bad_rank == 0 and "hnsw" not in defs and "ivfflat" not in defs,
                            f"{len(Crows)} 筆查詢；第一名不在並列組 {bad_top}、距離超出容差 {bad_rank}；最大距離偏差 {max_dev:.3g}；容差 {NN_TOLERANCE:g}")
                    if max_dev > NN_ATTENTION:
                        LOG.note(f"A11 最大距離偏差 {max_dev:.3g} 超過 {NN_ATTENTION:g}：須回報使用者，不得自行放寬容差")
        # A12：腳本自身
        own = Path(__file__).read_text(encoding="utf-8")
        hits = sorted(set(WRITE_RE.findall(own)))
        with conn.cursor() as cur:
            ro_now = scalar(cur, "SHOW transaction_read_only")
        LOG.add("A12", "本腳本原始碼不含寫入類關鍵字（大寫 SQL 寫法）、連線維持唯讀", not hits and ro_now == "on", f"命中 {hits}；transaction_read_only={ro_now}")
        conn.rollback()
    except psycopg.Error as exc:
        LOG.add("A12", "核對過程發生資料庫錯誤", False, f"{type(exc).__name__}：{mask(first_line(str(exc)))}")
    except Exception as exc:   # noqa: BLE001（未預期的例外：不再送任何 SQL，仍寫出報告並以 1 結束）
        LOG.add("中止", "核對中止（未預期的例外）", False, f"{type(exc).__name__}：{mask(first_line(str(exc)))}")
    finally:
        conn.close()
    return finish(intro)


def finish(intro: list[str]) -> int:
    write_text(REPORT_PATH, LOG.render("正式庫核對報告（audit_index.py，唯讀）",
                                       ["只做 SELECT；目標庫 " + PROD_DB] + intro + [f"容差：|d − d_min| ≤ {NN_TOLERANCE:g}"]))
    print(f"     報告：{REPORT_PATH.relative_to(PROJECT_ROOT)}")
    failed = LOG.failed
    print(f"[audit_index] 共 {len(LOG.results)} 項，不通過 {len(failed)} 項")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
