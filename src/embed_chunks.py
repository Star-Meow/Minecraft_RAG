"""[6] 向量化（Embedding）。

職責：讀 [5] 的 data/processed/chunks/<version>/children.jsonl，組出 embedding 輸入
f"{section}\\n\\n{text}"，以 BAAI/bge-m3（dense、1024 維、正規化、revision 鎖定）產生向量，輸出
data/processed/embeddings/<version>/children_embeddings.jsonl 並產生 reports/embedding_report.md
（docs/05_embed.md）。

- 輸出與輸入 child 逐筆對應（順序、ID、11 個原欄位不變），再加 embedding_input／embedding／
  model_name／model_revision。parent 不進 embedding。
- --dry-run：只組字串、做 tokenizer 斷言與對帳，不載入模型、不初始化 CUDA、不寫任何檔案。
- 模型一律離線載入（HF_HUB_OFFLINE=1）；不下載任何檔案。
設計原則（同 [3]～[5]）：模組化、型別標註、main() 只做編排。
"""

from __future__ import annotations

import os

# 離線：必須在匯入 transformers／sentence_transformers 之前設定
os.environ["HF_HUB_OFFLINE"] = "1"

import argparse
import json
import math
import shutil
import statistics
import sys
from pathlib import Path

from transformers import AutoTokenizer

# ---------------------------------------------------------------------------
# [6.0] 設定
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"
EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "processed" / "embeddings"
REPORTS_DIR = PROJECT_ROOT / "reports"
SOURCES_PATH = PROJECT_ROOT / "sources.json"
REPORT_PATH = REPORTS_DIR / "embedding_report.md"
OUTPUT_NAME = "children_embeddings.jsonl"

MODEL_NAME = "BAAI/bge-m3"
MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"   # 與 [5] chunk_pages.py 的 TOKENIZER_REVISION 相同
EMBEDDING_DIM = 1024
MAX_INPUT_TOKENS = 8192          # 含 special tokens
BATCH_SIZE = 16                  # 實作細節：child ≤ 256 tokens，16 對一般 GPU 都保守
DEVICE = "cuda"                  # 2026-11-05 人工裁定：非 dry-run 必須使用 CUDA，不退回 CPU
NORM_TOLERANCE = 1e-4

NEWLINE = "\n"
# [5] children.jsonl 的 11 個原欄位（docs/04_chunk.md §1），原樣帶入
CHILD_FIELDS = ["chunk_id", "parent_id", "text", "title", "source_url", "version",
                "mod", "chapter", "page", "section", "token_count"]
# provenance 欄位：缺少或為空 → 中止（AGENTS.md §3.1）
PROVENANCE_FIELDS = ["chunk_id", "source_url", "title", "version", "mod", "chapter", "page", "section"]


# ---------------------------------------------------------------------------
# [6.1] 輸入
# ---------------------------------------------------------------------------
def load_sources(path: Path) -> dict:
    """讀 sources.json；缺檔代表 [1] 未設定，直接報錯。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}：[1] sources.json 不存在")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def check_revision_consistency() -> None:
    """核對 [5] 使用的 tokenizer revision 與本模塊一致；不一致即中止。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import chunk_pages
    if chunk_pages.TOKENIZER_NAME != MODEL_NAME or chunk_pages.TOKENIZER_REVISION != MODEL_REVISION:
        raise RuntimeError(
            f"revision 不一致：[5]={chunk_pages.TOKENIZER_NAME}@{chunk_pages.TOKENIZER_REVISION}，"
            f"[6]={MODEL_NAME}@{MODEL_REVISION}")


def load_children(path: Path) -> list:
    """讀 children.jsonl，逐筆檢查欄位齊全、provenance 非空、chunk_id 唯一。"""
    if not path.is_file():
        raise FileNotFoundError(f"找不到 {path}：請先執行 [5] src/chunk_pages.py")
    children = []
    seen = set()
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                raise ValueError(f"{path.name}:{lineno} 為空行")
            record = json.loads(line)
            missing = [k for k in CHILD_FIELDS if k not in record]
            if missing:
                raise ValueError(f"{path.name}:{lineno} 缺欄位：{missing}")
            empty = [k for k in PROVENANCE_FIELDS if not record[k]]
            if empty:
                raise ValueError(f"{path.name}:{lineno} provenance 欄位為空：{empty}")
            if record["chunk_id"] in seen:
                raise ValueError(f"{path.name}:{lineno} chunk_id 重複：{record['chunk_id']}")
            seen.add(record["chunk_id"])
            children.append(record)
    if not children:
        raise ValueError(f"{path} 無任何 child")
    return children


