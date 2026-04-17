"""Database schema migrations for PolarsClaw."""

from __future__ import annotations

CURRENT_VERSION = 1

MIGRATIONS: dict[int, list[str]] = {
    1: [
        # ── version tracking ─────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version  INTEGER PRIMARY KEY,
            applied  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        """,
        # ── sessions ─────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            title       TEXT,
            scope       TEXT    NOT NULL DEFAULT 'main',
            peer_id     TEXT,
            channel_id  TEXT,
            metadata    TEXT    NOT NULL DEFAULT '{}',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        """,
        # ── messages ─────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role        TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            metadata    TEXT    NOT NULL DEFAULT '{}',
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, timestamp);
        """,
        # ── memories ─────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS memories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT    NOT NULL UNIQUE,
            value       TEXT    NOT NULL,
            type        TEXT    NOT NULL DEFAULT 'general',
            session_id  TEXT    REFERENCES sessions(id) ON DELETE SET NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        """,
        # ── memories FTS5 ────────────────────────────────────────────────
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            key, value, type,
            content=memories,
            content_rowid=id
        );
        """,
        # Triggers to keep FTS in sync
        """
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, key, value, type)
            VALUES (new.id, new.key, new.value, new.type);
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, value, type)
            VALUES ('delete', old.id, old.key, old.value, old.type);
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, value, type)
            VALUES ('delete', old.id, old.key, old.value, old.type);
            INSERT INTO memories_fts(rowid, key, value, type)
            VALUES (new.id, new.key, new.value, new.type);
        END;
        """,
        # ── cron jobs ────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            schedule    TEXT    NOT NULL,
            type        TEXT    NOT NULL DEFAULT 'cron',
            payload     TEXT    NOT NULL DEFAULT '{}',
            enabled     INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        """,
        # ── cron results ─────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS cron_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      INTEGER NOT NULL REFERENCES cron_jobs(id) ON DELETE CASCADE,
            status      TEXT    NOT NULL,
            output      TEXT,
            error       TEXT,
            started_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_cron_results_job
            ON cron_results(job_id, started_at);
        """,
        # ── plugin state ─────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS plugin_state (
            plugin_name TEXT PRIMARY KEY,
            state       TEXT    NOT NULL DEFAULT '{}',
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        """,
    ],
}
