"""Cimientos de watch (spec 012): rendimiento, hora local, tema, avisos y agentes sin plugins."""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta

from umbra.cli import theme
from umbra.cli.watch import WatchApp
from umbra.cli.watch_data import Loader
from umbra.routines import engine
from umbra.unified import clock
from umbra.unified.store import new_id, now


def seed(env, tasks=50, events=2000):
    """Una base con historia: tareas aceptadas y una ejecución con muchos eventos."""
    conn = env.conn
    base = datetime(2026, 11, 3, 22, 0, tzinfo=UTC)
    ids = []
    for n in range(1, tasks + 1):
        tid = new_id()
        ids.append(tid)
        conn.execute("INSERT INTO task (id, number, title, acceptance, status, created_at,"
                     " updated_at) VALUES (?, ?, ?, '[\"x\"]', 'accepted', ?, ?)",
                     (tid, n, f"Tarea {n}", now(), now()))
    run_id = new_id()
    conn.execute("INSERT INTO run (id, task_id, routine, status, stage, base_sha, branch,"
                 " idempotency_key, created_at, updated_at) VALUES (?, ?, 'quick', 'RUNNING',"
                 " 'build', 'abc', 'umbra/1', ?, ?, ?)", (run_id, ids[0], new_id(), now(), now()))
    att = new_id()
    conn.execute("INSERT INTO attempt (id, run_id, stage, attempt_no, profile, agent, status,"
                 " started_at) VALUES (?, ?, 'build', 1, 'builder', 'claude-code', 'running', ?)",
                 (att, run_id, now()))
    conn.execute("INSERT INTO usage (id, attempt_id, agent, cost, invocation_id)"
                 " VALUES (?, ?, 'claude-code', '0.42', ?)", (new_id(), att, new_id()))
    conn.execute("BEGIN")
    for seq in range(1, events + 1):
        ts = (base + timedelta(seconds=seq * 90)).isoformat()  # cruza varios días
        conn.execute("INSERT INTO event (run_id, seq, type, origin, payload, created_at)"
                     " VALUES (?, ?, 'stage.started', 'worker', '{\"stage\": \"build\"}', ?)",
                     (run_id, seq, ts))
    conn.execute("COMMIT")
    conn.close()
    return run_id


def test_a_tick_without_changes_costs_nothing_and_with_changes_is_fast(env):
    seed(env)
    loader = Loader(env.root / ".umbra")
    first = loader.load(None, False, None, 0)
    assert first is not None and len(first.tasks) == 50 and len(first.log) == 2000
    assert first.selected == 1  # la tarea con la ejecución más reciente

    t0 = time.perf_counter()
    for _ in range(20):
        assert loader.load(1, False, first.run_id, first.last_seq) is None  # nada cambió
    unchanged = (time.perf_counter() - t0) / 20
    assert unchanged < 0.005, f"tick sin cambios: {unchanged * 1000:.1f} ms"

    other = env.conn
    other.execute("UPDATE task SET title = 'Cambiada' WHERE number = 7")
    other.close()
    t0 = time.perf_counter()
    snap = loader.load(1, False, first.run_id, first.last_seq)
    changed = time.perf_counter() - t0
    assert snap is not None and snap.tasks[6].title == "Cambiada" and snap.log == []
    assert changed < 0.05, f"tick con cambios: {changed * 1000:.1f} ms"
    loader.close()


def test_watch_updates_cells_in_place_and_keeps_the_cursor(env):
    seed(env, tasks=12, events=10)

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.1)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            table = app.query_one("#tasks")
            assert table.row_count == 12
            assert app.query_one("#log").lines[0].text.startswith("── ")  # separador de día
            await pilot.press("down", "down")
            await pilot.pause(0.3)
            assert app.selected == 3
            other = env.conn
            other.execute("UPDATE task SET title = 'Nueva' WHERE number = 9")
            other.close()
            await pilot.pause(0.5)
            assert table.get_cell("9", "title") == "Nueva"
            assert app.selected == 3 and table.cursor_row == 2  # el cursor no se movió
            await pilot.press("q")

    asyncio.run(scenario())