# ---------------------------------------------------------------------------
# [6.2] embedding 輸入與 tokenizer 斷言
# ---------------------------------------------------------------------------
def build_embedding_input(child: dict) -> str:
    """embedding 輸入 = f"{section}\\n\\n{text}"（docs/05_embed.md §1；所有 child 同一規則）。"""
    return f"{child['section']}\n\n{child['text']}"


def count_input_tokens(tokenizer, inputs: list) -> list:
    """每筆含 special tokens 的 token 數。"""
    return [len(tokenizer.encode(s, add_special_tokens=True)) for s in inputs]


def find_over_limit(children: list, counts: list) -> list:
    """上限斷言：含 special tokens ≤ 8192。回傳違規清單。"""
    return [f"{c['chunk_id']}：{n} > {MAX_INPUT_TOKENS}"
            for c, n in zip(children, counts) if n > MAX_INPUT_TOKENS]


# ---------------------------------------------------------------------------
# [6.3] 向量計算（只在非 dry-run 時呼叫；此時才建立模型、載入權重）
# ---------------------------------------------------------------------------
def require_cuda() -> str:
    """確認 CUDA 可用並回傳裝置資訊字串；不可用即 RuntimeError（呼叫端須在載入模型、寫檔、刪檔之前呼叫）。"""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA 不可用：[6] 向量化必須使用 NVIDIA GPU（CUDA），不退回 CPU。"
            f"請確認有 NVIDIA GPU 與驅動，且 torch 為 cu130 build（目前 torch {torch.__version__}）")
    return f"{torch.cuda.get_device_name(0)}（torch {torch.__version__}）"


def encode_inputs(inputs: list) -> list:
    """以 sentence-transformers 在 CUDA 上計算 dense 向量（normalize_embeddings=True）。"""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, device=DEVICE)
    vectors = model.encode(inputs, batch_size=BATCH_SIZE, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=False)
    return [[float(x) for x in row] for row in vectors]


def check_vectors(vectors: list, n_expected: int) -> None:
    """向量檢查：筆數、1024 維、norm = 1。失敗即中止。"""
    if len(vectors) != n_expected:
        raise ValueError(f"向量筆數 {len(vectors)} ≠ 輸入筆數 {n_expected}")
    for i, vec in enumerate(vectors):
        if len(vec) != EMBEDDING_DIM:
            raise ValueError(f"第 {i + 1} 筆維度 {len(vec)} ≠ {EMBEDDING_DIM}")
        norm = math.sqrt(sum(x * x for x in vec))
        if abs(norm - 1.0) > NORM_TOLERANCE:
            raise ValueError(f"第 {i + 1} 筆 norm = {norm} ≠ 1")


def build_records(children: list, inputs: list, vectors: list) -> list:
    """原欄位原樣帶入（順序同 children.jsonl）+ embedding_input／embedding／model_name／model_revision。"""
    records = []
    for child, text_in, vec in zip(children, inputs, vectors):
        record = dict(child)
        record["embedding_input"] = text_in
        record["embedding"] = vec
        record["model_name"] = MODEL_NAME
        record["model_revision"] = MODEL_REVISION
        records.append(record)
    return records


# ---------------------------------------------------------------------------
# [6.4] 輸出（embeddings/<version>/ 重建：人工已授權的敏感操作，2026-11-05）
# ---------------------------------------------------------------------------
def assert_rebuild_target(version: str) -> Path:
    """斷言重建目標合法：必須是 EMBEDDINGS_DIR 的直接版本子目錄，且 EMBEDDINGS_DIR 位置正確。"""
    if EMBEDDINGS_DIR != PROJECT_ROOT / "data" / "processed" / "embeddings":
        raise RuntimeError(f"EMBEDDINGS_DIR 位置異常：{EMBEDDINGS_DIR}")
    if not version or not version.isascii() or "/" in version or "\\" in version or version in (".", ".."):
        raise ValueError(f"version 不合法：{version!r}")
    target = EMBEDDINGS_DIR / version
    if target.parent != EMBEDDINGS_DIR:
        raise RuntimeError(f"重建目標不在 EMBEDDINGS_DIR 之下：{target}")
    return target


