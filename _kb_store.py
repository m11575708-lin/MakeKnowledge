"""
_kb_store.py - 知識庫文件索引（SQLite，只用標準庫 sqlite3）

資料表：
  documents    匯入後的文件元資料（page02 的 skill_26 會查這張表）
  chunks       滑動視窗切片
  row_hashes   已收錄段落／資料列的 SHA-256（跨次匯入去重用）
  imports      每次匯入的總覽
  import_files 每次匯入中每個檔案的結果（匯入紀錄表）
所有查詢一律使用參數化（?），不拼接字串。
匯入的檔案預設為「內部資料」(is_public = 0)，不會出現在民眾可見的文件清單裡。
"""

import json
import os
import sqlite3
from contextlib import closing

try:
    from ._common import project_root
except ImportError:
    from _common import project_root

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY, source_name TEXT NOT NULL, file_type TEXT NOT NULL, category TEXT NOT NULL,
    file_sha256 TEXT NOT NULL UNIQUE, stored_name TEXT, ext TEXT, is_public INTEGER NOT NULL DEFAULT 0,
    license_type TEXT NOT NULL, source_url TEXT NOT NULL, updated_at TEXT NOT NULL, data_latest TEXT,
    content_preview TEXT NOT NULL, char_count INTEGER NOT NULL, row_count INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL, imported_at TEXT NOT NULL, import_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL, text TEXT NOT NULL, text_sha256 TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE TABLE IF NOT EXISTS row_hashes (hash TEXT PRIMARY KEY, doc_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports (
    import_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, n_files INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS import_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT, import_id TEXT NOT NULL, file_name TEXT NOT NULL, file_type TEXT NOT NULL,
    status TEXT NOT NULL, rows_read INTEGER, rows_cleaned INTEGER, duplicates INTEGER, duplicate_rate_pct REAL,
    chunks INTEGER, failure_stage TEXT, failure_reason TEXT, detail_json TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dataset_publishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, dataset TEXT NOT NULL, file_name TEXT, ok INTEGER NOT NULL, n_rows INTEGER,
    backup TEXT, error TEXT, published_at TEXT NOT NULL);
"""


def db_path() -> str:
    return os.path.join(project_root(), "data", "kb_index.sqlite")


def connect(path: str = None) -> sqlite3.Connection:
    path = path or db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def existing_hashes(conn, hashes):
    """回傳 hashes 中已存在於資料庫的集合（分批查詢避開參數數量上限）。"""
    found = set()
    hs = list(hashes)
    for i in range(0, len(hs), 500):
        part = hs[i:i + 500]
        q = "SELECT hash FROM row_hashes WHERE hash IN (%s)" % ",".join("?" * len(part))
        found.update(r[0] for r in conn.execute(q, part))
    return found


def doc_by_sha(conn, sha):
    r = conn.execute("SELECT doc_id, source_name, imported_at FROM documents WHERE file_sha256 = ?", (sha,)).fetchone()
    return {"doc_id": r[0], "source_name": r[1], "imported_at": r[2]} if r else None


def start_import(conn, import_id, started_at, n_files):
    with conn:
        conn.execute("INSERT INTO imports (import_id, started_at, status, n_files) VALUES (?,?,?,?)",
                     (import_id, started_at, "running", n_files))


def finish_import(conn, import_id, finished_at, status):
    with conn:
        conn.execute("UPDATE imports SET finished_at = ?, status = ? WHERE import_id = ?", (finished_at, status, import_id))


def log_file(conn, import_id, rec, created_at):
    with conn:
        conn.execute(
            "INSERT INTO import_files (import_id, file_name, file_type, status, rows_read, rows_cleaned, duplicates, "
            "duplicate_rate_pct, chunks, failure_stage, failure_reason, detail_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (import_id, rec["file_name"], rec["file_type"], rec["status"], rec.get("rows_read"), rec.get("rows_cleaned"),
             rec.get("duplicates"), rec.get("duplicate_rate_pct"), rec.get("chunks"), rec.get("failure_stage"),
             rec.get("failure_reason"), json.dumps(rec.get("stages") or {}, ensure_ascii=False), created_at))


def recent_logs(limit=30):
    limit = max(1, min(int(limit), 200))
    with closing(connect()) as conn:
        cur = conn.execute(
            "SELECT f.import_id, f.created_at, f.file_name, f.file_type, f.status, f.rows_read, f.rows_cleaned, f.duplicates, "
            "f.duplicate_rate_pct, f.chunks, f.failure_stage, f.failure_reason, f.detail_json FROM import_files f "
            "ORDER BY f.id DESC LIMIT ?", (limit,))
        cols = [c[0] for c in cur.description]
        out = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            try:
                d["stages"] = json.loads(d.pop("detail_json") or "{}")
            except ValueError:
                d["stages"] = {}
            out.append(d)
        return out


def totals():
    with closing(connect()) as conn:
        return {"documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]}


def log_publish(pub: dict, published_at: str):
    """記錄一次「發佈為分析資料集」的結果（page04 用來顯示各資料集最近一次發佈）。"""
    with closing(connect()) as conn:
        with conn:
            conn.execute(
                "INSERT INTO dataset_publishes (dataset, file_name, ok, n_rows, backup, error, published_at) VALUES (?,?,?,?,?,?,?)",
                (pub.get("dataset"), pub.get("file"), 1 if pub.get("ok") else 0, pub.get("rows"), pub.get("backup"),
                 (pub.get("error") or "")[:300] or None, published_at))
