"""SQL DDL migrations for the memory subsystem."""

from __future__ import annotations

MEMORY_MIGRATION: list[str] = [
    # ── Core file tracking ───────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS mem_files (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        path    TEXT    NOT NULL UNIQUE,
        type    TEXT    NOT NULL DEFAULT 'markdown',
        hash    TEXT    NOT NULL,
        size    INTEGER NOT NULL DEFAULT 0,
        indexed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    """,
    # ── Chunks ───────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS mem_chunks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id     INTEGER NOT NULL REFERENCES mem_files(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        content     TEXT    NOT NULL,
        heading     TEXT    NOT NULL DEFAULT '',
        token_count INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    """,
    # ── FTS5 virtual table ───────────────────────────────────────────────
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS mem_chunks_fts USING fts5(
        content, heading, content='mem_chunks', content_rowid='id'
    );
    """,
    # FTS triggers — keep the index in sync with the content table.
    """
    CREATE TRIGGER IF NOT EXISTS mem_chunks_ai AFTER INSERT ON mem_chunks BEGIN
        INSERT INTO mem_chunks_fts(rowid, content, heading)
        VALUES (new.id, new.content, new.heading);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS mem_chunks_ad AFTER DELETE ON mem_chunks BEGIN
        INSERT INTO mem_chunks_fts(mem_chunks_fts, rowid, content, heading)
        VALUES ('delete', old.id, old.content, old.heading);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS mem_chunks_au AFTER UPDATE ON mem_chunks BEGIN
        INSERT INTO mem_chunks_fts(mem_chunks_fts, rowid, content, heading)
        VALUES ('delete', old.id, old.content, old.heading);
        INSERT INTO mem_chunks_fts(rowid, content, heading)
        VALUES (new.id, new.content, new.heading);
    END;
    """,
    # ── Vector storage ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS mem_chunks_vec (
        chunk_id  INTEGER PRIMARY KEY REFERENCES mem_chunks(id) ON DELETE CASCADE,
        embedding BLOB NOT NULL
    );
    """,
    # ── Embedding cache ──────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS mem_embedding_cache (
        hash       TEXT PRIMARY KEY,
        model      TEXT NOT NULL,
        embedding  BLOB NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    """,
    # ── Recall log ───────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS mem_recalls (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        chunk_id    INTEGER NOT NULL REFERENCES mem_chunks(id) ON DELETE CASCADE,
        query       TEXT    NOT NULL,
        score       REAL    NOT NULL,
        session_id  TEXT    NOT NULL DEFAULT '',
        recalled_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_mem_recalls_chunk ON mem_recalls(chunk_id);
    """,
    # ── Key-value metadata ───────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS mem_meta (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    """,
]
