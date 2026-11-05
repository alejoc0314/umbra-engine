"""Decidir desde watch (spec 014): autorizar cambios que la política frenó, responder al
agente, integrar en bloque, hallazgos abiertos y la base local al día."""

import asyncio
import json

from tests.conftest import git
from umbra import service
from umbra.cli.watch import AskText, Confirm, WatchApp
from umbra.routines import worker


def task(env, title="Sumar", *extra):
    env.umbra("task", "add", title, "-a", "add(2, 3) == 5", *extra)


def sync_worker(env):
    env.monkeypatch.setattr(worker, "spawn", lambda root: worker.work(root))


def test_allow_lets_the_agent_change_a_protected_test_and_resumes(env):
    env.mode("skip_test", "skip_test")  # el agente "arregla" desactivando el test existente
    task(env)
    env.umbra("run", "1", "--foreground")
    run = env.run()
    assert run["status"] == "BLOCKED"
    blocked = json.loads(env.conn.execute("SELECT payload FROM event WHERE type = 'run.blocked'"
                                          ).fetchone()[0])
    assert blocked["code"] == "policy"
    assert service.blocked_paths(service.load(), 1) == ["tests/test_calc.py"]

    out = env.umbra("task", "allow", "1", "tests/test_calc.py", "--json").output
    data = json.loads(out)
    assert data["allowed"] == ["tests/test_calc.py"] and data["resumed_from"] == "build"
    worker.work(env.root)  # el reintento corre con el permiso
    assert env.run()["status"] == "WAITING_APPROVAL"
    # el agente recibió el permiso en su sobre y queda registrado quién lo dio
    assert "cambiar estos archivos en esta tarea" in env.claude_calls()[-1]["prompt"]
    allowed = env.conn.execute("SELECT payload FROM event WHERE type = 'policy.allowed'"
                               ).fetchone()[0]
    assert "tests/test_calc.py" in allowed


def test_answer_reaches_the_agent_and_resumes_the_stage(env):
    env.mode("blocked", "ok")
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    out = json.loads(env.umbra("task", "answer", "1", "Los negativos se suman igual.",
                               "--json").output)
    assert out["resumed_from"] == "build"
    worker.work(env.root)
    assert env.run()["status"] == "WAITING_APPROVAL"
    prompt = env.claude_calls()[-1]["prompt"]
    assert "Respuesta de la persona" in prompt and "Los negativos se suman igual." in prompt
    env.umbra("task", "answer", "1", "otra", ok=False)  # ya no está detenida


def test_approve_all_integrates_every_waiting_task_and_updates_local_main(env):
    task(env, "Una")
    env.umbra("run", "1", "--foreground")
    task(env, "Dos")
    env.umbra("run", "2", "--foreground")
    assert service.waiting_tasks(service.load()) == [1, 2]
    before = git(env.root, "rev-parse", "HEAD").stdout.strip()
    out = env.umbra("approve", "--all", input="y\n").output
    assert out.count("integrada") == 2  # (la salida trae colores: no se compara la frase entera)
    assert env.run(1)["status"] == "SUCCEEDED" and env.run(2)["status"] == "SUCCEEDED"
    assert git(env.root, "rev-parse", "HEAD").stdout.strip() != before  # main local al día
    assert git(env.root, "status", "--porcelain", "--untracked-files=no").stdout == ""


def test_open_findings_can_be_decided_even_when_nothing_blocks(env):
    env.codex_mode("medium")
    env.mode("noop", "ok", "ok", "noop")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace('default_routine = "quick"',
                                           'default_routine = "feature"'))
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    opened = service.open_findings(service.load(), 1)
    assert opened and all(f["severity"] == "medium" for f in opened)
    out = env.umbra("finding", "list", "1").output
    assert "medium" in out
    env.umbra("finding", "waive", "1", "-m", "no aplica")
    assert service.open_findings(service.load(), 1) == []


def test_watch_decision_panel_authorizes_and_answers(env):
    env.mode("skip_test", "skip_test")
    task(env)
    env.umbra("run", "1", "--foreground")
    sync_worker(env)

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.2)
        notes = []
        original = app.notify
        app.notify = lambda message, **kw: (notes.append(message), original(message, **kw))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.6)
            assert app._kind == "blocked" and app._decision["paths"] == ["tests/test_calc.py"]
            assert app.check_action("accept", ()) is True  # «a» = autorizar
            assert "Decisión" in app.query_one("#situation").border_title
            await pilot.press("a")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Confirm)
            await pilot.press("y")
            for _ in range(400):
                await pilot.pause(0.1)
                if not app.busy and env.run()["status"] == "WAITING_APPROVAL":
                    break
            assert env.run()["status"] == "WAITING_APPROVAL"
            assert any("umbra task allow 1 tests/test_calc.py" in n for n in notes)
            await pilot.press("q")

    asyncio.run(scenario())


def test_watch_r_answers_when_the_agent_asked(env):
    env.mode("blocked", "ok")
    task(env)
    env.umbra("run", "1", "--foreground")
    sync_worker(env)

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.2)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.6)
            assert app._decision["code"] == "agent_questions"
            await pilot.press("r")
            await pilot.pause(0.3)
            assert isinstance(app.screen, AskText)
            await pilot.press(*"se suman igual", "enter")
            for _ in range(400):
                await pilot.pause(0.1)
                if not app.busy and env.run()["status"] == "WAITING_APPROVAL":
                    break
            assert env.run()["status"] == "WAITING_APPROVAL"
            await pilot.press("q")

    asyncio.run(scenario())
