"""Persistence layer: a small SQLite store so the tracker remembers.

Keeps across runs:

  * `emails`  — every email we've already classified, plus its classification
                and whether it's been responded to. On re-runs we read the
                cached classification instead of calling Claude again.
  * `deals`   — an accumulating record of every deal we've ever seen, with its
                latest stage and last activity. Deals persist even if they're
                not in the current batch of email.
  * `todos`   — manual to-do items you add yourself (separate from the
                auto-generated "needs reply" items derived from email).

Uses only the standard library (`sqlite3`). Thread-safe: the web dashboard
runs the poller and request handlers on different threads, so the connection
is opened with check_same_thread=False and all access is serialized with a
lock.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from classifier import Classification
from email_source import Email

DEFAULT_DB = str(Path(__file__).with_name("tracker.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str = DEFAULT_DB):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS emails (
                    id             TEXT PRIMARY KEY,
                    from_name      TEXT,
                    from_addr      TEXT,
                    subject        TEXT,
                    received       TEXT,
                    body           TEXT,
                    classification TEXT    NOT NULL,   -- full Classification as JSON
                    needs_reply    INTEGER NOT NULL,
                    deal_name      TEXT,
                    responded      INTEGER NOT NULL DEFAULT 0,
                    classified_at  TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS deals (
                    name          TEXT PRIMARY KEY,
                    stage         TEXT,
                    first_seen    TEXT    NOT NULL,
                    last_activity TEXT    NOT NULL,
                    email_count   INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS todos (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    text       TEXT    NOT NULL,
                    done       INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT    NOT NULL
                );
                """
            )
            self.conn.commit()

    # --- emails ----------------------------------------------------------

    def get_email(self, email_id: str) -> Optional[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM emails WHERE id = ?", (email_id,)
            ).fetchone()

    def save_email(self, email: Email, c: Classification) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO emails
                    (id, from_name, from_addr, subject, received, body,
                     classification, needs_reply, deal_name, responded, classified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                        COALESCE((SELECT responded FROM emails WHERE id = ?), 0), ?)
                """,
                (
                    email.id, email.from_name, email.from_addr, email.subject,
                    email.received, email.body, c.model_dump_json(),
                    int(c.needs_reply), c.deal_name, email.id, _now(),
                ),
            )
            self.conn.commit()

    def mark_responded(self, email_id: str, responded: bool = True) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "UPDATE emails SET responded = ? WHERE id = ?",
                (int(responded), email_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def get_to_respond(self) -> list[sqlite3.Row]:
        """Emails that still need a reply — the live to-do feed from email."""
        with self._lock:
            return self.conn.execute(
                """
                SELECT * FROM emails
                 WHERE needs_reply = 1 AND responded = 0
                 ORDER BY classified_at DESC
                """
            ).fetchall()

    def count_emails(self) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) AS n FROM emails").fetchone()["n"]

    # --- deals -----------------------------------------------------------

    def upsert_deal(self, name: str, stage: Optional[str], activity: str) -> None:
        with self._lock:
            existing = self.conn.execute(
                "SELECT stage, last_activity, email_count FROM deals WHERE name = ?",
                (name,),
            ).fetchone()

            if existing is None:
                self.conn.execute(
                    """
                    INSERT INTO deals (name, stage, first_seen, last_activity, email_count)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (name, stage, activity, activity),
                )
            else:
                # Keep the most recent activity timestamp; advance the stage if known.
                last_activity = max(existing["last_activity"], activity)
                new_stage = stage or existing["stage"]
                self.conn.execute(
                    """
                    UPDATE deals
                       SET stage = ?, last_activity = ?, email_count = email_count + 1
                     WHERE name = ?
                    """,
                    (new_stage, last_activity, name),
                )
            self.conn.commit()

    def get_deals(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                """
                SELECT
                    d.name,
                    d.stage,
                    d.last_activity,
                    d.email_count,
                    (SELECT COUNT(*) FROM emails e
                       WHERE e.deal_name = d.name
                         AND e.needs_reply = 1
                         AND e.responded = 0) AS awaiting
                FROM deals d
                ORDER BY d.last_activity DESC
                """
            ).fetchall()

    # --- manual to-dos ---------------------------------------------------

    def add_todo(self, text: str) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO todos (text, done, created_at) VALUES (?, 0, ?)",
                (text, _now()),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_todos(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM todos ORDER BY done ASC, created_at DESC"
            ).fetchall()

    def set_todo_done(self, todo_id: int, done: bool = True) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "UPDATE todos SET done = ? WHERE id = ?", (int(done), todo_id)
            )
            self.conn.commit()
            return cur.rowcount > 0

    def delete_todo(self, todo_id: int) -> bool:
        with self._lock:
            cur = self.conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
            self.conn.commit()
            return cur.rowcount > 0

    # --- maintenance -----------------------------------------------------

    def reset(self) -> None:
        with self._lock:
            self.conn.executescript(
                "DELETE FROM emails; DELETE FROM deals; DELETE FROM todos;"
            )
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()