def rebuild_dir(version_dir: Path) -> None:
    """清空 embeddings/<version>/ 並重建。呼叫前須先通過 assert_rebuild_target。"""
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Path, records: list) -> None:
    """一行一筆 JSON（UTF-8、不跳脫非 ASCII、強制 LF）。"""
    with path.open("w", encoding="utf-8", newline=NEWLINE) as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + NEWLINE)


# ---------------------------------------------------------------------------
# [6.5] 報告
# ---------------------------------------------------------------------------
def token_summary(counts: list) -> dict:
    """輸入 token 數分布。"""
    return {"count": len(counts), "max": max(counts), "mean": round(statistics.mean(counts), 2),
            "median": statistics.median(counts)}


def write_embedding_report(path: Path, version: str, n_input: int, summary: dict, device_info: str) -> None:
    """寫 reports/embedding_report.md（單次報告，整份覆寫）。"""
    lines = [
        "# 向量化報告（[6] embed_chunks.py）",
        "",
        "## 1. 設定",
        "",
        f"- version：`{version}`",
        f"- 模型：`{MODEL_NAME}` @ `{MODEL_REVISION}`（dense、{EMBEDDING_DIM} 維、normalize_embeddings=True）",
        '- embedding 輸入：`f"{section}\\n\\n{text}"`',
        f"- 裝置：`{DEVICE}`，{device_info}",
        f"- 批次大小：{BATCH_SIZE}",
        "",
        "## 2. 對帳",
        "",
        f"- 輸入 child：{n_input}",
        f"- 輸出向量：{n_input}",
        "",
        f"## 3. embedding 輸入 token 分布（含 special tokens，上限 {MAX_INPUT_TOKENS}）",
        "",
        "| 數量 | 平均 | 中位數 | 最大 |",
        "| --- | --- | --- | --- |",
        f"| {summary['count']} | {summary['mean']} | {summary['median']} | {summary['max']} |",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline=NEWLINE) as f:
        f.write(NEWLINE.join(lines))


# ---------------------------------------------------------------------------
# [6.6] 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    """[6] 主流程。回傳 exit code：0 成功；1 表輸入錯誤、超過上限或向量檢查失敗。"""
    parser = argparse.ArgumentParser(description="[6] 向量化")
    parser.add_argument("--dry-run", action="store_true",
                        help="只組輸入字串、做 tokenizer 斷言與對帳；不載入模型、不寫檔")
    args = parser.parse_args()

    device_info = ""
    if not args.dry_run:
        try:
            device_info = require_cuda()
        except RuntimeError as exc:
            print(f"[6] 中止：{exc}", file=sys.stderr)
            return 1
        print(f"[6] 裝置：{DEVICE}，{device_info}")

    sources = load_sources(SOURCES_PATH)
    version = sources["version"]
    print(f"[1] sources.json：version={version} mod={sources['mod']}")

    try:
        check_revision_consistency()
        children = load_children(CHUNKS_DIR / version / "children.jsonl")
        assert_rebuild_target(version)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"[6] 中止：{exc}", file=sys.stderr)
        return 1
    print(f"[5] children：{len(children)} 筆；chunk_id 唯一、provenance 齊全")

    inputs = [build_embedding_input(c) for c in children]
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, revision=MODEL_REVISION)
    counts = count_input_tokens(tokenizer, inputs)
    over = find_over_limit(children, counts)
    if over:
        for item in over:
            print(f"  OVER {item}", file=sys.stderr)
        print("[6] 中止：embedding 輸入超過 token 上限", file=sys.stderr)
        return 1
    summary = token_summary(counts)
    print(f"[6] embedding 輸入 token（含 special）：最大 {summary['max']}、平均 {summary['mean']}、"
          f"中位數 {summary['median']}（上限 {MAX_INPUT_TOKENS}）")

    if args.dry_run:
        print(f"[6] dry-run 完成：{len(inputs)} 筆輸入；未載入模型、未寫任何檔案")
        return 0

    vectors = encode_inputs(inputs)
    try:
        check_vectors(vectors, len(children))
    except ValueError as exc:
        print(f"[6] 中止：{exc}，不寫任何產出", file=sys.stderr)
        return 1
    records = build_records(children, inputs, vectors)

    version_dir = assert_rebuild_target(version)
    rebuild_dir(version_dir)
    write_jsonl(version_dir / OUTPUT_NAME, records)
    write_embedding_report(REPORT_PATH, version, len(children), summary, device_info)
    print(f"[6] 已寫入 {(version_dir / OUTPUT_NAME).relative_to(PROJECT_ROOT)}（{len(records)} 筆）")
    print(f"     報告：{REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
