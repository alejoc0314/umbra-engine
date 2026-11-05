import sqlite3

import pytest

from umbra.unified import store


def test_v2_conserva_datos_y_crea_estructuras(tmp_path):
    conn = sqlite3.connect(tmp_path / "x.db", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(f"BEGIN;\n{store._V1}\nPRAGMA user_version = 1;\nCOMMIT;")
    conn.execute("INSERT INTO spec VALUES ('s1', 1, 'h', 'cuerpo', 'a', 'now')")
    conn.execute("INSERT INTO task (id, number, title, created_at, updated_at)"
                 " VALUES ('t1', 1, 'vieja', 'now', 'now')")
    conn.execute("INSERT INTO usage (id, agent, invocation_id) VALUES ('u1', 'claude', 'i1')")

    assert store.migrate(conn) == len(store.MIGRATIONS)  # V3+ se suman encima

    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(store.MIGRATIONS)
    assert conn.execute("SELECT title, spec_dir, requirements FROM task").fetchone()[:] == (
        "vieja", None, "[]")
    assert conn.execute("SELECT body, dir FROM spec").fetchone()[:] == ("cuerpo", None)
    assert conn.execute("SELECT conversation_id FROM usage").fetchone()[0] is None
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"conversation", "task_story"} <= names


def test_indice_task_story(tmp_path):
    conn = store.connect(tmp_path / "y.db")

    def add(n, story):
        conn.execute("INSERT INTO task (id, number, title, spec_dir, story, created_at,"
                     " updated_at) VALUES (?, ?, 't', 'specs/a', ?, 'n', 'n')",
                     (f"id{n}", n, story))

    add(1, "US1")
    add(2, None)
    add(3, None)
    with pytest.raises(sqlite3.IntegrityError):
        add(4, "US1")
