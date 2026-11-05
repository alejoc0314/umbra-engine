import asyncio
import json
import sys
import time
from pathlib import Path

from textual.widgets import Input, OptionList

from umbra import service
from umbra.cli.spec_screen import SpecApp
from umbra.cli.watch import AskText, Confirm, PickOne

FAKES = Path(__file__).resolve().parent.parent / "fakes"
SPEC = """# Demo

### User Story 1 - Uno (Priority: P1)

Texto uno. FR-001

**Acceptance Scenarios**:

1. **Given** a, **When** b, **Then** c

### User Story 2 - Dos (Priority: P2)

Texto dos.

**Acceptance Scenarios**:

1. **Given** d, **When** e, **Then** f
"""
EFFECTS = {
    "1": {"specs/001-x/spec.md": SPEC,
          ".specify/feature.json": json.dumps({"feature_directory": "specs/001-x"})},
    "5": {"specs/001-x/tasks.md": "- [ ] T001 [US1] Editar `calc.py`\n- [ ] T002 [US2] Algo\n"},
}


def install_flow(env, stream="full_flow.jsonl") -> str:
    """`claude` falso de varias fases (un proceso por fase, retoma donde quedó el anterior)."""
    bin_dir = env.root.parent / "bin"
    script = FAKES / "claude_flow.py"
    if sys.platform == "win32":
        shim = bin_dir / "claude.cmd"
        shim.write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        shim = bin_dir / "claude"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        shim.chmod(0o755)
    env.monkeypatch.setenv("FAKE_STREAM", str(FAKES / "streams" / stream))
    env.monkeypatch.setenv("FAKE_TURN_FILES", json.dumps(EFFECTS))
    return str(shim)


async def until(pilot, cond, what="condición"):
    end = time.monotonic() + 20
    while not cond():
        assert time.monotonic() < end, f"no se cumplió: {what}"
        await pilot.pause(0.05)


def phase(env):
    return env.conn.execute("SELECT phase FROM conversation").fetchone()["phase"]


async def review(pilot, app, env, which):
    await until(pilot, lambda: phase(env) == which and isinstance(app.screen, PickOne), which)


async def pick(pilot, app, index):
    await until(pilot, lambda: app.screen.query(OptionList), "lista de opciones")
    app.screen.query_one(OptionList).highlighted = index
    await pilot.press("enter")


def run(env, scenario, stream="full_flow.jsonl"):
    exe = install_flow(env, stream)

    async def go():
        app = SpecApp(service.load(), "una idea", exe=exe)
        async with app.run_test() as pilot:
            await scenario(pilot, app)
        return app

    return asyncio.run(go())


def test_recorrido_completo_hasta_tareas_en_borrador(env):
    async def scenario(pilot, app):
        await until(pilot, lambda: isinstance(app.screen, PickOne), "pregunta")
        await until(pilot, lambda: app.screen.query(OptionList), "lista de opciones")
        options = app.screen.query_one(OptionList)
        assert str(options.get_option_at_index(0).prompt) == "1000 (recomendada)"
        assert options.option_count == 3  # 2 opciones + «Otra respuesta…»
        await pick(pilot, app, 0)
        await review(pilot, app, env, "spec_review")
        await pick(pilot, app, 0)
        await review(pilot, app, env, "plan_review")
        await pick(pilot, app, 0)
        await until(pilot, lambda: phase(env) == "done", "fase done")
        text = "\n".join(app.lines)
        assert "[1, 2]" in text and "umbra task accept" in text

    run(env, scenario)
    assert [r["spec_dir"] for r in env.conn.execute("SELECT spec_dir FROM task")] \
        == ["specs/001-x"] * 2
    events = [(r["type"], r["origin"]) for r in env.conn.execute(
        "SELECT type, origin FROM event WHERE type LIKE 'spec.%' ORDER BY id")]
    assert events == [("spec.started", "spec"), ("spec.approved", "spec"),
                      ("spec.approved", "spec"), ("spec.tasks", "spec")]
    calls = env.claude_calls()
    assert [c["message"] for c in calls][-3:] == ["1000", "/speckit-plan", "/speckit-tasks"]
    names = [Path(c["args"][c["args"].index("--settings") + 1]).name for c in calls]
    assert names == ["settings-specify.json", "settings-clarify.json", "settings-clarify.json",
                     "settings-plan.json", "settings-tasks.json"]
    assert "--resume" not in calls[0]["args"]
    assert all(c["args"][c["args"].index("--resume") + 1] == "sess-1" for c in calls[1:])


def test_pedir_cambios_vuelve_a_la_fase_anterior_con_el_comentario(env):
    async def scenario(pilot, app):
        await until(pilot, lambda: isinstance(app.screen, PickOne), "pregunta")
        await pick(pilot, app, 0)
        await review(pilot, app, env, "spec_review")
        await pick(pilot, app, 1)
        await until(pilot, lambda: isinstance(app.screen, AskText), "comentario")
        await pilot.press(*"mas usuarios", "enter")
        await until(pilot, lambda: len(env.claude_calls()) == 4, "turno de cambios")
        await review(pilot, app, env, "spec_review")  # el turno termina y vuelve a revisión

    run(env, scenario)
    last = env.claude_calls()[-1]
    assert last["message"] == "Cambios pedidos: mas usuarios"
    assert last["args"][last["args"].index("--settings") + 1].endswith("settings-clarify.json")
    assert ("spec.changes",) in [tuple(r) for r in env.conn.execute(
        "SELECT type FROM event WHERE type = 'spec.changes'")]


def test_descartar_pide_confirmacion_y_no_crea_tareas(env):
    async def scenario(pilot, app):
        await until(pilot, lambda: isinstance(app.screen, PickOne), "pregunta")
        await pick(pilot, app, 0)
        await review(pilot, app, env, "spec_review")
        await pick(pilot, app, 2)
        await until(pilot, lambda: isinstance(app.screen, Confirm), "confirmación")
        await pilot.press("enter")  # por defecto «No»: sigue la revisión
        await review(pilot, app, env, "spec_review")
        await pick(pilot, app, 2)
        await until(pilot, lambda: isinstance(app.screen, Confirm), "confirmación")
        await pilot.press("y")
        await until(pilot, lambda: phase(env) == "discarded", "descartada")

    run(env, scenario)
    assert env.conn.execute("SELECT COUNT(*) FROM task").fetchone()[0] == 0
    assert env.conn.execute(
        "SELECT COUNT(*) FROM event WHERE type = 'spec.discarded'").fetchone()[0] == 1


def test_error_del_asistente_no_cierra_la_pantalla(env):
    async def scenario(pilot, app):
        await until(pilot, lambda: any("Error del asistente" in x for x in app.lines), "error")
        assert app.is_running and not app.query_one("#entry", Input).disabled
        assert "Se cayó el asistente" in "\n".join(app.lines)
        assert phase(env) == "specify"

    run(env, scenario, "error_turn.jsonl")


def test_spec_new_sin_terminal_falla_con_mensaje_claro(env):
    env.monkeypatch.setattr(service, "interactive", lambda: False)
    result = env.umbra("spec", "new", "una idea", ok=False)
    assert result.exit_code == 2 and "terminal interactiva" in result.output
