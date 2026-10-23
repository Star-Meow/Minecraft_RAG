# 入庫

> 職責：把 child 向量與 parent 文件寫入 PostgreSQL + pgvector。
> 上一個階段：[向量化](05_embed.md)

程式：`src/index_chunks.py`（**擱置**；schema、入庫方式、索引類型待前面各階段跑通後，依實際資料定義，不預先虛構）

## 1. 輸入與輸出

- **輸入**：[向量化](05_embed.md) 的 child 向量，以及 [切分](04_chunk.md) 的 parent 文件。
- **輸出**：PostgreSQL + pgvector 中的資料。

## 2. 已定的內容

- **資料庫**：PostgreSQL + pgvector。
- **docstore 模式**：child 向量進向量庫；parent 文件能由 child 上的 parent 參照取回。本階段直接讀切分階段的 parent 產物，不經向量化階段轉交。
- **向量維度**：1024（見 [05_embed.md](05_embed.md)）。

## 3. 為什麼這樣做

docstore 模式是子母分層的標準做法（見 [04_chunk.md](04_chunk.md)）：只對 child 建索引，命中後取回 parent 交給 LLM。

## 4. 待定事項

| 事項 | 狀態 |
| --- | --- |
| schema | 擱置 |
| 入庫方式 | 擱置 |
| 索引類型 | 擱置 |
