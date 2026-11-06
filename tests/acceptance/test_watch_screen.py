"""Pantalla principal de watch (spec 013): orden por atención, cabecera, pestañas, evidencia,
cambios y el agente en vivo."""

import asyncio
import json

from umbra.blocks import lease
from umbra.cli import agent_story
from umbra.cli.watch import WatchApp
from umbra.unified.store import new_id, now

TS = "2026-11-03T22:17:47.000000+00:00"


def seed_states(env):
    """Cuatro tareas: en borrador, trabajando, detenida e integrada (en ese orden de número)."""
    conn = env.conn
    plan = [("Borrador", "draft", None), ("Trabajando", "accepted", "RUNNING"),
            ("Detenida", "accepted", "BLOCKED"), ("Integrada", "done", "SUCCEEDED")]
    for n, (title, tstatus, rstatus) in enumerate(plan, 1):
        tid = new_id()
        conn.execute("INSERT INTO task (id, number, title, acceptance, status, created_at,"
                     " updated_at) VALUES (?, ?, ?, '[\"x\"]', ?, ?, ?)",
                     (tid, n, title, tstatus, TS, TS))
        if rstatus:
            conn.execute("INSERT INTO run (id, task_id, routine, status, stage, base_sha,"
                         " branch, idempotency_key, created_at, updated_at) VALUES (?, ?,"
                         " 'quick', ?, 'build', 'abc', 'b', ?, ?, ?)",
                         (new_id(), tid, rstatus, new_id(), TS, TS))
    conn.close()


def drive(env, scenario, size=(120, 40)):
    async def main():
        app = WatchApp(env.root / ".umbra", interval=0.2)
        async with app.run_test(size=size) as pilot:
            await pilot.pause(0.5)
            await scenario(app, pilot)
            await pilot.press("q")

    asyncio.run(main())


def test_attention_first_and_header(env):
    seed_states(env)
    conn = env.conn
    lease.acquire(conn, "worker", "1@host")  # un worker vivo
    conn.close()

    async def scenario(app, pilot):
        table = app.query_one("#tasks")
        order = [table.coordinate_to_cell_key((i, 0)).row_key.value
                 for i in range(table.row_count)]
        assert order == ["3", "2", "1", "4"]  # detenida → trabajando → borrador → integrada
        assert app.selected == 3  # la que te necesita, seleccionada al abrir
        status = str(app.query_one("#status").render())
        assert "worker vivo" in status and "1 te necesita" in status and "4 tareas" in status

    drive(env, scenario)


def test_right_panel_by_key_keeps_the_selection(env):
    seed_states(env)

    async def scenario(app, pilot):
        assert app.tab == "timeline"
        await pilot.press("e")
        await pilot.pause(0.2)
        assert app.tab == "evidence" and app.selected == 3
        await pilot.press("d")
        await pilot.pause(0.2)
        assert app.tab == "changes"
        await pilot.press("d")  # la misma tecla vuelve a «Qué ha pasado»
        await pilot.pause(0.2)
        assert app.tab == "timeline"
        await pilot.press("g")
        await pilot.pause(0.2)
        assert app.tab == "agent"

    drive(env, scenario)


def test_evidence_and_changes_tabs_show_the_run(env):
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")  # rutina quick: build + ship → espera aprobación

    async def scenario(app, pilot):
        await pilot.press("e")
        for _ in range(40):  # la evidencia se prepara en un hilo
            await pilot.pause(0.1)
            text = str(app.query_one("#evidence-body").render())
            if "Pruebas" in text or "pruebas" in text:
                break
        assert "pruebas" in text.lower() and "passed" in text  # informe + salida de pytest
        await pilot.press("d")
        for _ in range(40):
            await pilot.pause(0.1)
            files = str(app.query_one("#changes-files").render())
            if "calc.py" in files:
                break
        assert "calc.py" in files and "+" in files
        assert "+    return a + b" in app.query_one("#changes-patch").content.code

    drive(env, scenario)