def test_times_are_shown_in_local_time_with_day_separators(env):
    ts = "2026-11-03T22:17:47.000000+00:00"
    assert clock.hhmm(ts) == clock.local(ts).strftime("%H:%M")
    assert clock.local(ts).utcoffset() == datetime.now().astimezone().utcoffset()
    assert clock.duration("2026-11-03T22:00:00+00:00", "2026-11-03T22:04:12+00:00") == "4m12s"
    assert clock.duration("2026-11-03T22:00:00+00:00", "2026-11-04T00:03:00+00:00") == "2h03m"
    seed(env, tasks=1, events=3000)  # 3000 eventos cada 90 s cruzan varios días
    out = env.umbra("log", "1").output
    assert out.count("── ") >= 2
    assert "T22:" not in out  # nada en ISO/UTC crudo


def test_log_json_keeps_utc_timestamps(env):
    seed(env, tasks=1, events=2)
    data = json.loads(env.umbra("log", "1", "--json").output)
    assert data[0]["created_at"].endswith("+00:00")


def test_theme_defaults_to_umbra_and_keeps_dracula_if_saved(env):
    seed(env, tasks=1, events=1)

    async def opens_with(expected, then=None):
        app = WatchApp(env.root / ".umbra", interval=0.5)
        async with app.run_test() as pilot:
            await pilot.pause(0.3)
            assert app.theme == expected
            assert "umbra" in app.available_themes and "umbra-claro" in app.available_themes
            if then:
                then(app)
                await pilot.pause(0.2)
            await pilot.press("q")

    asyncio.run(opens_with("umbra"))
    theme.save_prefs(theme="dracula")
    asyncio.run(opens_with("dracula", lambda app: setattr(app, "theme", "umbra-claro")))
    assert theme.load_prefs()["theme"] == "umbra-claro"
    theme.save_prefs(theme="no-existe")
    asyncio.run(opens_with("umbra"))


def test_state_colors_exist_in_every_theme(env):
    seed(env, tasks=1, events=1)

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.5)
        async with app.run_test() as pilot:
            await pilot.pause(0.2)
            for name in ("umbra", "umbra-claro", "dracula", "textual-light"):
                app.theme = name
                await pilot.pause(0.1)
                for key in theme.STATE_KEYS:
                    assert app.theme_variables[f"state-{key}"].startswith("#"), (name, key)
            await pilot.press("q")

    asyncio.run(scenario())


def test_engine_skips_desktop_alert_while_watch_is_open(env, monkeypatch):
    sent = []
    monkeypatch.setattr(engine.notify, "send", lambda title, body: sent.append(title))
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace("desktop = false", "desktop = true"))
    env.umbra("task", "add", "Sumar", "-a", "x")
    seed_conn = env.conn
    tid = seed_conn.execute("SELECT id FROM task").fetchone()[0]
    rid = new_id()
    seed_conn.execute("INSERT INTO run (id, task_id, routine, status, stage, base_sha, branch,"
                      " idempotency_key, created_at, updated_at) VALUES (?, ?, 'quick',"
                      " 'RUNNING', 'build', 'abc', 'b', ?, ?, ?)",
                      (rid, tid, new_id(), now(), now()))
    seed_conn.close()

    def alert():
        from umbra import service
        ctx = service.load(env.root)
        service.engine(ctx).event(rid, "run.blocked", reason="x")
        ctx.conn.close()

    alert()
    assert sent == ["umbra · tarea 1"]  # sin watch abierto: aviso del sistema

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.2)
        async with app.run_test() as pilot:
            await pilot.pause(0.3)
            alert()
            await pilot.pause(0.2)
            await pilot.press("q")

    asyncio.run(scenario())
    assert sent == ["umbra · tarea 1"]  # con watch abierto: ninguno más
    alert()
    assert len(sent) == 2  # al cerrar watch se libera y vuelven los avisos del sistema


def test_agents_do_not_inherit_the_users_global_claude_settings(env):
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    for call in env.claude_calls():
        args = call["args"]
        assert args[args.index("--setting-sources") + 1] == "project"
