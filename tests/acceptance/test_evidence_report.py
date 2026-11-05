import asyncio
import json

from textual.widgets import DataTable

from umbra.cli.watch import WatchApp
from umbra.routines import engine as eng
from umbra.unified import project


def feature_task(env):
    env.umbra("task", "add", "Sumar correctamente", "-d", "add debe sumar",
              "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "-r", "feature", "--foreground")
    return env.run()["status"]


def with_summary(env):
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace("summary = false", "summary = true"))


def test_summary_explains_the_work_in_evidence_and_pr(env):
    with_summary(env)
    env.mode("noop", "ok", "ok", "noop", "resumen")
    env.codex_mode("high:faltaba validar entradas. Detalle técnico", "clean")
    assert feature_task(env) == "WAITING_APPROVAL"
    assert env.attempts()[-1] == ("summary", "done")
    summary_call = env.claude_calls()[-1]
    assert "haiku" in summary_call["args"]
    assert "faltaba validar entradas" in summary_call["prompt"]  # sabe qué se corrigió
    assert env.prs()[0]["body"].startswith("**Qué se hizo**")  # el .cmd falso corta en el \n
    engine = eng.Engine(env.root, env.root / ".umbra", env.conn, project.load_project(env.root))
    assert "modo resumen" in engine.pr_body(engine.run_row(env.run()["id"]))

    out = env.umbra("evidence", "1").output
    assert "QUÉ SE HIZO" in out and "modo resumen" in out
    assert "lo cuenta el agente de resumen" in out
    assert "Criterios de aceptación: 1 de 1 cumplidos" in out
    assert "Revisión independiente: 2 rondas · 1 observación importante, corregida" in out
    assert "faltaba validar entradas → corregida" in out  # sin resumen por hallazgo: 1.ª frase
    assert "Pruebas:" in out and "sobre la versión final" in out
    raw = env.umbra("evidence", "1", "--raw").output
    assert "ejecución" in raw and "reviewer-strict" in raw


def test_a_failed_summary_never_blocks_the_delivery(env):
    with_summary(env)
    env.mode("noop", "ok", "noop", "error")
    assert feature_task(env) == "WAITING_APPROVAL"
    assert env.attempts()[-1] == ("summary", "error")
    out = env.umbra("evidence", "1").output
    assert "lo cuenta el constructor" in out and "modo ok" in out
    report = json.loads(env.umbra("evidence", "1", "--json").output)["report"]
    assert report["what_by"] == "el constructor"


def test_attempts_table_keeps_scroll_while_an_attempt_runs(env):
    env.mode("noop", "ok", "ok", "ok", "noop")
    env.codex_mode("high", "high", "clean")
    feature_task(env)
    conn = env.conn
    last = conn.execute("SELECT id FROM attempt ORDER BY started_at DESC LIMIT 1").fetchone()[0]
    conn.execute("UPDATE attempt SET status = 'running', ended_at = NULL WHERE id = ?", (last,))

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.1)
        async with app.run_test() as pilot:
            await pilot.pause(0.3)
            attempts = app.query_one("#attempts", DataTable)
            attempts.move_cursor(row=5)
            await pilot.pause(1.2)  # varios refrescos con la duración cambiando
            assert attempts.cursor_row == 5
            await pilot.press("q")

    asyncio.run(scenario())


def test_watch_remembers_the_chosen_theme(env):
    async def choose():
        app = WatchApp(env.root / ".umbra", interval=0.5)
        async with app.run_test() as pilot:
            app.theme = "nord"
            await pilot.pause(0.1)
            await pilot.press("q")

    async def reopen():
        app = WatchApp(env.root / ".umbra", interval=0.5)
        async with app.run_test() as pilot:
            await pilot.pause(0.1)
            assert app.theme == "nord"
            await pilot.press("q")

    asyncio.run(choose())
    asyncio.run(reopen())
