"""[7] 檢查腳本共用的純工具（verify_index.py、audit_index.py）。

只放不含「通過與否」判斷的純函式：JSONL 讀取、指紋序列化、float32 位元組、暴力 cosine、結果收集與報告渲染。
不含 URL 解析與任何斷言（兩支腳本各自實作），也不 import index_chunks.py（獨立性，計畫 N2）。
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NEWLINE = "\n"
D6_SENTENCE = "V5 只證明資料庫排序等於暴力計算，不證明檢索品質"
NN_TOLERANCE = 1e-6          # S5：最小距離並列組與逐名距離的容差
NN_ATTENTION = 5e-7          # 實測偏差超過此值須回報（不自行放寬）
NN_TOP_K = 5

# 內容指紋的欄位序列化順序（= docs/06_index.md §2.2 的 DDL 欄位順序）；kind：s 字串、i 整數、v 向量
PARENT_FP_COLUMNS = [("parent_id", "s"), ("text", "s"), ("title", "s"), ("source_url", "s"),
                     ("version", "s"), ("mod", "s"), ("chapter", "s"), ("page", "s"), ("section", "s"),
                     ("token_count", "i")]
CHILD_FP_COLUMNS = [("chunk_id", "s"), ("parent_id", "s"), ("text", "s"), ("title", "s"),
                    ("source_url", "s"), ("version", "s"), ("mod", "s"), ("chapter", "s"), ("page", "s"),
                    ("section", "s"), ("token_count", "i"), ("embedding", "v"), ("model_name", "s"),
                    ("model_revision", "s")]


def read_jsonl(path: Path) -> list[dict]:
    """讀 JSONL（一行一筆 JSON 物件）。"""
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def artifact_paths(version: str, root: Path = PROJECT_ROOT) -> tuple[Path, Path, Path]:
    """三份輸入的路徑：parents、children、向量檔。"""
    return (root / "data" / "processed" / "chunks" / version / "parents.jsonl",
            root / "data" / "processed" / "chunks" / version / "children.jsonl",
            root / "data" / "processed" / "embeddings" / version / "children_embeddings.jsonl")


def f32(vec: Any) -> np.ndarray:
    """轉成 float32 一維陣列（資料庫的 vector 以 float32 儲存）。"""
    return np.asarray(vec, dtype=np.float32)


def f32_bytes(vec: Any) -> bytes:
    """float32 小端位元組。"""
    return np.asarray(vec, dtype="<f4").tobytes()


def serialize_value(value: Any, kind: str) -> bytes:
    """單一欄位序列化：字串＝8 位元組小端長度＋UTF-8；整數＝'I'＋8 位元組小端；向量＝'V'＋4 位元組小端維度＋float32。"""
    if kind == "s":
        raw = str(value).encode("utf-8")
        return struct.pack("<Q", len(raw)) + raw
    if kind == "i":
        return b"I" + struct.pack("<q", int(value))
    if kind == "v":
        raw = f32_bytes(value)
        return b"V" + struct.pack("<I", len(raw) // 4) + raw
    raise ValueError(f"未知的欄位種類 {kind!r}")


def fingerprint(rows: Iterable[dict], columns: list[tuple[str, str]], key: str, already_sorted: bool = False) -> str:
    """表的內容指紋：按主鍵（UTF-8 位元組序）排序，依 columns 序列化，SHA-256 串流累加。"""
    h = hashlib.sha256()
    ordered = rows if already_sorted else sorted(rows, key=lambda r: str(r[key]).encode("utf-8"))
    for row in ordered:
        for name, kind in columns:
            h.update(serialize_value(row[name], kind))
    return h.hexdigest()


def cosine_distance_matrix(queries: np.ndarray, corpus: np.ndarray) -> np.ndarray:
    """真正的 cosine 距離（float64；先各自除以 L2 norm，再 1 − 點積）。回傳 [n_queries, n_corpus]。"""
    q = np.asarray(queries, dtype=np.float64)
    c = np.asarray(corpus, dtype=np.float64)
    q = q / np.linalg.norm(q, axis=1, keepdims=True)
    c = c / np.linalg.norm(c, axis=1, keepdims=True)
    return 1.0 - q @ c.T


def tie_set(distances: np.ndarray, tolerance: float = NN_TOLERANCE) -> set[int]:
    """與最小距離相差不超過 tolerance 的索引集合（最小距離並列組）。"""
    d_min = float(distances.min())
    return {int(i) for i in np.nonzero(distances - d_min <= tolerance)[0]}


@dataclass
class Result:
    """單一驗證項目的結果。"""
    check_id: str
    title: str
    ok: bool
    detail: str = ""


@dataclass
class ResultLog:
    """收集結果並渲染成報告；不做判斷，只記錄呼叫端給的結果。"""
    results: list[Result] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, check_id: str, title: str, ok: bool, detail: str = "") -> bool:
        self.results.append(Result(check_id, title, bool(ok), detail))
        print(f"  [{'通過' if ok else '不通過'}] {check_id} {title}" + (f"：{detail}" if detail else ""))
        return bool(ok)

    def note(self, text: str) -> None:
        self.notes.append(text)
        print(f"  [註] {text}")

    @property
    def failed(self) -> list[Result]:
        return [r for r in self.results if not r.ok]

    def render(self, heading: str, intro: list[str]) -> str:
        lines = [f"# {heading}", "", f"- 時間：{datetime.now().isoformat(timespec='seconds')}"]
        lines += [f"- {s}" for s in intro]
        lines += ["", f"- 總計：{len(self.results)} 項，不通過 {len(self.failed)} 項", "",
                  "| 編號 | 項目 | 結果 | 說明 |", "| --- | --- | --- | --- |"]
        for r in self.results:
            detail = r.detail.replace("|", "／").replace(NEWLINE, " ")
            lines.append(f"| {r.check_id} | {r.title} | {'通過' if r.ok else '**不通過**'} | {detail} |")
        if self.notes:
            lines += ["", "## 註記", ""] + [f"- {n}" for n in self.notes]
        lines += ["", f"> {D6_SENTENCE}。", ""]
        return NEWLINE.join(lines)


def write_text(path: Path, text: str) -> None:
    """寫檔（UTF-8、LF、整份覆寫）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline=NEWLINE) as f:
        f.write(text)


def mask_secrets(text: str, secrets: list[str]) -> str:
    """把指定密碼字串與 URL 內嵌的帳密樣式取代為 ***（純字串處理）。"""
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return re.sub(r"://[^/\s:@]+:[^@\s]+@", "://***:***@", text)


def first_line(text: Optional[str], limit: int = 300) -> str:
    """取第一行並截短（例外訊息用）。"""
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line[:limit]
