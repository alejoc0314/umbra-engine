"""Registro de eventos append-only con seq por ejecución."""

import getpass
import json
import sqlite3

from umbra.unified.store import now


def add_event(conn: sqlite3.Connection, run_id: str | None, type_: str, origin: str = "worker",
              **payload) -> int:
    conn.execute("BEGIN IMMEDIATE")
    try:
        seq = None
        if run_id:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM event WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
        conn.execute(
            "INSERT INTO event (run_id, seq, type, origin, actor, payload, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, seq, type_, origin, _actor(),
             json.dumps(payload, ensure_ascii=False, default=str), now()),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return seq or 0


def events_for(conn: sqlite3.Connection, run_id: str, after: int = 0) -> list[dict]:
    rows = conn.execute(
        "SELECT seq, type, origin, actor, payload, created_at FROM event"
        " WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, after),
    )
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


def _actor() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"
