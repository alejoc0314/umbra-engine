"""Acciones desde `umbra watch`, manejadas por teclado como lo haría una persona."""

import asyncio

from umbra.cli.watch import Confirm, PickStage, WatchApp
from umbra.routines import worker


def task(env, *extra):
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5", *extra)


def sync_worker(env):
    """El worker corre dentro de la operación (en vez de un proceso aparte)."""
    env.monkeypatch.setattr(worker, "spawn", lambda root: worker.work(root))


def drive(env, scenario):
    async def main():
        app = WatchApp(env.root / ".umbra", interval=0.2)
        notes = []
        original = app.notify
        app.notify = lambda message, **kw: (notes.append(message), original(message, **kw))
        async with app.run_test() as pilot:
            await pilot.pause(0.4)
            await scenario(app, pilot, notes)
            await pilot.press("q")

    asyncio.run(main())


async def settle(app, pilot, timeout=40.0):
    """Espera a que termine la operación en curso y se refresque la pantalla."""
    for _ in range(int(timeout * 10)):
        await pilot.pause(0.1)
        if not app.busy:
            await pilot.pause(0.4)
            return
    raise AssertionError("la operación no terminó")


async def modal(app, pilot, kind, timeout=5.0):
    """Espera la ventana que abre una acción (la evidencia se prepara en un hilo)."""
    for _ in range(int(timeout * 20)):
        await pilot.pause(0.05)
        if isinstance(app.screen, kind):
            return
    raise AssertionError(f"no se abrió {kind.__name__}")


def test_accept_run_and_approve_from_watch(env):
    task(env, "--draft")
    sync_worker(env)

    async def scenario(app, pilot, notes):
        assert app._kind == "draft"
        assert app.check_action("approve", ()) is False  # no aplica: ni se muestra
        await pilot.press("A")
        assert not isinstance(app.screen, Confirm)
        await pilot.press("a")
        await settle(app, pilot)
        assert env.conn.execute("SELECT status FROM task").fetchone()[0] == "accepted"
        assert any("Equivale a: umbra task accept 1" in n for n in notes)
        await pilot.press("r")
        await settle(app, pilot)
        assert env.run()["status"] == "WAITING_APPROVAL" and app._kind == "waiting_approval"
        await pilot.press("A")
        await modal(app, pilot, Confirm)  # nunca de un solo tecleo
        await pilot.press("n")
        await pilot.pause(0.2)
        assert env.run()["status"] == "WAITING_APPROVAL"
        await pilot.press("A")
        await modal(app, pilot, Confirm)
        await pilot.press("y")
        await settle(app, pilot)
        assert env.run()["status"] == "SUCCEEDED"
        assert env.conn.execute("SELECT origin FROM event WHERE type = 'approval.approved'"
                                ).fetchone()[0] == "watch"

    drive(env, scenario)


def test_retry_a_stopped_task_choosing_the_stage(env):
    env.mode("broken")
    task(env)
    env.umbra("run", "1", "--foreground")
    sync_worker(env)

    async def scenario(app, pilot, notes):
        assert app._kind == "blocked"
        env.mode("ok")
        await pilot.press("r")
        await pilot.pause(0.2)
        assert isinstance(app.screen, PickStage)
        await pilot.press("enter")  # la sugerida: donde quedó (Construir)
        await settle(app, pilot)
        assert env.run()["status"] == "WAITING_APPROVAL"
        assert any("umbra retry 1 --from build" in n for n in notes)

    drive(env, scenario)


def test_start_over_and_reject(env):
    env.mode("broken")
    task(env)
    env.umbra("run", "1", "--foreground")
    first = env.run()["id"]
    sync_worker(env)

    async def scenario(app, pilot, notes):
        env.mode("ok")
        await pilot.press("n")
        await pilot.pause(0.2)
        await pilot.press("y")
        await settle(app, pilot)
        assert env.run()["id"] != first and env.run()["status"] == "WAITING_APPROVAL"
        await pilot.press("R")
        await pilot.pause(0.2)
        await pilot.press("ctrl+a", *"no convence", "enter")
        await settle(app, pilot)
        assert env.run()["status"] == "CANCELLED" and env.prs()[-1]["state"] == "CLOSED"
        reason = env.conn.execute("SELECT payload FROM event WHERE type = 'approval.rejected'"
                                  ).fetchone()[0]
        assert "no convence" in reason

    drive(env, scenario)


def test_pause_resume_cancel_and_evidence(env):
    task(env)
    env.monkeypatch.setattr(worker, "spawn", lambda root: None)  # se queda en cola
    env.umbra("run", "1")

    async def scenario(app, pilot, notes):
        assert app._kind == "queued"
        await pilot.press("p")
        await settle(app, pilot)
        assert env.run()["status"] == "PAUSED"
        await pilot.press("p")
        await settle(app, pilot)
        assert env.run()["status"] == "QUEUED"
        await pilot.press("e")
        await pilot.pause(0.3)
        assert app.tab == "evidence"  # la evidencia va en el panel derecho, no en una ventana
        await pilot.press("e")
        await pilot.pause(0.2)
        assert app.tab == "timeline"
        await pilot.press("c")
        await pilot.pause(0.2)
        assert isinstance(app.screen, Confirm)
        assert app.screen.query_one("#no").has_focus  # lo seguro viene seleccionado
        await pilot.press("y")
        await settle(app, pilot)
        assert env.run()["status"] == "CANCELLED"

    drive(env, scenario)


def test_errors_are_shown_without_breaking_the_screen(env):
    task(env)
    (env.root / ".mcp.json").write_text("{}")  # run se negará: configuración no confiada

    async def scenario(app, pilot, notes):
        await pilot.press("r")
        await settle(app, pilot)
        assert any(".mcp.json" in n for n in notes)
        assert env.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 0
        assert app.is_running

    drive(env, scenario)
