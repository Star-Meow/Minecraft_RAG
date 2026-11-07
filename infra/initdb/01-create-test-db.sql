-- 只在資料目錄為空的首次啟動時由容器執行（docker-entrypoint-initdb.d）。
-- 已有資料的 volume 不會重跑；此時若測試庫不存在，請手動建立。
-- 這裡不建立 pgvector 擴充：CREATE EXTENSION vector 由使用者手動、兩個庫各執行一次（D7）。
CREATE DATABASE minecraft_rag_test;
