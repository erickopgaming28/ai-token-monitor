from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

SCHEMA_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL UNIQUE,
    first_seen    TEXT NOT NULL DEFAULT (datetime('now')),
    last_activity TEXT NOT NULL DEFAULT (datetime('now')),
    is_archived   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_projects_path ON projects(path);
CREATE INDEX IF NOT EXISTS idx_projects_last_activity ON projects(last_activity DESC);

CREATE TABLE IF NOT EXISTS providers (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    slug  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL REFERENCES providers(id),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    is_active   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider_id);
CREATE INDEX IF NOT EXISTS idx_models_slug ON models(slug);

CREATE TABLE IF NOT EXISTS pricing (
    id                           INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id                     INTEGER NOT NULL REFERENCES models(id),
    input_rate_per_million       REAL NOT NULL DEFAULT 0,
    output_rate_per_million      REAL NOT NULL DEFAULT 0,
    cache_read_rate_per_million  REAL NOT NULL DEFAULT 0,
    cache_write_rate_per_million REAL NOT NULL DEFAULT 0,
    effective_date               TEXT NOT NULL DEFAULT (date('now')),
    UNIQUE(model_id, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_pricing_model_date ON pricing(model_id, effective_date DESC);

CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    provider_id         INTEGER NOT NULL REFERENCES providers(id),
    session_external_id TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    last_activity       TEXT NOT NULL,
    UNIQUE(provider_id, session_external_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_external ON sessions(session_external_id);

CREATE TABLE IF NOT EXISTS token_events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         INTEGER NOT NULL REFERENCES sessions(id),
    project_id         INTEGER NOT NULL REFERENCES projects(id),
    provider_id        INTEGER NOT NULL REFERENCES providers(id),
    model_id           INTEGER NOT NULL REFERENCES models(id),
    message_id         TEXT NOT NULL,
    input_tokens       INTEGER NOT NULL DEFAULT 0,
    output_tokens      INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    timestamp          TEXT NOT NULL,
    source_file        TEXT NOT NULL,
    source_line        INTEGER NOT NULL DEFAULT 0,
    data_quality       TEXT NOT NULL DEFAULT 'exact' CHECK(data_quality IN ('exact','estimated')),
    is_subagent        INTEGER NOT NULL DEFAULT 0,
    agent_id           TEXT,
    UNIQUE(provider_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_te_project ON token_events(project_id);
CREATE INDEX IF NOT EXISTS idx_te_session ON token_events(session_id);
CREATE INDEX IF NOT EXISTS idx_te_timestamp ON token_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_te_message ON token_events(message_id);

CREATE TABLE IF NOT EXISTS daily_aggregates (
    project_id        INTEGER NOT NULL REFERENCES projects(id),
    provider_id       INTEGER NOT NULL REFERENCES providers(id),
    model_id          INTEGER NOT NULL REFERENCES models(id),
    date              TEXT NOT NULL,
    total_input       INTEGER NOT NULL DEFAULT 0,
    total_output      INTEGER NOT NULL DEFAULT 0,
    total_cache_read  INTEGER NOT NULL DEFAULT 0,
    total_cache_write INTEGER NOT NULL DEFAULT 0,
    event_count       INTEGER NOT NULL DEFAULT 0,
    estimated_cost    REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, provider_id, model_id, date)
);

CREATE TABLE IF NOT EXISTS scan_state (
    file_path     TEXT PRIMARY KEY,
    byte_offset   INTEGER NOT NULL DEFAULT 0,
    last_scanned  TEXT NOT NULL DEFAULT (datetime('now')),
    file_size     INTEGER NOT NULL DEFAULT 0,
    file_mtime    REAL NOT NULL DEFAULT 0
);
"""


class Database:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._get_conn()

    def initialize(self) -> None:
        with self._lock:
            self.conn.executescript(SCHEMA_DDL)
            self._seed_default_data()
            self.conn.commit()

    def _seed_default_data(self) -> None:
        row = self.conn.execute("SELECT COUNT(*) FROM providers").fetchone()
        if row[0] > 0:
            return

        pricing_file = Path(__file__).parent.parent / "config" / "default_pricing.json"
        data = json.loads(pricing_file.read_text(encoding="utf-8"))

        provider_ids: dict[str, int] = {}
        for p in data["providers"]:
            cur = self.conn.execute(
                "INSERT INTO providers (name, slug) VALUES (?, ?)",
                (p["name"], p["slug"]),
            )
            provider_ids[p["slug"]] = cur.lastrowid

        model_ids: dict[str, int] = {}
        for m in data["models"]:
            pid = provider_ids[m["provider"]]
            cur = self.conn.execute(
                "INSERT INTO models (provider_id, name, slug) VALUES (?, ?, ?)",
                (pid, m["name"], m["slug"]),
            )
            model_ids[m["slug"]] = cur.lastrowid

        for pr in data["pricing"]:
            mid = model_ids[pr["model"]]
            self.conn.execute(
                """INSERT INTO pricing
                   (model_id, input_rate_per_million, output_rate_per_million,
                    cache_read_rate_per_million, cache_write_rate_per_million)
                   VALUES (?, ?, ?, ?, ?)""",
                (mid, pr["input"], pr["output"], pr["cache_read"], pr["cache_write"]),
            )

    # ── Scan State ──────────────────────────────────────────────

    def get_scan_state(self, file_path: str) -> Optional[dict]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM scan_state WHERE file_path = ?", (file_path,)
            ).fetchone()
            return dict(row) if row else None

    def upsert_scan_state(
        self, file_path: str, byte_offset: int, file_mtime: float, file_size: int
    ) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT INTO scan_state (file_path, byte_offset, file_mtime, file_size, last_scanned)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(file_path) DO UPDATE SET
                     byte_offset = excluded.byte_offset,
                     file_mtime = excluded.file_mtime,
                     file_size = excluded.file_size,
                     last_scanned = datetime('now')""",
                (file_path, byte_offset, file_mtime, file_size),
            )
            self.conn.commit()

    # ── Providers & Models ──────────────────────────────────────

    def get_provider_id(self, slug: str) -> Optional[int]:
        row = self.conn.execute(
            "SELECT id FROM providers WHERE slug = ?", (slug,)
        ).fetchone()
        return row["id"] if row else None

    def get_model_id(self, slug: str) -> Optional[int]:
        row = self.conn.execute(
            "SELECT id FROM models WHERE slug = ?", (slug,)
        ).fetchone()
        return row["id"] if row else None

    def ensure_model(self, model_slug: str, provider_slug: str) -> int:
        with self._lock:
            mid = self.get_model_id(model_slug)
            if mid:
                return mid
            pid = self.get_provider_id(provider_slug)
            if not pid:
                return -1
            cur = self.conn.execute(
                "INSERT INTO models (provider_id, name, slug, is_active) VALUES (?, ?, ?, 0)",
                (pid, model_slug, model_slug),
            )
            self.conn.execute(
                """INSERT INTO pricing
                   (model_id, input_rate_per_million, output_rate_per_million,
                    cache_read_rate_per_million, cache_write_rate_per_million)
                   VALUES (?, 0, 0, 0, 0)""",
                (cur.lastrowid,),
            )
            self.conn.commit()
            return cur.lastrowid

    # ── Projects ────────────────────────────────────────────────

    def ensure_project(self, path: str, name: str) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM projects WHERE path = ?", (path,)
            ).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE projects SET last_activity = datetime('now') WHERE id = ?",
                    (row["id"],),
                )
                self.conn.commit()
                return row["id"]
            cur = self.conn.execute(
                "INSERT INTO projects (name, path) VALUES (?, ?)", (name, path)
            )
            self.conn.commit()
            return cur.lastrowid

    # ── Sessions ────────────────────────────────────────────────

    def ensure_session(
        self, session_external_id: str, project_id: int, provider_id: int, timestamp: str
    ) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM sessions WHERE provider_id = ? AND session_external_id = ?",
                (provider_id, session_external_id),
            ).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE sessions SET last_activity = ? WHERE id = ? AND last_activity < ?",
                    (timestamp, row["id"], timestamp),
                )
                self.conn.commit()
                return row["id"]
            cur = self.conn.execute(
                """INSERT INTO sessions (project_id, provider_id, session_external_id, started_at, last_activity)
                   VALUES (?, ?, ?, ?, ?)""",
                (project_id, provider_id, session_external_id, timestamp, timestamp),
            )
            self.conn.commit()
            return cur.lastrowid

    # ── Token Events ────────────────────────────────────────────

    def insert_token_event(
        self,
        session_id: int,
        project_id: int,
        provider_id: int,
        model_id: int,
        message_id: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
        timestamp: str,
        source_file: str,
        source_line: int = 0,
        data_quality: str = "exact",
        is_subagent: bool = False,
        agent_id: str | None = None,
    ) -> bool:
        with self._lock:
            try:
                self.conn.execute(
                    """INSERT OR IGNORE INTO token_events
                       (session_id, project_id, provider_id, model_id, message_id,
                        input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                        timestamp, source_file, source_line, data_quality, is_subagent, agent_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id, project_id, provider_id, model_id, message_id,
                        input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                        timestamp, source_file, source_line, data_quality,
                        1 if is_subagent else 0, agent_id,
                    ),
                )
                self.conn.commit()
                return self.conn.total_changes > 0
            except sqlite3.IntegrityError:
                return False

    def bulk_insert_token_events(self, events: list[tuple]) -> int:
        with self._lock:
            self.conn.executemany(
                """INSERT OR IGNORE INTO token_events
                   (session_id, project_id, provider_id, model_id, message_id,
                    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                    timestamp, source_file, source_line, data_quality, is_subagent, agent_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                events,
            )
            count = self.conn.total_changes
            self.conn.commit()
            return count

    # ── Pricing ─────────────────────────────────────────────────

    def get_current_pricing(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT m.slug, p.input_rate_per_million, p.output_rate_per_million,
                      p.cache_read_rate_per_million, p.cache_write_rate_per_million
               FROM pricing p
               JOIN models m ON p.model_id = m.id
               WHERE p.effective_date = (
                   SELECT MAX(p2.effective_date) FROM pricing p2 WHERE p2.model_id = p.model_id
               )"""
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Aggregates ──────────────────────────────────────────────

    def rebuild_daily_aggregates(self, project_ids: list[int] | None = None) -> None:
        with self._lock:
            where = ""
            params: tuple = ()
            if project_ids:
                placeholders = ",".join("?" * len(project_ids))
                where = f"WHERE te.project_id IN ({placeholders})"
                params = tuple(project_ids)

            self.conn.execute(
                f"""INSERT OR REPLACE INTO daily_aggregates
                    (project_id, provider_id, model_id, date,
                     total_input, total_output, total_cache_read, total_cache_write,
                     event_count, estimated_cost)
                    SELECT
                        te.project_id, te.provider_id, te.model_id,
                        date(te.timestamp) as d,
                        SUM(te.input_tokens),
                        SUM(te.output_tokens),
                        SUM(te.cache_read_tokens),
                        SUM(te.cache_write_tokens),
                        COUNT(*),
                        COALESCE(
                            SUM(te.input_tokens) * MAX(p.input_rate_per_million) / 1000000.0 +
                            SUM(te.output_tokens) * MAX(p.output_rate_per_million) / 1000000.0 +
                            SUM(te.cache_read_tokens) * MAX(p.cache_read_rate_per_million) / 1000000.0 +
                            SUM(te.cache_write_tokens) * MAX(p.cache_write_rate_per_million) / 1000000.0,
                            0
                        )
                    FROM token_events te
                    LEFT JOIN pricing p ON p.model_id = te.model_id
                        AND p.effective_date = (
                            SELECT MAX(p2.effective_date) FROM pricing p2
                            WHERE p2.model_id = te.model_id
                        )
                    {where}
                    GROUP BY te.project_id, te.provider_id, te.model_id, d""",
                params,
            )
            self.conn.commit()

    # ── Query helpers for UI ────────────────────────────────────

    def get_all_projects_summary(self, period: str = "all") -> list[dict]:
        date_filter = self._period_filter(period)
        rows = self.conn.execute(
            f"""SELECT
                    p.id, p.name, p.path, p.last_activity,
                    COALESCE(SUM(da.total_input), 0) as total_input,
                    COALESCE(SUM(da.total_output), 0) as total_output,
                    COALESCE(SUM(da.total_cache_read), 0) as total_cache_read,
                    COALESCE(SUM(da.total_cache_write), 0) as total_cache_write,
                    COALESCE(SUM(da.estimated_cost), 0) as total_cost,
                    COALESCE(SUM(da.event_count), 0) as event_count
                FROM projects p
                LEFT JOIN daily_aggregates da ON da.project_id = p.id
                    {date_filter}
                WHERE p.is_archived = 0
                GROUP BY p.id
                ORDER BY p.last_activity DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_project_detail(self, project_id: int, period: str = "all") -> dict:
        date_filter = self._period_filter(period)
        project = dict(
            self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )

        breakdown = self.conn.execute(
            f"""SELECT
                    prov.name as provider_name, prov.slug as provider_slug,
                    m.name as model_name, m.slug as model_slug,
                    COALESCE(SUM(da.total_input), 0) as total_input,
                    COALESCE(SUM(da.total_output), 0) as total_output,
                    COALESCE(SUM(da.total_cache_read), 0) as total_cache_read,
                    COALESCE(SUM(da.total_cache_write), 0) as total_cache_write,
                    COALESCE(SUM(da.estimated_cost), 0) as cost
                FROM daily_aggregates da
                JOIN providers prov ON prov.id = da.provider_id
                JOIN models m ON m.id = da.model_id
                WHERE da.project_id = ?
                    {date_filter}
                GROUP BY da.provider_id, da.model_id
                ORDER BY cost DESC""",
            (project_id,),
        ).fetchall()

        daily = self.conn.execute(
            f"""SELECT
                    da.date,
                    SUM(da.total_input) as input,
                    SUM(da.total_output) as output,
                    SUM(da.estimated_cost) as cost
                FROM daily_aggregates da
                WHERE da.project_id = ?
                    {date_filter}
                GROUP BY da.date
                ORDER BY da.date DESC
                LIMIT 30""",
            (project_id,),
        ).fetchall()

        session_count = self.conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_id = ?", (project_id,)
        ).fetchone()[0]

        return {
            **project,
            "breakdown": [dict(r) for r in breakdown],
            "daily_history": [dict(r) for r in daily],
            "session_count": session_count,
        }

    def _period_filter(self, period: str) -> str:
        if period == "today":
            return "AND da.date = date('now')"
        elif period == "week":
            return "AND da.date >= date('now', '-7 days')"
        elif period == "month":
            return "AND da.date >= date('now', '-30 days')"
        return ""

    def get_global_cost(self, period: str = "all") -> float:
        date_filter = self._period_filter(period).replace("AND da.", "AND ")
        row = self.conn.execute(
            f"SELECT COALESCE(SUM(estimated_cost), 0) FROM daily_aggregates da WHERE 1=1 {date_filter}"
        ).fetchone()
        return row[0]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
