"""Instantáneas SVG de `umbra watch`: cómo se ve, para revisarlo con ojos en cada PR.

Se regeneran con `uv run pytest tests/acceptance/test_watch_look.py --snapshot-update`.
Solo estados deterministas: sin intentos en curso (su duración usa el reloj) ni versión real.
"""

import pytest

from umbra.cli import theme, watch
from umbra.cli.watch import WatchApp
from umbra.unified.store import new_id

FIXED = "2026-11-03T22:17:47.000000+00:00"


@pytest.fixture
def looks(env, monkeypatch):
    monkeypatch.setattr(watch.version, "label", lambda: "v1.0.0")
    monkeypatch.setenv("TEXTUAL_ANIMATIONS", "none")
    conn = env.conn
    rows = [("Preguntar en una línea y recibir la respuesta", "SUCCEEDED", "0.64"),
            ("Salida que otro programa puede leer", "WAITING_APPROVAL", "1.09"),
            ("Ver el costo de una tarea en forma corta", "BLOCKED", "0.60"),
            ("Seguir la misma conversación", None, None)]
    for n, (title, status, cost) in enumerate(rows, 12):
        tid = new_id()
        conn.execute("INSERT INTO task (id, number, title, about, acceptance, status, created_at,"
                     " updated_at) VALUES (?, ?, ?, 'Que el costo se lea corto.', '[\"x\"]',"
                     " ?, ?, ?)", (tid, n, title, "done" if status == "SUCCEEDED" else
                                   "accepted", FIXED, FIXED))
        if not status:
            continue
        rid = new_id()
        conn.execute("INSERT INTO run (id, task_id, routine, status, stage, base_sha, head_sha,"
                     " branch, idempotency_key, created_at, updated_at) VALUES (?, ?, 'feature',"
                     " ?, 'build', 'abc', 'def', 'umbra/x', ?, ?, ?)",
                     (rid, tid, status, new_id(), FIXED, FIXED))
        att = new_id()
        conn.execute("INSERT INTO attempt (id, run_id, stage, attempt_no, profile, agent,"
                     " status, started_at, ended_at) VALUES (?, ?, 'build', 1, 'builder-tdd',"
                     " 'claude-code', 'done', ?, '2026-11-03T22:21:59+00:00')",
                     (att, rid, FIXED))
        conn.execute("INSERT INTO usage (id, attempt_id, agent, cost, invocation_id)"
                     " VALUES (?, ?, 'claude-code', ?, ?)", (new_id(), att, cost, new_id()))
        for seq, (t, payload) in enumerate((
                ("run.started", '{"routine": "feature"}'),
                ("stage.started", '{"stage": "build"}'),
                ("run.blocked", '{"stage": "build", "reason": "el agente tiene preguntas",'
                                ' "code": "agent_questions", "details": {"stage": "build",'
                                ' "questions": ["¿Autorizas cambiar el test?"]}}')), 1):
            if t == "run.blocked" and status != "BLOCKED":
                continue
            conn.execute("INSERT INTO event (run_id, seq, type, origin, payload, created_at)"
                         " VALUES (?, ?, ?, 'worker', ?, ?)", (rid, seq, t, payload, FIXED))
    conn.close()
    return env


@pytest.mark.parametrize("theme_name", ["umbra", "dracula"])
def test_main_screen(looks, snap_compare, theme_name):
    theme.save_prefs(theme=theme_name)  # el guardado se aplica al abrir: sin cambio en caliente

    async def before(pilot):
        await pilot.pause(0.6)
        table = pilot.app.query_one("#tasks")
        table.move_cursor(row=table.get_row_index("14"))  # la detenida
        await pilot.pause(0.8)

    assert snap_compare(WatchApp(looks.root / ".umbra", interval=10), terminal_size=(120, 40),
                        run_before=before)
