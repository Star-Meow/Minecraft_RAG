"""[7] 入庫的獨立驗證腳本（只連測試庫 minecraft_rag_test）。

- 不 import index_chunks.py 的判斷邏輯；只為了走同一條寫入路徑而 import ensure_schema、write_update、
  write_rebuild，並為負向測試 import 受測對象 check_table_schema、evaluate_extension_version（計畫疑義 1）。
  其餘案例一律以子行程執行真正的 CLI（在沒有 .env 的暫存專案根副本內），不留測試後門。
- URL 解析、指紋與暴力 cosine 都由本腳本（與 index_check_utils.py）自己計算。
- 預設跑全部（V1～V23，需要 .env 與測試庫，由使用者執行）；--offline 只跑不讀 .env、不連線的項目：
  V13a（連線前即中止的負向案例）、V15、V17、V18、V19。
- V5 只證明資料庫排序等於暴力計算，不證明檢索品質（D6）。
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import unquote, urlsplit, urlunsplit

import numpy as np

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))

from index_check_utils import (CHILD_FP_COLUMNS, D6_SENTENCE, NN_ATTENTION, NN_TOLERANCE, NN_TOP_K,  # noqa: E402
                               PARENT_FP_COLUMNS, PROJECT_ROOT, ResultLog, artifact_paths,
                               cosine_distance_matrix, f32, f32_bytes, fingerprint, first_line,
                               mask_secrets, read_jsonl, tie_set, write_text)

INDEX_SRC = SRC_DIR / "index_chunks.py"
REPORT_PATH = PROJECT_ROOT / "reports" / "verify_index_report.md"
TEST_DB = "minecraft_rag_test"
PROD_DB = "minecraft_rag"
LOOPBACK = ("127.0.0.1", "localhost")
VERSION_B = "9.9.9-test"                      # V20 的替身 version
OTHER_REVISION = "other-revision-for-test"
FORBIDDEN_MODULES = {"torch", "transformers", "sentence_transformers", "FlagEmbedding", "chunk_pages",
                     "embed_chunks", "tokenizers"}
FORBIDDEN_SQL = re.compile(r"\b(DROP|TRUNCATE|ALTER|CASCADE)\b", re.IGNORECASE)
PARENT_NAMES = [c for c, _ in PARENT_FP_COLUMNS]
CHILD_NAMES = [c for c, _ in CHILD_FP_COLUMNS]

SECRETS: list[str] = []                       # 需遮罩的密碼（真實與哨兵）
CAPTURED: list[str] = []                      # 所有子行程的 stdout／stderr，供 V14 掃描
TEMP_ROOTS: list[Path] = []

LOG = ResultLog()


def sub_env(extra: Optional[dict] = None, strip_db: bool = True) -> dict:
    """所有子行程共用的環境：強制 UTF-8 輸出（避免 PowerShell 下的 cp950）；預設移除 PG* 與資料庫 URL 變數。"""
    env = {k: v for k, v in os.environ.items()
           if not strip_db or not (k.startswith("PG") or k in ("DATABASE_URL", "DATABASE_URL_TEST"))}
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    env.update(extra or {})
    return env


def run_sub(cmd: list[str], env: dict, timeout: int = 300) -> subprocess.CompletedProcess:
    """所有 subprocess.run 的唯一入口：UTF-8 解碼、無法解碼的位元組以 ? 取代（不崩潰）；stdout／stderr 保證是 str。"""
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, timeout=timeout)
    proc.stdout, proc.stderr = proc.stdout or "", proc.stderr or ""
    return proc


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def strict_parse(url: str) -> dict:
    """自己的 URL 解析（urllib；與 index_chunks 使用的 libpq 解析器不同實作）。拒絕查詢字串與多主機。"""
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
    return {"host": host, "port": sp.port, "dbname": dbname,
            "password": unquote(sp.password) if sp.password else None}


def mask(text: str) -> str:
    return mask_secrets(text, SECRETS)


def make_spy_dir(root: Path) -> Path:
    """建立 sitecustomize.py：替換 psycopg.connect，每次呼叫在標記檔寫一行（不含 conninfo）。"""
    spy = root / "spy"
    spy.mkdir(parents=True, exist_ok=True)
    (spy / "sitecustomize.py").write_text(
        "import os\n"
        "_m = os.environ.get('INDEX_SPY_FILE')\n"
        "if _m:\n"
        "    import psycopg\n"
        "    _orig = psycopg.Connection.connect\n"
        "    def _cm(cls, *a, **k):\n"
        "        with open(_m, 'a') as f:\n"
        "            f.write('x\\n')\n"
        "        return _orig(*a, **k)\n"
        "    psycopg.Connection.connect = classmethod(_cm)\n"
        "    psycopg.connect = psycopg.Connection.connect\n", encoding="utf-8")
    return spy


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class TempRoot:
    """暫存的專案根副本：index_chunks.py 副本、sources.json、可替換的產物；沒有 .env。"""

    def __init__(self, version: str) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="idx_verify_"))
        TEMP_ROOTS.append(self.root)
        (self.root / "src").mkdir()
        shutil.copy2(INDEX_SRC, self.root / "src" / "index_chunks.py")
        shutil.copy2(PROJECT_ROOT / "sources.json", self.root / "sources.json")
        self.version = version
        self.spy_dir = make_spy_dir(self.root)
        self.spy_file = self.root / "spy_calls.txt"

    def set_artifacts(self, parents: list[dict], children: list[dict], embeddings: list[dict]) -> None:
        p, c, e = artifact_paths(self.version, self.root)
        write_jsonl(p, parents)
        write_jsonl(c, children)
        write_jsonl(e, embeddings)

    def run(self, args: list[str], env_extra: Optional[dict] = None) -> subprocess.CompletedProcess:
        env = sub_env({"PYTHONPATH": str(self.spy_dir), "INDEX_SPY_FILE": str(self.spy_file), **(env_extra or {})})
        if self.spy_file.exists():
            self.spy_file.unlink()
        proc = run_sub([sys.executable, str(self.root / "src" / "index_chunks.py")] + args, env)
        CAPTURED.append(proc.stdout + "\n" + proc.stderr)
        return proc

    def spy_calls(self) -> int:
        return len(self.spy_file.read_text().splitlines()) if self.spy_file.exists() else 0

    def report_text(self) -> Optional[str]:
        p = self.root / "reports" / "index_report.md"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def load_real_artifacts() -> tuple[str, list[dict], list[dict], list[dict]]:
    version = json.loads((PROJECT_ROOT / "sources.json").read_text(encoding="utf-8"))["version"]
    p, c, e = artifact_paths(version)
    return version, read_jsonl(p), read_jsonl(c), read_jsonl(e)


# ---------------------------------------------------------------------------
# 離線項目：V13a、V15、V17、V18、V19（不讀 .env、不連線）
# ---------------------------------------------------------------------------
REPORT_FIELDS = ["# 入庫報告", "模式", "version", "結束碼", "庫名", "是否 loopback", "指紋比對結果"]
REPORT_CHECKS: list[tuple[str, bool, str]] = []   # V16 累積：(案例, 通過, 說明)


def check_report(case: str, root: TempRoot) -> None:
    """V16：CLI 寫出的報告欄位齊全，且不含密碼或完整 URL。"""
    text = root.report_text()
    if text is None:
        REPORT_CHECKS.append((case, False, "未產生報告"))
        return
    missing = [f for f in REPORT_FIELDS if f not in text]
    leaked = [s for s in SECRETS if s and s in text] + re.findall(r"postgres(?:ql)?://\S+", text)
    REPORT_CHECKS.append((case, not missing and not leaked,
                          f"缺欄位 {missing}" if missing else ("含密碼或 URL" if leaked else "ok")))


def mutate_cases(P: list[dict], C: list[dict], E: list[dict]):
    """V19 的損壞案例：(名稱, 變形函式, stderr 應含的關鍵字)。每個變形只複製被改的列。"""
    def with_(rows: list[dict], i: int, **kw) -> list[dict]:
        out = list(rows)
        out[i] = {**rows[i], **kw}
        return out

    yield "orphan_child", lambda: (P, with_(C, 0, parent_id="x:orphan"), with_(E, 0, parent_id="x:orphan")), "孤兒"
    yield "version_mixed", lambda: (with_(P, 0, version="9.9.9"), C, E), "version"
    yield "duplicate_chunk_id", lambda: (P, with_(C, 1, chunk_id=C[0]["chunk_id"]),
                                         with_(E, 1, chunk_id=C[0]["chunk_id"])), "重複"
    yield "dim_1023", lambda: (P, C, with_(E, 3, embedding=E[3]["embedding"][:1023])), "維度"
    nan_vec = list(E[2]["embedding"])
    nan_vec[5] = float("nan")
    yield "nan_vector", lambda: (P, C, with_(E, 2, embedding=nan_vec)), "非有限"
    yield "nul_char", lambda: (with_(P, 0, text=P[0]["text"] + "\x00"), C, E), "NUL"
    yield "childless_parent", lambda: (P + [{**P[1], "parent_id": P[1]["parent_id"] + "x"}], C, E), "沒有 child"
    yield "child_not_substring", lambda: (P, with_(C, 0, text="這段文字不在 parent 內"),
                                          with_(E, 0, text="這段文字不在 parent 內")), "子字串"
    yield "order_swapped", lambda: (P, C, [E[1], E[0]] + E[2:]), "順序"
    yield "model_mixed", lambda: (P, C, with_(E, 0, model_revision=OTHER_REVISION)), "model 組"
    yield "norm_off", lambda: (P, C, with_(E, 1, embedding=[x * 2 for x in E[1]["embedding"]])), "norm"
    yield "embedding_input_mismatch", lambda: (P, C, with_(E, 4, embedding_input="x")), "embedding_input"


def run_v19(version: str, P: list[dict], C: list[dict], E: list[dict]) -> None:
    """V19：入庫前驗證先於連線。每個案例：結束碼 1、訊息指出原因、未連線、尚未讀 .env。"""
    root = TempRoot(version)
    try:
        # 對照組：乾淨資料通過入庫前驗證，之後才因缺少連線設定而中止（證明驗證沒有誤擋）
        root.set_artifacts(P, C, E)
        proc = root.run(["--mode", "update"])
        ok = proc.returncode == 1 and "缺少設定" in proc.stderr and root.spy_calls() == 0
        LOG.add("V19", "對照組：乾淨資料通過入庫前驗證後才因缺少設定中止", ok,
                f"exit={proc.returncode}、spy={root.spy_calls()}、{first_line(mask(proc.stderr))}")
        check_report("V19 對照組", root)
        for name, build, keyword in mutate_cases(P, C, E):
            p2, c2, e2 = build()
            root.set_artifacts(p2, c2, e2)
            proc = root.run(["--mode", "update"])
            ok = (proc.returncode == 1 and keyword in proc.stderr and "缺少設定" not in proc.stderr
                  and root.spy_calls() == 0)
            LOG.add("V19", f"損壞案例 {name}", ok,
                    f"exit={proc.returncode}、含關鍵字「{keyword}」={keyword in proc.stderr}、"
                    f"未讀 .env={'缺少設定' not in proc.stderr}、spy={root.spy_calls()}")
            check_report(f"V19 {name}", root)
    finally:
        root.cleanup()


def run_v13a(version: str, P: list[dict], C: list[dict], E: list[dict]) -> None:
    """V13a：連線前就該中止的負向案例（子行程＋spy）；並以自己的解析器交叉比對。"""
    root = TempRoot(version)
    s1, s2 = "SentinelPw1_x", "SentinelPw2_y"
    SECRETS.extend([s1, s2])
    good_test = f"postgresql://u:{s1}@127.0.0.1:5433/{TEST_DB}"
    try:
        root.set_artifacts(P, C, E)
        # spy 的正向對照：用會立刻被 libpq 拒絕的 conninfo（不產生任何網路連線）
        probe = run_sub([sys.executable, "-c", "import psycopg\ntry:\n    psycopg.connect('badkeyxyz=1')\n"
                         "except Exception:\n    pass"],
                        sub_env({"PYTHONPATH": str(root.spy_dir), "INDEX_SPY_FILE": str(root.spy_file)}, strip_db=False))
        LOG.add("V13a", "spy 正向對照（呼叫 psycopg.connect 會被記錄）", root.spy_calls() >= 1,
                f"記錄 {root.spy_calls()} 次")
        cases: list[tuple[str, list[str], dict, int, str, Optional[str]]] = [
            ("未傳 --mode", [], {}, 2, "--mode", None),
            ("非法 --mode", ["--mode", "foo"], {}, 2, "--mode", None),
            ("多餘的旗標（無後門）", ["--mode", "update", "--db", "x"], {}, 2, "unrecognized", None),
            ("主機非 loopback", ["--mode", "update"],
             {"DATABASE_URL": f"postgresql://u:{s1}@10.0.0.5:5433/{PROD_DB}", "DATABASE_URL_TEST": good_test},
             1, "允許清單", f"postgresql://u:{s1}@10.0.0.5:5433/{PROD_DB}"),
            ("以查詢字串覆蓋主機", ["--mode", "update"],
             {"DATABASE_URL": f"postgresql://u:{s1}@127.0.0.1:5433/{PROD_DB}?host=evil.example",
              "DATABASE_URL_TEST": good_test}, 1, "允許清單",
             f"postgresql://u:{s1}@127.0.0.1:5433/{PROD_DB}?host=evil.example"),
            ("查詢字串帶 options", ["--mode", "update"],
             {"DATABASE_URL": f"postgresql://u:{s1}@127.0.0.1:5433/{PROD_DB}?options=-csearch_path%3Dx",
              "DATABASE_URL_TEST": good_test}, 1, "不允許的連線參數",
             f"postgresql://u:{s1}@127.0.0.1:5433/{PROD_DB}?options=-csearch_path%3Dx"),
            ("多主機", ["--mode", "update"],
             {"DATABASE_URL": f"postgresql://u:{s1}@127.0.0.1,10.0.0.5:5433/{PROD_DB}",
              "DATABASE_URL_TEST": good_test}, 1, "單一值",
             f"postgresql://u:{s1}@127.0.0.1,10.0.0.5:5433/{PROD_DB}"),
            ("兩個 URL 同庫名", ["--mode", "update"],
             {"DATABASE_URL": f"postgresql://u:{s1}@127.0.0.1:5433/{PROD_DB}",
              "DATABASE_URL_TEST": f"postgresql://u:{s2}@127.0.0.1:5433/{PROD_DB}"}, 1, "同一個庫名", None),
            ("缺 DATABASE_URL_TEST", ["--mode", "update"],
             {"DATABASE_URL": f"postgresql://u:{s1}@127.0.0.1:5433/{PROD_DB}"}, 1, "DATABASE_URL_TEST", None),
            ("值含變數展開語法", ["--mode", "update"],
             {"DATABASE_URL": "${SOME_VAR}", "DATABASE_URL_TEST": good_test}, 1, "變數展開", None),
        ]
        for name, args, env, code, keyword, strict_url in cases:
            proc = root.run(args, env)
            out = proc.stdout + proc.stderr
            leaked = [s for s in (s1, s2) if s in out]
            ok = (proc.returncode == code and keyword in out and root.spy_calls() == 0 and not leaked)
            detail = f"exit={proc.returncode}、關鍵字「{keyword}」={keyword in out}、spy={root.spy_calls()}、洩漏={bool(leaked)}"
            if strict_url is not None:     # 交叉比對：自己的解析器也必須拒絕
                try:
                    strict_parse(strict_url)
                    host_ok = urlsplit(strict_url).hostname in LOOPBACK
                    cross = not host_ok       # 通過 urllib 解析但主機非 loopback → 仍須拒絕
                except ValueError:
                    cross = True
                ok = ok and cross
                detail += f"、自己的解析器同樣拒絕={cross}"
            LOG.add("V13a", f"連線前中止：{name}", ok, detail)
            if code == 1:
                check_report(f"V13a {name}", root)
        # 缺 key 的訊息不回印另一個 URL 的任何字元（V14 的一部分）
        proc = root.run(["--mode", "update"], {"DATABASE_URL": f"postgresql://u:{s1}@127.0.0.1:5433/{PROD_DB}"})
        LOG.add("V14", "缺 key 訊息不含現有值", s1 not in proc.stdout + proc.stderr and "127.0.0.1" not in proc.stderr,
                first_line(proc.stderr))
    finally:
        root.cleanup()


def _imports_of(tree: ast.AST) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def run_v15(version: str, P: list[dict], C: list[dict], E: list[dict]) -> None:
    """V15：index_chunks.py 不載入模型。靜態（AST）＋動態（子行程結束時的 sys.modules）。"""
    tree = ast.parse(INDEX_SRC.read_text(encoding="utf-8"))
    bad = _imports_of(tree) & FORBIDDEN_MODULES
    LOG.add("V15", "靜態：沒有模型、tokenizer、chunk_pages、embed_chunks 的 import", not bad, f"違規 {sorted(bad)}")
    root = TempRoot(version)
    try:
        root.set_artifacts(P, C, E)
        wrapper = ("import json, runpy, sys\n"
                   "sys.argv = [sys.argv[1], '--mode', 'update']\n"
                   "try:\n    runpy.run_path(sys.argv[0], run_name='__main__')\nexcept SystemExit:\n    pass\n"
                   f"print('LOADED=' + json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in {sorted(FORBIDDEN_MODULES)!r})))\n")
        for label, args in (("未傳 --mode 的中止路徑", None), ("通過驗證後缺設定的中止路徑", "update")):
            script = wrapper if args else wrapper.replace("'--mode', 'update'", "'--bogus'")
            try:
                proc = run_sub([sys.executable, "-c", script, str(root.root / "src" / "index_chunks.py")], sub_env())
                CAPTURED.append((proc.stdout or "") + (proc.stderr or ""))
                m = re.search(r"LOADED=(.*)", proc.stdout or "")
                loaded = json.loads(m.group(1)) if m else None
                detail = f"載入 {loaded}" if m else f"子行程輸出不完整（無 LOADED 行），exit={proc.returncode}：{first_line(proc.stderr)}"
            except Exception as exc:   # noqa: BLE001（子行程逾時、輸出解析失敗等：記為不通過，不中斷）
                loaded, detail = None, f"{type(exc).__name__}：{first_line(str(exc))}"
            LOG.add("V15", f"動態：{label}沒有載入模型相關模組", loaded == [], detail)
    finally:
        root.cleanup()


def run_v17_v18() -> None:
    """V17、V18：原始碼靜態檢查（無破壞性 SQL、DELETE 皆限 version、無測試後門）。"""
    text = INDEX_SRC.read_text(encoding="utf-8")
    tree = ast.parse(text)
    hits = sorted({m.group(0).upper() for m in FORBIDDEN_SQL.finditer(text)})
    LOG.add("V17", "原始碼不含 DROP／TRUNCATE／ALTER／CASCADE", not hits, f"命中 {hits}")
    deletes = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and n.value.lstrip().upper().startswith("DELETE")]
    LOG.add("V17", "所有 DELETE 陳述式都含 version = %s", bool(deletes) and all("version = %s" in d for d in deletes),
            f"DELETE 陳述式 {len(deletes)} 個")

    # V18：參數、環境變數、庫名字面量、斷言不可被條件跳過
    add_args = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "add_argument"]
    flags = [a.value for n in add_args for a in n.args if isinstance(a, ast.Constant)]
    mode_kw = {k.arg: k.value for n in add_args for k in n.keywords}
    required = isinstance(mode_kw.get("required"), ast.Constant) and mode_kw["required"].value is True
    LOG.add("V18", "argparse 只有 --mode，且必填、無預設", flags == ["--mode"] and required and "default" not in mode_kw,
            f"旗標 {flags}、required={required}")
    env_like = sorted({n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                       and re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", n.value)})
    LOG.add("V18", "程式讀取的環境變數名稱 ⊆ {DATABASE_URL, DATABASE_URL_TEST}",
            set(env_like) <= {"DATABASE_URL", "DATABASE_URL_TEST"}, f"大寫常數字串 {env_like}")
    LOG.add("V18", "庫名字面量只有正式庫名，沒有測試庫名", PROD_DB in text and TEST_DB not in text, "")
    dotenv_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "load_dotenv"]
    LOG.add("V18", "load_dotenv 不使用 override 參數", bool(dotenv_calls) and all(not c.keywords for c in dotenv_calls),
            f"呼叫 {len(dotenv_calls)} 處")
    expected_assign = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "EXPECTED_DB" for t in n.targets)]
    LOG.add("V18", "EXPECTED_DB 在模組內寫死為 minecraft_rag（只有一處指定）",
            len(expected_assign) == 1 and isinstance(expected_assign[0].value, ast.Constant)
            and expected_assign[0].value.value == PROD_DB, "")
    guarded = {"assert_target_urls", "assert_server_database", "check_extension", "check_inputs", "load_settings"}
    skippable: list[str] = []
    parents_of: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents_of[id(child)] = node
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in guarded:
            cur: Optional[ast.AST] = node
            while cur is not None and not isinstance(cur, ast.FunctionDef):
                cur = parents_of.get(id(cur))
                if isinstance(cur, ast.If):
                    skippable.append(node.func.id)
                    break
    LOG.add("V18", "run() 內的斷言呼叫不在任何 if 之內（不可被旗標跳過）", not skippable, f"可被跳過者 {skippable}")


def run_offline() -> None:
    version, P, C, E = load_real_artifacts()
    groups: list[tuple[str, str, str, Callable[[], Any]]] = [
        ("V17／V18", "V17、V18（靜態）", "靜態檢查", run_v17_v18),
        ("V13a", "V13a（連線前中止的負向案例）", "連線前中止的負向案例", lambda: run_v13a(version, P, C, E)),
        ("V15", "V15（無模型載入）", "無模型載入", lambda: run_v15(version, P, C, E)),
        ("V19", "V19（入庫前驗證先於連線）", "入庫前驗證先於連線", lambda: run_v19(version, P, C, E)),
    ]
    for check_id, banner, title, fn in groups:
        print(f"[離線] {banner}")
        try:
            fn()
        except Exception as exc:   # noqa: BLE001（單組例外記為不通過，繼續其餘各組）
            LOG.add(check_id, title, False, f"執行時發生例外 {type(exc).__name__}：{mask(first_line(str(exc)))}"
                    + " | " + mask(traceback.format_exc().splitlines()[-3].strip()))
    ok = bool(REPORT_CHECKS) and all(ok for _, ok, _ in REPORT_CHECKS)
    LOG.add("V16", "CLI 報告欄位齊全且不含密碼或 URL（離線案例）", ok,
            f"{len(REPORT_CHECKS)} 份；異常 {[(c, d) for c, o, d in REPORT_CHECKS if not o][:3]}")
    leaked = [s for s in SECRETS if s and any(s in out for out in CAPTURED)]
    LOG.add("V14", "所有子行程輸出不含密碼（離線案例）", not leaked, f"掃描 {len(CAPTURED)} 份輸出")


# ---------------------------------------------------------------------------
# 連線項目（需要 .env 與測試庫；由使用者執行）
# ---------------------------------------------------------------------------
def db_rows(conn: Any, table: str, columns: list[str], key: str, versions: list[str]) -> list[dict]:
    """讀某表（限 versions）所有列；依主鍵位元組序排序；向量轉 float32 numpy。"""
    import psycopg  # noqa: F401
    sql = (f"SELECT {', '.join(columns)} FROM rag.{table} WHERE version = ANY(%s) "
           f'ORDER BY {key} COLLATE "C"')
    with conn.cursor() as cur:
        cur.execute(sql, (versions,))
        out = []
        for values in cur.fetchall():
            row = dict(zip(columns, values))
            if "embedding" in row:
                row["embedding"] = row["embedding"].to_numpy()
            out.append(row)
    return out


def db_fp(conn: Any, version: str) -> tuple[str, str]:
    """資料庫端指紋（parents、children），限 version。"""
    p = db_rows(conn, "parents", PARENT_NAMES, "parent_id", [version])
    c = db_rows(conn, "children", CHILD_NAMES, "chunk_id", [version])
    return (fingerprint(p, PARENT_FP_COLUMNS, "parent_id", True), fingerprint(c, CHILD_FP_COLUMNS, "chunk_id", True))


def art_fp(P: list[dict], Crows: list[dict]) -> tuple[str, str]:
    """產物端指紋。"""
    return (fingerprint(P, PARENT_FP_COLUMNS, "parent_id"), fingerprint(Crows, CHILD_FP_COLUMNS, "chunk_id"))


def child_rows_of(E: list[dict]) -> list[dict]:
    return [{k: e[k] for k in CHILD_NAMES} for e in E]


def scalar_count(conn: Any, sql: str, params: tuple = ()) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return int(cur.fetchone()[0])


class SqlTap:
    """包裝連線：記錄每個陳述式，並可在第 fail_at 個陳述式注入例外（只存在於本腳本）。"""

    def __init__(self, conn: Any, fail_at: Optional[int] = None) -> None:
        self._c, self.fail_at, self.n, self.sql = conn, fail_at, 0, []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def cursor(self, *a: Any, **k: Any) -> "TapCursor":
        return TapCursor(self._c.cursor(*a, **k), self)


class TapCursor:
    def __init__(self, cur: Any, tap: SqlTap) -> None:
        self._cur, self._tap = cur, tap

    def __enter__(self) -> "TapCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        self._cur.close()
        return False

    def execute(self, query: Any, params: Any = None, **kw: Any) -> "TapCursor":
        self._tap.n += 1
        self._tap.sql.append(str(query))
        if self._tap.fail_at == self._tap.n:
            raise RuntimeError("注入的故障")
        self._cur.execute(query, params, **kw)
        return self

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cur, name)


def connect_test(url_test: str) -> Any:
    import psycopg
    try:
        return psycopg.connect(url_test, autocommit=True, connect_timeout=10)
    except psycopg.Error as exc:
        raise SystemExit(f"無法連線測試庫（{type(exc).__name__}）：{mask(first_line(str(exc)))}") from None


def run_full(log_intro: list[str]) -> None:
    """V1～V23 全部項目（含離線項目）。"""
    import psycopg
    from dotenv import load_dotenv
    from pgvector import Vector
    from pgvector.psycopg.vector import register_vector_info
    from psycopg.types import TypeInfo

    load_dotenv(PROJECT_ROOT / ".env")
    url_test, url_main = os.environ.get("DATABASE_URL_TEST", ""), os.environ.get("DATABASE_URL", "")
    if not url_test or not url_main:
        raise SystemExit("缺少 DATABASE_URL 或 DATABASE_URL_TEST（只顯示 key 名稱；請在 .env 或 shell 設定）")
    # V1：D5-2 斷言（在任何寫入或清理之前）
    try:
        t, m = strict_parse(url_test), strict_parse(url_main)
    except ValueError as exc:
        raise SystemExit(f"URL 不合規：{exc}") from None
    SECRETS.extend([s for s in (t["password"], m["password"]) if s])
    if t["host"] not in LOOPBACK:
        raise SystemExit("DATABASE_URL_TEST 的主機必須是 127.0.0.1 或 localhost（D5-2）")
    if t["dbname"] == m["dbname"]:
        raise SystemExit("DATABASE_URL 與 DATABASE_URL_TEST 的庫名相同，拒絕執行（D5-2）")
    conn = connect_test(url_test)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            actual = cur.fetchone()[0]
        if actual != TEST_DB or t["dbname"] != TEST_DB:
            raise SystemExit(f"目標資料庫是 {actual!r}（URL 庫名 {t['dbname']!r}），預期 {TEST_DB!r}（D5-2）；拒絕執行")
        LOG.add("V1", "測試庫斷言（主機 loopback、current_database()、兩 URL 庫名不同）", True,
                f"host={t['host']} port={t['port']} db={actual}")
        with conn.cursor() as cur:
            cur.execute("SELECT e.extversion, n.nspname FROM pg_extension e JOIN pg_namespace n "
                        "ON n.oid = e.extnamespace WHERE e.extname = 'vector'")
            ext = cur.fetchone()
        if ext is None:
            raise SystemExit("測試庫沒有 vector 擴充：請手動執行 CREATE EXTENSION IF NOT EXISTS vector;（D7）")
        log_intro.append(f"vector 擴充 {ext[0]}（schema {ext[1]}）")
        register_vector_info(conn, TypeInfo.fetch(conn, "public.vector"))
        sys.path.insert(0, str(SRC_DIR))
        import index_chunks as ic   # 只用於：ensure_schema、write_update、write_rebuild；及負向測試的受測對象

        version, P, C, E = load_real_artifacts()
        Crows = child_rows_of(E)
        pair = (E[0]["model_name"], E[0]["model_revision"])
        versions = [version, VERSION_B]

        def clean() -> None:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rag.children WHERE version = ANY(%s)", (versions,))
                cur.execute("DELETE FROM rag.parents WHERE version = ANY(%s)", (versions,))

        def rebuild_base() -> Any:
            clean()
            return ic.write_rebuild(conn, version, P, Crows)

        def guarded(check_id: str, title: str, fn: Callable[[], Any]) -> None:
            try:
                fn()
            except SystemExit:
                raise
            except Exception as exc:   # noqa: BLE001
                LOG.add(check_id, title, False, f"執行時發生例外 {type(exc).__name__}：{mask(first_line(str(exc)))}"
                        + " | " + mask(traceback.format_exc().splitlines()[-3].strip()))

        with conn.transaction():
            ic.ensure_schema(conn)
        clean()
        left = scalar_count(conn, "SELECT count(*) FROM rag.parents") + scalar_count(conn, "SELECT count(*) FROM rag.children")

        # V22：空表 update（Q1：視同全部新增）
        def v22() -> None:
            if left != 0:
                LOG.add("V22", "空表 update（前置：兩表清空）", False, f"測試庫含非本腳本版本的資料 {left} 列，無法在空表上測試")
                return
            counts = ic.write_update(conn, version, P, Crows)
            ok = (counts.parents.inserted == len(P) and counts.children.inserted == len(C)
                  and counts.parents.updated == counts.parents.deleted == counts.children.updated == counts.children.deleted == 0
                  and db_fp(conn, version) == art_fp(P, Crows))
            LOG.add("V22", "空表 update 視同全部新增（Q1），內容與產物一致", ok,
                    f"新增 parents {counts.parents.inserted}、children {counts.children.inserted}")
        guarded("V22", "空表 update", v22)

        # V12 對帳（S3）：這次 rebuild 之前不 clean()；表內必須有已知筆數的該 version 資料。
        # V22 成功時表內即為其寫入的資料；V22 被跳過或失敗而表內沒有該 version 資料時，先以 write_update 寫入一份。
        def version_rows() -> tuple[int, int]:
            return (scalar_count(conn, "SELECT count(*) FROM rag.parents WHERE version = %s", (version,)),
                    scalar_count(conn, "SELECT count(*) FROM rag.children WHERE version = %s", (version,)))

        seeded = False
        if version_rows() == (0, 0):
            ic.write_update(conn, version, P, Crows)
            seeded = True
        measured_before = version_rows()                    # 實測：rebuild 前該 version 的列數
        base_counts = ic.write_rebuild(conn, version, P, Crows)
        base_fp = art_fp(P, Crows)

        # V2～V7、V23：基準狀態（rebuild 後）
        def v2() -> None:
            n_p = scalar_count(conn, "SELECT count(*) FROM rag.parents WHERE version = %s", (version,))
            n_c = scalar_count(conn, "SELECT count(*) FROM rag.children WHERE version = %s", (version,))
            t_p, t_c = (scalar_count(conn, "SELECT count(*) FROM rag.parents"), scalar_count(conn, "SELECT count(*) FROM rag.children"))
            LOG.add("V2", "筆數等於產物即時計算（不硬寫）", (n_p, n_c, t_p, t_c) == (len(P), len(C), len(P), len(C)),
                    f"parents {n_p}/{len(P)}、children {n_c}/{len(C)}（全表 {t_p}、{t_c}）")
            bp, bc = base_counts.parents, base_counts.children
            reconciled = (measured_before[0] > 0 and measured_before[1] > 0       # 實測值為 0 不得視為通過
                          and (bp.deleted_before, bp.deleted) == (measured_before[0], measured_before[0])
                          and (bc.deleted_before, bc.deleted) == (measured_before[1], measured_before[1]))
            LOG.add("V12", "rebuild 的刪除前列數與各表刪除筆數對帳（S3）", reconciled,
                    f"rebuild 前實測 parents {measured_before[0]}、children {measured_before[1]}；"
                    f"deleted_before {bp.deleted_before}/{bc.deleted_before}、deleted {bp.deleted}/{bc.deleted}"
                    f"（資料來源：{'V22 之外另寫入一份' if seeded else 'V22 寫入的資料'}）")
        guarded("V2", "筆數", v2)

        def v3() -> None:
            bad = 0
            for table, rows, key in (("parents", P, "parent_id"), ("children", Crows, "chunk_id")):
                with conn.cursor() as cur:
                    cur.execute(f"SELECT {key}, text, length(text), octet_length(text) FROM rag.{table} WHERE version = %s", (version,))
                    got = {r[0]: r[1:] for r in cur.fetchall()}
                for r in rows:
                    g = got.get(r[key])
                    if g is None or g != (r["text"], len(r["text"]), len(r["text"].encode("utf-8"))):
                        bad += 1
            LOG.add("V3", "text 往返：內容、字元長度、位元組長度逐列相等", bad == 0, f"不符 {bad} 列")
        guarded("V3", "text 往返", v3)

        def v4() -> None:
            cols_ok = True
            for table, names in (("parents", PARENT_NAMES), ("children", CHILD_NAMES)):
                with conn.cursor() as cur:
                    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'rag' "
                                "AND table_name = %s ORDER BY ordinal_position", (table,))
                    cols_ok &= [r[0] for r in cur.fetchall()] == names
            scalar_bad = 0
            for table, names, rows, key in (("parents", PARENT_NAMES, P, "parent_id"),
                                            ("children", [n for n in CHILD_NAMES if n != "embedding"], Crows, "chunk_id")):
                got = {r[key]: r for r in db_rows(conn, table, names, key, [version])}
                for r in rows:
                    if r[key] not in got or any(got[r[key]][n] != r[n] for n in names):
                        scalar_bad += 1
            LOG.add("V4", "欄位清單（含順序）與純量欄位往返；資料庫沒有 embedding_input 欄", cols_ok and scalar_bad == 0,
                    f"欄位相符={cols_ok}、純量不符 {scalar_bad} 列")
        guarded("V4", "純量欄位", v4)

        def v23() -> None:
            got = {r["chunk_id"]: r["embedding"] for r in db_rows(conn, "children", ["chunk_id", "embedding"], "chunk_id", [version])}
            bad = sum(1 for r in Crows if r["chunk_id"] not in got or got[r["chunk_id"]].astype("<f4").tobytes() != f32_bytes(r["embedding"]))
            LOG.add("V23", "向量往返（float32 位元組相等，全部 child）", bad == 0, f"不符 {bad}/{len(Crows)}")
        guarded("V23", "向量往返", v23)

        def v6() -> None:
            ok = db_fp(conn, version) == base_fp
            LOG.add("V6", "內容指紋：資料庫端對產物端（parents、children）", ok, f"parents {base_fp[0][:16]}、children {base_fp[1][:16]}")
            expected_cols = [(n, "x") for n in CHILD_NAMES]
            LOG.add("V6", "指紋序列化欄位清單等於資料庫欄位清單", [c for c, _ in CHILD_FP_COLUMNS] == [c for c, _ in expected_cols]
                    and [c for c, _ in PARENT_FP_COLUMNS] == PARENT_NAMES, "")
        guarded("V6", "內容指紋", v6)

        def v7() -> None:
            with conn.cursor() as cur:
                cur.execute("SELECT count(DISTINCT (model_name, model_revision)), min(model_name), min(model_revision), "
                            "bool_and(model_name <> '' AND model_revision <> '') FROM rag.children")
                n, name, rev, nonempty = cur.fetchone()
            LOG.add("V7", "全表只有一組非空 (model_name, model_revision)，且等於產物端唯一組（不寫死 revision）",
                    n == 1 and bool(nonempty) and (name, rev) == pair, f"組數 {n}")
        guarded("V7", "單一 model 組", v7)

        def v5(table_label: str = "V5") -> None:
            ids = [r["chunk_id"] for r in Crows]
            D = cosine_distance_matrix(np.array([r["embedding"] for r in Crows]), np.array([r["embedding"] for r in Crows]))
            max_dev, bad_top, bad_rank = 0.0, 0, 0
            with conn.cursor() as cur:
                for i, r in enumerate(Crows):
                    q = Vector(f32(r["embedding"]))
                    cur.execute("SELECT chunk_id, embedding OPERATOR(public.<=>) %s AS d FROM rag.children "
                                "ORDER BY d LIMIT %s", (q, NN_TOP_K))
                    got = cur.fetchall()
                    ties = tie_set(D[i])
                    if ids.index(got[0][0]) not in ties:
                        bad_top += 1
                    ref = np.sort(D[i])[:NN_TOP_K]
                    for (gid, gd), rd in zip(got, ref):
                        max_dev = max(max_dev, abs(float(gd) - float(rd)))
                    if any(abs(float(gd) - float(rd)) > NN_TOLERANCE for (gid, gd), rd in zip(got, ref)):
                        bad_rank += 1
                cur.execute("SELECT indexdef FROM pg_indexes WHERE schemaname = 'rag' AND tablename = 'children'")
                defs = " ".join(x[0].lower() for x in cur.fetchall())
            no_vec_index = "hnsw" not in defs and "ivfflat" not in defs
            LOG.add(table_label, "最近鄰排序：第一名在暴力最小距離並列組內、前 5 名距離逐名在容差內、無向量索引（"
                    + D6_SENTENCE + "）", bad_top == 0 and bad_rank == 0 and no_vec_index,
                    f"{len(Crows)} 筆查詢；第一名不在並列組 {bad_top}、距離超出容差 {bad_rank}；最大距離偏差 {max_dev:.3g}；容差 {NN_TOLERANCE:g}")
            if max_dev > NN_ATTENTION:
                LOG.note(f"V5 最大距離偏差 {max_dev:.3g} 超過 {NN_ATTENTION:g}：須回報使用者，不得自行放寬容差（D-12）")
        guarded("V5", "最近鄰排序", v5)

        # 變更版資料（V8、V9、V10 共用）
        drop_pids = [p["parent_id"] for p in P[-3:]]
        kept_c = [c for c in Crows if c["parent_id"] not in drop_pids]
        mod_c = dict(kept_c[0])
        mod_c["section"] = mod_c["section"] + " (v)"
        emb = list(mod_c["embedding"])
        emb[0] = emb[0] + 1e-3
        mod_c["embedding"] = emb
        mod_p = dict(P[0])
        mod_p["title"] = mod_p["title"] + " (v)"
        new_pid = f"{version}:test:test:test:p99"
        new_p = {**P[1], "parent_id": new_pid}
        src_c = next(c for c in Crows if c["parent_id"] == P[1]["parent_id"])
        new_c = {**src_c, "chunk_id": new_pid + ":c01", "parent_id": new_pid}
        P2 = [mod_p if p["parent_id"] == mod_p["parent_id"] else p for p in P if p["parent_id"] not in drop_pids] + [new_p]
        C2 = [mod_c if c["chunk_id"] == mod_c["chunk_id"] else c for c in kept_c] + [new_c]
        dropped_children = len(Crows) - len(kept_c)

        recorded: list[list[str]] = []

        def v9() -> None:
            clean_state = rebuild_base()
            tap = SqlTap(conn)
            counts = ic.write_update(tap, version, P2, C2)
            recorded.append(tap.sql)
            exp_p = (1, 1, len(P) - 3 - 1, 3)     # 新增、更新、未變、刪除
            exp_c = (1, 1, len(Crows) - dropped_children - 1, dropped_children)
            got_p = (counts.parents.inserted, counts.parents.updated, counts.parents.unchanged, counts.parents.deleted)
            got_c = (counts.children.inserted, counts.children.updated, counts.children.unchanged, counts.children.deleted)
            fp_ok = db_fp(conn, version) == art_fp(P2, C2)
            LOG.add("V9", "update 新增／更新／未變／刪除筆數與資料庫實際結果一致", got_p == exp_p and got_c == exp_c and fp_ok,
                    f"parents 實際 {got_p} 預期 {exp_p}；children 實際 {got_c} 預期 {exp_c}；指紋相符={fp_ok}")
            return clean_state
        guarded("V9", "update 新增／更新／刪除", v9)

        def v10() -> None:
            before = db_fp(conn, version)
            c1 = ic.write_update(conn, version, P2, C2)
            c2 = ic.write_update(conn, version, P2, C2)
            after = db_fp(conn, version)
            zero = all(x == 0 for c in (c1, c2) for t in (c.parents, c.children) for x in (t.inserted, t.updated, t.deleted))
            LOG.add("V10", "冪等：連跑兩次 update，指紋相同且新增／更新／刪除皆 0", zero and before == after == art_fp(P2, C2),
                    f"指紋相同={before == after}、變動為 0={zero}")
        guarded("V10", "冪等", v10)

        def v8() -> None:
            all_ok = True
            details = []
            for mode, writer, data in (("update", ic.write_update, (P2, C2)), ("rebuild", ic.write_rebuild, (P2, C2))):
                rebuild_base()
                before = db_fp(conn, version)
                probe = SqlTap(conn)
                writer(probe, version, *data)
                total = probe.n
                rebuild_base()
                for n in sorted({1, max(1, total // 2), total}):
                    try:
                        writer(SqlTap(conn, fail_at=n), version, *data)
                        ok = False
                    except RuntimeError:
                        ok = db_fp(conn, version) == before
                    all_ok &= ok
                    details.append(f"{mode}@{n}/{total}={'ok' if ok else 'FAIL'}")
            # 輸入混入 1023 維向量
            rebuild_base()
            before = db_fp(conn, version)
            bad_rows = [dict(r) for r in Crows]
            bad_rows[5]["embedding"] = list(bad_rows[5]["embedding"])[:1023]
            for mode, writer in (("update", ic.write_update), ("rebuild", ic.write_rebuild)):
                try:
                    writer(conn, version, P, bad_rows)
                    ok = False
                except Exception:   # noqa: BLE001
                    ok = db_fp(conn, version) == before
                all_ok &= ok
                details.append(f"1023維-{mode}={'ok' if ok else 'FAIL'}")
            LOG.add("V8", "交易回滾：注入例外與 1023 維向量後，資料與寫入前相同（兩種模式）", all_ok, "、".join(details))
        guarded("V8", "交易回滾", v8)

        def v11() -> None:
            rebuild_base()
            before = db_fp(conn, version)
            bad = [{**c, "model_revision": OTHER_REVISION} for c in Crows]
            try:
                ic.write_update(conn, version, P, bad)
                raised, msg = False, ""
            except Exception as exc:   # noqa: BLE001
                raised, msg = True, str(exc)
            LOG.add("V11", "update 防呆：model 組不同即中止並提示 rebuild，資料不變", raised and "rebuild" in msg and db_fp(conn, version) == before,
                    first_line(mask(msg)))
        guarded("V11", "update 防呆", v11)

        def v12() -> None:
            rebuild_base()
            with conn.cursor() as cur:
                cur.execute("SELECT confdeltype, confupdtype FROM pg_constraint WHERE conrelid = 'rag.children'::regclass AND contype = 'f'")
                fks = cur.fetchall()
            LOG.add("V12", "外鍵存在且為 NO ACTION（非 CASCADE）", len(fks) == 1 and fks[0] == ("a", "a"), f"外鍵 {fks}")
            orphan = {**Crows[0], "chunk_id": version + ":orphan:c01", "parent_id": version + ":orphan:p99"}
            cols = CHILD_NAMES
            sql = f"INSERT INTO rag.children ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
            try:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(sql, [Vector(f32(orphan[c])) if c == "embedding" else orphan[c] for c in cols])
                orphan_blocked = False
            except psycopg.errors.ForeignKeyViolation:
                orphan_blocked = True
            try:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM rag.parents WHERE parent_id = %s AND version = %s", (P[0]["parent_id"], version))
                parent_blocked = False
            except psycopg.errors.ForeignKeyViolation:
                parent_blocked = True
            LOG.add("V12", "資料庫強制外鍵：孤兒 child 無法寫入、仍有 child 的 parent 無法刪除", orphan_blocked and parent_blocked,
                    f"孤兒被擋={orphan_blocked}、刪 parent 被擋={parent_blocked}")
            # 寫入與刪除順序（由 SQL 紀錄判定）
            def first(stmts: list[str], prefix: str) -> int:
                for i, s in enumerate(stmts):
                    if s.strip().lower().startswith(prefix):
                        return i
                return -1
            clean()
            tap_r = SqlTap(conn)
            ic.write_rebuild(tap_r, version, P, Crows)
            r = [first(tap_r.sql, x) for x in ("delete from rag.children", "delete from rag.parents",
                                               "insert into rag.parents", "insert into rag.children")]
            u = [first(recorded[0], x) for x in ("insert into rag.parents", "insert into rag.children",
                                                 "delete from rag.children", "delete from rag.parents")] if recorded else [-1]
            LOG.add("V12", "SQL 順序：rebuild 先刪 children 再刪 parents、先寫 parents 再寫 children；update 先 upsert parents 再 children、先刪 children 再刪 parents",
                    all(x >= 0 for x in r + u) and r == sorted(r) and u == sorted(u), f"rebuild {r}、update {u}")
            recorded.append(tap_r.sql)
        guarded("V12", "外鍵與刪除順序", v12)

        def v17_dynamic() -> None:
            stmts = [s for group in recorded for s in group]
            bad = [s[:60] for s in stmts if FORBIDDEN_SQL.search(s)]
            unscoped = [s[:60] for s in stmts if s.strip().lower().startswith("delete") and "version = %s" not in s]
            LOG.add("V17", "執行時送出的 SQL 不含 DROP／TRUNCATE／ALTER／CASCADE，DELETE 皆含 version = %s",
                    bool(stmts) and not bad and not unscoped, f"檢查 {len(stmts)} 個陳述式；違規 {bad + unscoped}")
        guarded("V17", "動態 SQL 檢查", v17_dynamic)

        def v20() -> None:
            rebuild_base()
            def rename(s: str) -> str:
                return s.replace(version, VERSION_B, 1)
            PB = [{**p, "parent_id": rename(p["parent_id"]), "version": VERSION_B} for p in P]
            CB = [{**c, "chunk_id": rename(c["chunk_id"]), "parent_id": rename(c["parent_id"]), "version": VERSION_B} for c in Crows]
            ic.write_rebuild(conn, VERSION_B, PB, CB)
            fp_b = db_fp(conn, VERSION_B)
            ic.write_rebuild(conn, version, P, Crows)
            ic.write_update(conn, version, P2, C2)
            scoped = db_fp(conn, VERSION_B) == fp_b == art_fp(PB, CB)
            LOG.add("V20", "DELETE 範圍限於 version：對 A 做 rebuild／update 後，B 的指紋不變", scoped, "")
            ic.write_rebuild(conn, version, P, Crows)
            before_a, before_b = db_fp(conn, version), db_fp(conn, VERSION_B)
            other_model = [{**c, "model_revision": OTHER_REVISION} for c in Crows]
            try:
                ic.write_rebuild(conn, version, P, other_model)
                raised = False
            except Exception:   # noqa: BLE001
                raised = True
            LOG.add("V20", "rebuild 檢查其他 version 的 model 組：不一致即中止，兩個 version 資料皆不變（Q2）",
                    raised and db_fp(conn, version) == before_a and db_fp(conn, VERSION_B) == before_b, "")
        guarded("V20", "version 範圍", v20)

        def v21() -> None:
            # 擴充版本（函式層級注入）
            for found, should_pass in (("0.8.1", False), ("0.8.2", True), ("0.10.0", True), (None, False), ("garbage", False)):
                try:
                    ic.evaluate_extension_version(found)
                    passed = True
                except Exception:   # noqa: BLE001
                    passed = False
                LOG.add("V21", f"擴充版本注入 {found!r}", passed == should_pass, f"通過={passed}、預期={should_pass}")
            # schema 不符：TEMP 表交給檢查函式（不修改 rag.*）
            text_cols = ["text", "title", "source_url", "version", "mod", "chapter", "page", "section"]
            spec_parent = {"columns": [("parent_id", "text", True)] + [(c, "text", True) for c in text_cols] + [("token_count", "integer", True)],
                           "pk": ["parent_id"], "fk": None, "checks": ["parents_nonempty_chk"], "index": None}
            spec_child = {"columns": [("chunk_id", "text", True), ("parent_id", "text", True)] + [(c, "text", True) for c in text_cols]
                          + [("token_count", "integer", True), ("embedding", "vector(1024)", True), ("model_name", "text", True),
                             ("model_revision", "text", True)],
                          "pk": ["chunk_id"], "fk": {"column": "parent_id", "target": "pg_temp.t_parents", "target_column": "parent_id"},
                          "checks": ["children_nonempty_chk"], "index": ("t_idx", "parent_id")}
            with conn.cursor() as cur:
                cur.execute("CREATE TEMP TABLE t_parents (parent_id text NOT NULL PRIMARY KEY, text text NOT NULL, title text NOT NULL, "
                            "source_url text NOT NULL, version text NOT NULL, mod text NOT NULL, chapter text NOT NULL, page text NOT NULL, "
                            "section text NOT NULL, token_count integer NOT NULL, CONSTRAINT parents_nonempty_chk CHECK (text <> ''))")
            base_cols = ("chunk_id text NOT NULL PRIMARY KEY, parent_id text NOT NULL{fk}, text text NOT NULL, title text NOT NULL, "
                         "source_url text NOT NULL, version text NOT NULL, mod text NOT NULL, chapter text NOT NULL, page text NOT NULL, "
                         "section text NOT NULL, token_count integer NOT NULL, embedding public.vector({dim}) {nn}, "
                         "model_name text NOT NULL, model_revision text NOT NULL{extra}, CONSTRAINT children_nonempty_chk CHECK (text <> '')")
            fk_ok = " REFERENCES t_parents (parent_id)"
            variants = [
                ("t_good", dict(fk=fk_ok, dim=1024, nn="NOT NULL", extra=""), True, True, ""),
                ("t_dim", dict(fk=fk_ok, dim=1023, nn="NOT NULL", extra=""), True, False, "vector(1023)"),
                ("t_nofk", dict(fk="", dim=1024, nn="NOT NULL", extra=""), True, False, "缺少外鍵"),
                ("t_cascade", dict(fk=fk_ok + " ON DELETE CASCADE", dim=1024, nn="NOT NULL", extra=""), True, False, "ON DELETE"),
                ("t_extra", dict(fk=fk_ok, dim=1024, nn="NOT NULL", extra=", unexpected_col text"), True, False, "多出未預期"),
                ("t_nullable", dict(fk=fk_ok, dim=1024, nn="", extra=""), True, False, "NOT NULL"),
                ("t_noindex", dict(fk=fk_ok, dim=1024, nn="NOT NULL", extra=""), False, False, "缺少索引"),
            ]
            for name, kw, with_index, should_pass, keyword in variants:
                with conn.cursor() as cur:
                    cur.execute(f"CREATE TEMP TABLE {name} (" + base_cols.format(**kw) + ")")
                    if with_index:
                        cur.execute(f"CREATE INDEX {name}_idx ON {name} (parent_id)")
                spec = {**spec_child, "index": (f"{name}_idx", "parent_id")}
                problems = ic.check_table_schema(conn, f"pg_temp.{name}", spec)
                ok = (not problems) if should_pass else any(keyword in p for p in problems)
                LOG.add("V21", f"schema 檢查函式：TEMP 表變體 {name}", ok, f"回報 {len(problems)} 項：{'；'.join(problems)[:160]}")
            # 缺欄位與缺 CHECK
            with conn.cursor() as cur:
                cur.execute("CREATE TEMP TABLE t_missing (chunk_id text NOT NULL PRIMARY KEY)")
            problems = ic.check_table_schema(conn, "pg_temp.t_missing", spec_child)
            LOG.add("V21", "schema 檢查函式：缺欄位與缺 CHECK 約束", any("缺少欄位" in p for p in problems) and any("CHECK" in p for p in problems),
                    f"回報 {len(problems)} 項")
            parent_problems = ic.check_table_schema(conn, "pg_temp.t_parents", spec_parent)
            LOG.add("V21", "schema 檢查函式：正確的 TEMP parents 無不符項（對照組）", not parent_problems, "；".join(parent_problems)[:160])
            LOG.add("V21", "rag.* 的結構以函式檢查通過（不修改任何 rag 表）",
                    not ic.check_table_schema(conn, "rag.parents", ic.PARENTS_SPEC) and not ic.check_table_schema(conn, "rag.children", ic.CHILDREN_SPEC), "")
        guarded("V21", "schema 與擴充版本", v21)

        # V13b、V14、V16：會連線的 CLI 案例（只對測試庫）
        def v13b() -> None:
            version_, P_, C_, E_ = version, P, C, E
            rebuild_base()
            before = db_fp(conn, version)
            root = TempRoot(version)
            try:
                root.set_artifacts(P_, C_, E_)
                dummy = urlunsplit(urlsplit(url_test)._replace(path="/other_db_name"))
                proc = root.run(["--mode", "update"], {"DATABASE_URL": url_test, "DATABASE_URL_TEST": dummy})
                out = proc.stdout + proc.stderr
                ok = (proc.returncode == 1 and TEST_DB in out and root.spy_calls() >= 1 and db_fp(conn, version) == before
                      and not [s for s in SECRETS if s and s in out])
                LOG.add("V13b", "DATABASE_URL 指向測試庫：連線後 current_database() 斷言中止，資料不變（spy 有記錄，正向對照）", ok,
                        f"exit={proc.returncode}、spy={root.spy_calls()}、{first_line(mask(proc.stderr))}")
                check_report("V13b 庫名不符", root)
                # 錯誤密碼：連線失敗，輸出與報告不含密碼
                bad_pw = "WrongPw_for_test_only"
                SECRETS.append(bad_pw)
                sp = urlsplit(url_test)
                bad_url = urlunsplit(sp._replace(netloc=f"{sp.username}:{bad_pw}@{sp.hostname}:{sp.port}"))
                dummy_bad = urlunsplit(urlsplit(bad_url)._replace(path="/other_db_name"))
                proc = root.run(["--mode", "update"], {"DATABASE_URL": bad_url, "DATABASE_URL_TEST": dummy_bad})
                out = proc.stdout + proc.stderr
                LOG.add("V14", "錯誤密碼連線：結束碼 1，輸出不含密碼", proc.returncode == 1 and bad_pw not in out
                        and not any(s and s in out for s in SECRETS), f"exit={proc.returncode}、{first_line(mask(proc.stderr))}")
                check_report("V13b 錯誤密碼", root)
            finally:
                root.cleanup()
        guarded("V13b", "會連線的 CLI 案例", v13b)

        # 離線項目（同一次跑完）
        run_offline()
        ok = bool(REPORT_CHECKS) and all(o for _, o, _ in REPORT_CHECKS)
        LOG.add("V16", "CLI 報告欄位齊全且不含密碼或 URL（含連線案例）", ok, f"{len(REPORT_CHECKS)} 份")
        leaked = [s for s in SECRETS if s and any(s in out for out in CAPTURED)]
        LOG.add("V14", "所有子行程輸出不含密碼（含連線案例與真實測試庫密碼）", not leaked, f"掃描 {len(CAPTURED)} 份輸出")
        # 清理：只動明列的兩表，先 children 後 parents（N14）
        clean()
        left = scalar_count(conn, "SELECT count(*) FROM rag.parents WHERE version = ANY(%s)", (versions,)) \
            + scalar_count(conn, "SELECT count(*) FROM rag.children WHERE version = ANY(%s)", (versions,))
        LOG.add("V1", "清理後測試庫中本腳本使用的 version 皆已清空（N14）", left == 0, f"殘留 {left} 列")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="[7] 入庫的獨立驗證（測試庫）")
    parser.add_argument("--offline", action="store_true",
                        help="只跑不讀 .env、不連線的項目：V13a、V15、V17、V18、V19（並附帶 V14、V16 的離線部分）")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")   # 主控台編碼（如 cp950）無法顯示的字元以 ? 取代，避免中斷
    intro: list[str] = []
    try:
        if args.offline:
            print("[verify_index] 離線模式（不讀 .env、不連線）")
            run_offline()
        else:
            print("[verify_index] 全部項目（連測試庫）")
            run_full(intro)
            write_text(REPORT_PATH, LOG.render("入庫驗證報告（verify_index.py，測試庫）",
                                               [f"模式：全部（V1～V23）", f"測試庫名：{TEST_DB}"] + intro
                                               + [f"容差：|d − d_min| ≤ {NN_TOLERANCE:g}"]))
            print(f"     報告：{REPORT_PATH.relative_to(PROJECT_ROOT)}")
    finally:
        for r in TEMP_ROOTS:
            shutil.rmtree(r, ignore_errors=True)
    failed = LOG.failed
    print(f"[verify_index] 共 {len(LOG.results)} 項，不通過 {len(failed)} 項")
    for r in failed:
        print(f"  不通過：{r.check_id} {r.title}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
