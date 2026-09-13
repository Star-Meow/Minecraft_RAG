"""將 data/chunks.jsonl 的 chunks 轉為 embedding 向量（已準備完成、尚未執行）。

Pipeline 位置：chunks.jsonl → Embedding Model → Embedding Vectors（→ 之後才是 Vector Index）。

指定模型：sentence-transformers/all-MiniLM-L6-v2（Hugging Face）。
重要狀態：本程式為「準備完成、未執行」——模型下載/載入/encode 皆尚未發生。
首次執行前須先安裝依賴：pip install -r requirements.txt（含 sentence-transformers）。

未來執行方式：
    python embed_chunks.py                    # 使用預設路徑、模型與裝置
    python embed_chunks.py --device cpu       # 指定裝置
    python embed_chunks.py --batch-size 16    # 指定批次大小

設計說明：
    - Embedding 輸入契約（Option B）：page_title + section_title + content，
      以換行串接。依據 onetime-report.md 檢索評審模擬，標題併入對歧義查詢
      （基本系統 vs 自動合成、storage 同形異義）有正向助力（Inferred）。
    - all-MiniLM-L6-v2 的 max_seq_length 為 256 wordpieces；超長 content 會被
      截斷。截斷的實際影響 UNKNOWN — REQUIRES RUNTIME VERIFICATION。
    - 輸出為整份覆寫（冪等）：每行 = 原 chunk 完整 metadata + embedding 向量
      + embedding_model + embedded_at。metadata 不被破壞，未來 retrieval 可
      以 source_url + chunk_id（複合鍵；chunk_id 為頁內編號，非全域唯一）
      找回原始 chunk。
    - chunk_id 不具全域唯一性。若 index 階段需要單一穩定 ID，建議方案為
      sha1(f"{source_url}#{chunk_id}")——屬 index 階段決策，本程式不擅自變更
      chunk schema。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -------------------------------------------------------------------- 路徑設定
PROJECT_ROOT = Path(__file__).resolve().parent
INPUT_PATH = PROJECT_ROOT / "data" / "chunks.jsonl"
OUTPUT_PATH = PROJECT_ROOT / "data" / "embeddings.jsonl"

# -------------------------------------------------------------------- 模型設定
# 任務指派的模型（非選型結果），來源：
# https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# 留空 = 使用模型庫最新版本；建議正式化時鎖定特定 revision（commit hash）
MODEL_REVISION = ""

BATCH_SIZE = 32
NORMALIZE_EMBEDDINGS = True  # all-MiniLM-L6-v2 為 cosine 相似度模型，慣例為正規化
DEVICE = None  # None = 交由 sentence-transformers 自動選擇（有 CUDA 用 GPU，否則 CPU）

# Embedding 輸入契約（Option B）：哪些 chunk 欄位會進入 embedding 文字
EMBEDDING_TEXT_FIELDS = ("page_title", "section_title", "content")

# 產生 embedding 向量時必須存在的 chunk 欄位（provenance 最低需求）
REQUIRED_FIELDS = ("source_url", "chunk_id", "page_title", "section_title", "content")


# -------------------------------------------------------------------- 資料載入
def load_chunks(path: Path) -> list[dict[str, Any]]:
    """讀取 chunks.jsonl，驗證非空且每行含必要欄位；不符時中止（exit 1）。"""
    if not path.is_file():
        raise FileNotFoundError(f"找不到輸入檔：{path}")
    chunks: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} 第 {line_number} 行不是合法 JSON：{exc}") from exc
            missing = [f for f in REQUIRED_FIELDS if not record.get(f)]
            if missing:
                raise ValueError(
                    f"{path} 第 {line_number} 行缺少 embedding 必要欄位：{', '.join(missing)}"
                )
            chunks.append(record)
    if not chunks:
        raise ValueError(f"{path} 沒有任何 chunk 記錄")
    return chunks


def build_embedding_text(chunk: dict[str, Any]) -> str:
    """依 EMBEDDING_TEXT_FIELDS 契約組出送入模型的文字。"""
    return "\n".join(str(chunk[field]) for field in EMBEDDING_TEXT_FIELDS)


# -------------------------------------------------------------------- 主流程
def run_embedding(
    input_path: Path,
    output_path: Path,
    model_name: str,
    revision: str,
    batch_size: int,
    device: str | None,
) -> int:
    """載入 chunks → 載入模型 → encode → 覆寫輸出 embeddings.jsonl。"""
    chunks = load_chunks(input_path)
    texts = [build_embedding_text(chunk) for chunk in chunks]
    print(f"loaded {len(chunks)} chunks from {input_path}")

    # 延遲載入：安裝 sentence-transformers 前本模組仍可被靜態檢查
    from sentence_transformers import SentenceTransformer

    print(f"loading model {model_name} (revision={revision or 'latest'}, device={device or 'auto'})...")
    model = SentenceTransformer(model_name, revision=revision or None, device=device)
    print(f"encoding {len(texts)} texts (batch_size={batch_size}, normalize={NORMALIZE_EMBEDDINGS})...")
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=NORMALIZE_EMBEDDINGS,
        show_progress_bar=True,
    )

    embedded_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with output_path.open("w", encoding="utf-8") as out:
        for chunk, vector in zip(chunks, vectors):
            record = dict(chunk)
            record["embedding"] = [float(x) for x in vector]
            record["embedding_model"] = model_name
            record["embedded_at"] = embedded_at
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"wrote {len(chunks)} embeddings to {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_PATH, help="chunks.jsonl 路徑")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="輸出 embeddings.jsonl 路徑")
    parser.add_argument("--model", default=MODEL_NAME, help="embedding 模型名稱")
    parser.add_argument("--revision", default=MODEL_REVISION, help="模型 revision（留空 = latest）")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--device", default=DEVICE, help='"cuda" / "cpu"，預設自動選擇')
    args = parser.parse_args()

    try:
        return run_embedding(
            input_path=args.input,
            output_path=args.output,
            model_name=args.model,
            revision=args.revision,
            batch_size=args.batch_size,
            device=args.device,
        )
    except (FileNotFoundError, ValueError, ImportError) as exc:
        print(f"embedding failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
