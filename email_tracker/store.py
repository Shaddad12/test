"""Persistence layer: a small SQLite store so the tracker remembers.

Keeps two things across runs:

  * `emails`  — every email we've already classified, plus its classification
                and whether it's been responded to. On re-runs we read the
                cached classification instead of calling Claude again.
  * `deals`   — an accumulating record of every deal we've ever seen, with its
                latest stage and last activity. Deals persist even if they're
                not in the current batch of email.

Uses only the standard library (`sqlite3`) — no extra dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import sqlite3

from classifier import Classification
from email_source import Email

DEFAULT_DB = str(Path(__file__).with_name("tracker.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str = DEFAULT_DB):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
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
            """
        )
        self.conn.commit()

    # --- emails ----------------------------------------------------------

    def get_email(self, email_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM emails WHERE id = ?", (email_id,)
        ).fetchone()

    def save_email(self, email: Email, c: Classification) -> None:
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

    def mark_responded(self, email_id: str) -> bool:
        cur = self.conn.execute(
            "UPDATE emails SET responded = 1 WHERE id = ?", (email_id,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    # --- deals -----------------------------------------------------------

    def upsert_deal(self, name: str, stage: Optional[str], activity: str) -> None:
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

    # --- maintenance -----------------------------------------------------

    def reset(self) -> None:
        self.conn.executescript("DELETE FROM emails; DELETE FROM deals;")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