def test_agent_tab_follows_the_live_transcript(env):
    seed_states(env)
    conn = env.conn
    run_id = conn.execute("SELECT id FROM run WHERE status = 'RUNNING'").fetchone()[0]
    att = new_id()
    conn.execute("INSERT INTO attempt (id, run_id, stage, attempt_no, profile, agent, status,"
                 " started_at) VALUES (?, ?, 'build', 1, 'builder', 'claude-code', 'running', ?)",
                 (att, run_id, now()))
    conn.close()
    log = env.root / ".umbra" / "artifacts" / f"{att}-build.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)

    def say(*events):
        with log.open("a", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

    say({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": "C:/x/calc.py"}}]}})

    async def scenario(app, pilot):
        table = app.query_one("#tasks")
        table.move_cursor(row=table.get_row_index("2"))  # la que trabaja
        await pilot.pause(0.3)
        await pilot.press("g")
        await pilot.pause(0.6)
        lines = [line.text for line in app.query_one("#agent").lines]
        assert "Lee calc.py" in lines
        say({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/x/calc.py"}},
            {"type": "text", "text": "Arreglo la suma."}]}})
        for _ in range(20):  # sin cambios en la base, el registro se sigue por tamaño
            await pilot.pause(0.1)
            lines = [line.text for line in app.query_one("#agent").lines]
            if "Edita calc.py" in lines:
                break
        assert "Edita calc.py" in lines and "💬 Arreglo la suma." in lines

    drive(env, scenario)


def test_narrow_terminal_stacks_the_panels(env):
    seed_states(env)

    async def scenario(app, pilot):
        assert app.screen.has_class("-narrow")
        assert app.query_one("#middle").styles.layout.name == "vertical"

    drive(env, scenario, size=(80, 24))


def test_review_detail_shows_the_context_and_opens_the_package(env, monkeypatch):
    from tests.acceptance.test_e2 import run_feature
    from umbra import service
    env.mode("noop", "ok", "noop")
    env.umbra("task", "add", "Sumar correctamente", "-d", "add de calc.py debe sumar",
              "-a", "add(2, 3) == 5")
    assert run_feature(env) == "WAITING_APPROVAL"
    opened = []
    real_popen = service.subprocess.Popen

    def fake_popen(args, **kw):  # solo el editor es falso: git sigue siendo real
        if args and args[0] == "mi-editor":
            opened.append(args)
            return None
        return real_popen(args, **kw)

    monkeypatch.setattr(service, "editor_command", lambda config: ["mi-editor"])
    monkeypatch.setattr(service.subprocess, "Popen", fake_popen)

    async def scenario(app, pilot):
        import io

        from rich.console import Console
        console = Console(file=io.StringIO(), width=120, color_system=None)
        console.print(app.query_one("#situation-body").content)
        text = console.file.getvalue()
        assert "Contexto que recibió" in text and "ver paquete" in text
        assert app.check_action("context", ()) is True
        await pilot.press("k")
        for _ in range(30):
            await pilot.pause(0.1)
            if opened:
                break
        assert opened and opened[0][-1].endswith(".md")

    drive(env, scenario, size=(160, 60))
    result = service.open_context(service.load(env.root), 1)
    assert result["path"].endswith(".md") and result["editor"] == "mi-editor"


def test_agent_story_reads_claude_and_codex():
    claude = "\n".join(json.dumps(e) for e in [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q tests"}},
            {"type": "tool_use", "name": "Grep", "input": {"pattern": "def add"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True}]}},
        {"type": "result", "total_cost_usd": 0.42}])
    assert agent_story.lines(claude) == ["Ejecuta `pytest -q tests`", "Busca «def add»",
                                         "  ↳ falló", "Terminó ($0.42)."]
    codex = "\n".join(json.dumps(e) for e in [
        {"type": "thread.started", "thread_id": "t"},
        {"type": "item.completed", "item": {"type": "command_execution", "command": "ls"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Hola"}},
        {"type": "turn.completed"}])
    assert agent_story.lines(codex) == ["Codex empieza.", "Ejecuta `ls`", "💬 Hola", "Terminó."]
    assert agent_story.lines("no es json\n{\"type\": \"raro\"}") == []


def test_watch_does_not_count_lessons_without_lessons_db(env, monkeypatch):
    """Sin lessons.db no hay nada que decidir: el conteo de la cabecera de watch no corre git
    ni crea la base (antes frenaba la primera carga de watch con la máquina cargada)."""
    from umbra import service
    from umbra.management import lessons
    from umbra.unified import config as cfg

    def no_git(roots):
        raise AssertionError("no debe calcular la clave del proyecto")

    monkeypatch.setattr(lessons, "project_key", no_git)
    assert not (cfg.umbra_home() / "lessons.db").exists()
    assert service.lesson_pending(service.load(env.root)) == 0
    assert not (cfg.umbra_home() / "lessons.db").exists()
