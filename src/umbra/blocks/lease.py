"""Lease en SQLite con fencing token: un solo worker activo por repositorio."""

import sqlite3
from datetime import UTC, datetime, timedelta

TTL_S = 60


def _ts(delta: float = 0) -> str:
    return (datetime.now(UTC) + timedelta(seconds=delta)).isoformat()


def acquire(conn: sqlite3.Connection, name: str, owner: str, ttl: float = TTL_S) -> int | None:
    """Devuelve el token si se obtuvo el lease; None si otro dueño lo tiene vigente."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT owner, token, expires_at FROM lease WHERE name = ?",
                           (name,)).fetchone()
        if row and row["owner"] != owner and row["expires_at"] > _ts():
            conn.execute("ROLLBACK")
            return None
        token = (row["token"] if row else 0) + 1
        conn.execute(
            "INSERT INTO lease (name, owner, token, expires_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET owner = excluded.owner, token = excluded.token,"
            " expires_at = excluded.expires_at",
            (name, owner, token, _ts(ttl)),
        )
        conn.execute("COMMIT")
        return token
    except Exception:
        conn.execute("ROLLBACK")
        raise


def renew(conn: sqlite3.Connection, name: str, token: int, ttl: float = TTL_S) -> bool:
    cur = conn.execute("UPDATE lease SET expires_at = ? WHERE name = ? AND token = ?",
                       (_ts(ttl), name, token))
    return cur.rowcount == 1


def holds(conn: sqlite3.Connection, name: str, token: int) -> bool:
    row = conn.execute("SELECT token, expires_at FROM lease WHERE name = ?", (name,)).fetchone()
    return bool(row and row["token"] == token and row["expires_at"] > _ts())


def release(conn: sqlite3.Connection, name: str, token: int) -> None:
    conn.execute("DELETE FROM lease WHERE name = ? AND token = ?", (name, token))
