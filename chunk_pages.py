"""將 processed Markdown 切成可建立向量索引的 chunks。

輸入來源限定 data/processed/ 下由 fetch_pages.py 產生的檔案。每個輸入
必須有 YAML metadata 與 source_url；缺少來源網址的內容不會納入知識庫。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_PATH = PROJECT_ROOT / "data" / "chunks.jsonl"

TARGET_TOKENS = 600
OVERLAP_TOKENS = 100
MIN_CHUNK_TOKENS = 40
CHARS_PER_TOKEN = 4

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_YAML_LINE_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_-]*):\s*"?(.*?)"?$')


def parse_frontmatter(document: str) -> tuple[dict[str, str], str]:
    """解析檔首簡易雙引號 YAML；不符合規範時拋出 ValueError。"""
    match = _FRONTMATTER_RE.match(document)
    if not match:
        raise ValueError("找不到合法的 YAML frontmatter")

    metadata: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = _YAML_LINE_RE.match(line)
        if not parsed:
            raise ValueError(f"無法解析 frontmatter 欄位：{line}")
        key, value = parsed.groups()
        metadata[key] = value.strip()

    required_keys = {
        "title",
        "source_url",
        "minecraft_version",
        "mod",
        "source_type",
        "fetched_at",
    }
    missing = sorted(required_keys - metadata.keys())
    if missing:
        raise ValueError(f"frontmatter 缺少欄位：{', '.join(missing)}")
    return metadata, document[match.end() :]


def normalize_content(content: str) -> list[str]:
    """移除圖片語法與空行雜訊，保留可檢索文字與基本段落。"""
    without_images = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", content)
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", without_images):
        text = " ".join(block.split())
        if text:
            paragraphs.append(text)
    return paragraphs


def split_sections(content: str) -> list[dict[str, str]]:
    """以 Markdown heading 分節；標題前的內容歸入 Introduction。"""
    sections: list[dict[str, str]] = []
    current_title = "Introduction"
    current_lines: list[str] = []

    for line in content.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append({"title": current_title, "content": body})
            current_title = heading.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    body = "\n".join(current_lines).strip()
    if body:
        sections.append({"title": current_title, "content": body})
    return sections


def estimate_tokens(text: str) -> int:
    """以字元數估算 tokens，作為不依賴外部 tokenizer 的 MVP 方法。"""
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def split_long_text(text: str) -> list[str]:
    """將文本裝箱成目標大小的 chunk，並讓相鄰 chunk 帶有限、對齊句界的重疊。

    裝箱單位為段落；超過目標長度的段落先以句界預切成不重疊片段
    （邊界對齊句子或詞，避免字中切斷）。相鄰 chunk 的重疊只回收上一個
    chunk 尾端、總長不超過 overlap_chars 的完整單位；單位過大或已覆蓋
    整個 chunk 時直接不帶重疊，避免子集包含與內容重複。
    """
    target_chars = TARGET_TOKENS * CHARS_PER_TOKEN
    overlap_chars = OVERLAP_TOKENS * CHARS_PER_TOKEN

    units: list[str] = []
    for source_paragraph in normalize_content(text):
        if len(source_paragraph) <= target_chars:
            units.append(source_paragraph)
            continue

        start = 0
        while start < len(source_paragraph):
            end = min(start + target_chars, len(source_paragraph))
            if end < len(source_paragraph):
                boundary = source_paragraph.rfind(". ", start, end)
                if boundary > start:
                    end = min(boundary + 2, len(source_paragraph))  # 含句點與其後空格
                else:
                    space = source_paragraph.rfind(" ", start, end)  # 無句界時對齊詞邊
                    if space > start:
                        end = space
            units.append(" ".join(source_paragraph[start:end].split()))
            start = end

    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for unit in units:
        if current_parts and current_length + len(unit) + 2 > target_chars:
            chunks.append("\n\n".join(current_parts))
            tail_parts: list[str] = []
            tail_length = 0
            for part in reversed(current_parts):
                if tail_length + len(part) + 2 > overlap_chars:
                    break
                tail_parts.insert(0, part)
                tail_length += len(part) + 2
            if not tail_parts or tail_length >= current_length:
                current_parts, current_length = [], 0
            else:
                current_parts, current_length = tail_parts, tail_length

        current_parts.append(unit)
        current_length += len(unit) + (2 if len(current_parts) > 1 else 0)

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return [chunk for chunk in chunks if estimate_tokens(chunk) >= MIN_CHUNK_TOKENS]


def make_chunks(metadata: dict[str, str], content: str) -> list[dict[str, Any]]:
    """產生符合專案 metadata 規範的 chunk records。"""
    fetched_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    records: list[dict[str, Any]] = []
    sequence = 0

    for section in split_sections(content):
        pieces = split_long_text(section["content"])
        for piece_index, piece in enumerate(pieces):
            section_title = section["title"]
            if len(pieces) > 1:
                section_title += f"（{piece_index + 1}/{len(pieces)}）"

            sequence += 1
            records.append(
                {
                    "chunk_id": f"{sequence:04d}",
                    "source_url": metadata["source_url"],
                    "page_title": metadata["title"],
                    "section_title": section_title,
                    "minecraft_version": metadata["minecraft_version"],
                    "mod": metadata["mod"],
                    "source_type": metadata["source_type"],
                    "fetched_at": fetched_at,
                    "estimated_tokens": estimate_tokens(piece),
                    "content": piece,
                }
            )
    return records


def load_processed_files() -> list[tuple[Path, dict[str, str], str]]:
    """讀取所有 processed Markdown，回傳路徑、metadata 與正文。"""
    paths = sorted(PROCESSED_DIR.rglob("*.md"))
    if not paths:
        raise FileNotFoundError(f"找不到 processed Markdown：{PROCESSED_DIR}")

    documents: list[tuple[Path, dict[str, str], str]] = []
    for path in paths:
        document = path.read_text(encoding="utf-8")
        metadata, content = parse_frontmatter(document)
        if not metadata.get("source_url"):
            raise ValueError(f"缺少 source_url：{path}")
        documents.append((path, metadata, content))
    return documents


def run_chunker() -> int:
    """處理所有文件、覆寫輸出 JSONL，並印出摘要。"""
    documents = load_processed_files()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    total_tokens = 0
    with OUTPUT_PATH.open("w", encoding="utf-8") as output:
        for path, metadata, content in documents:
            chunks = make_chunks(metadata, content)
            if not chunks:
                print(f"WARN    無有效內容 {path}", file=sys.stderr, flush=True)
                continue
            page_tokens = sum(int(item["estimated_tokens"]) for item in chunks)
            total_tokens += page_tokens
            for chunk in chunks:
                output.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            print(f"OK      {path.name}: {len(chunks)} chunks, {page_tokens} estimated tokens")

    with OUTPUT_PATH.open(encoding="utf-8") as output:
        chunk_count = sum(1 for _ in output)
    print("\n=== 完成 ===")
    print(f"共 {len(documents)} 頁、{chunk_count} chunks、{total_tokens} estimated tokens")
    print(f"output={OUTPUT_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        return run_chunker()
    except Exception as exc:  # noqa: BLE001 - CLI 需要顯示單一明確錯誤
        print(f"chunking failed: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
