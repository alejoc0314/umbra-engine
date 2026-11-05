import asyncio
import json
from decimal import Decimal

import pytest
from textual.screen import Screen

from umbra import service
from umbra.cli import spec_screen
from umbra.cli.watch import AskText, Confirm, WatchApp
from umbra.unified.store import new_id, now

from .test_spec_tasks import SPEC


@pytest.fixture
def progress(env):
    """3 historias, una hecha; costo: conversación 0.1 + intento 0.2 (en float daría 0.3000…4)."""
    d = env.root / "specs" / "001-demo"
    d.mkdir(parents=True)
    (d / "spec.md").write_text(SPEC, encoding="utf-8")
    env.umbra("spec", "tasks", "specs/001-demo")
    env.umbra("task", "accept", "1")
    conn = env.conn
    ts = now()
    conv = new_id()
    with conn:
        conn.execute("INSERT INTO conversation (id, idea, phase, origin, spec_dir, created_at,"
                     " updated_at) VALUES (?, 'idea', 'plan', 'spec', 'specs/001-demo', ?, ?)",
                     (conv, ts, ts))
        conn.execute("UPDATE task SET status = 'done' WHERE number = 1")
        task_id = conn.execute("SELECT id FROM task WHERE number = 1").fetchone()["id"]
        run_id, att = new_id(), new_id()
        conn.execute("INSERT INTO run (id, task_id, routine, status, stage, created_at,"
                     " updated_at, idempotency_key) VALUES (?, ?, 'quick', 'SUCCEEDED', 'build',"
                     " ?, ?, ?)", (run_id, task_id, ts, ts, new_id()))
        conn.execute("INSERT INTO attempt (id, run_id, stage, attempt_no, status, started_at)"
                     " VALUES (?, ?, 'build', 1, 'ok', ?)", (att, run_id, ts))
        conn.execute("INSERT INTO usage (id, agent, cost, invocation_id, conversation_id)"
                     " VALUES (?, 'claude', '0.1', ?, ?)", (new_id(), new_id(), conv))
        conn.execute("INSERT INTO usage (id, attempt_id, agent, cost, invocation_id)"
                     " VALUES (?, ?, 'claude', '0.2', ?)", (new_id(), att, new_id()))
    return d


def test_avance_costo_exacto_en_decimal(env, progress):
    [p] = service.spec_progress(service.load())
    assert (p["spec_dir"], p["phase"], p["stories_done"], p["stories_total"]) == (
        "specs/001-demo", "plan", 1, 3)
    assert p["cost"] == "0.3" and Decimal(p["cost"]) == Decimal("0.3")


def test_spec_list_y_status_muestran_el_avance(env, progress):
    out = env.umbra("spec", "list").output
    assert "1 de 3" in out and "$0.30" in out
    out = env.umbra("status").output
    assert "1 de 3" in out and "$0.30" in out


def test_json_incluye_avance_por_spec(env, progress):
    for args in (("spec", "list", "--json"), ("status", "--json")):
        data = json.loads(env.umbra(*args).output)
        specs = data if isinstance(data, list) else data["specs"]
        assert specs[0]["stories_done"] == 1 and specs[0]["stories_total"] == 3
        assert specs[0]["cost"] == "0.3"


def test_spec_list_vacio(env):
    assert "No hay specs" in env.umbra("spec", "list").output
    assert json.loads(env.umbra("spec", "list", "--json").output) == []


def test_explain_muestra_origen_y_aviso_de_desalineada(env, progress):
    out = env.umbra("explain", "2").output
    assert "Viene de la historia 2 de specs/001-demo (FR-002)" in out
    assert "cambió en spec.md" not in out
    spec = progress / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("Texto dos.", "Texto dos, nuevo."),
                    encoding="utf-8")
    assert "cambió en spec.md" in env.umbra("explain", "2").output
    [p] = service.spec_progress(service.load())
    assert [m["number"] for m in p["misaligned"]] == [2]


def _drive(env, scenario):
    async def main():
        app = WatchApp(env.root / ".umbra", interval=0.2)
        async with app.run_test() as pilot:
            await pilot.pause(0.4)
            await scenario(app, pilot)
            await pilot.press("q")

    asyncio.run(main())


class FakeSpecApp(Screen):
    """Pantalla de spec falsa: anota con qué la abrió watch y vuelve enseguida."""

    calls = []

    def __init__(self, ctx, idea, **kw):
        super().__init__()
        self.args = (idea, kw)

    def on_mount(self):
        FakeSpecApp.calls.append(self.args)
        self.dismiss(None)


def _fake_spec(env):
    FakeSpecApp.calls = []
    env.monkeypatch.setattr(spec_screen, "SpecScreen", FakeSpecApp)
    env.monkeypatch.setattr(service, "preflight", lambda ctx, confirm=None: None)


def test_watch_muestra_avance_por_spec(env, progress):
    async def scenario(app, pilot):
        await pilot.pause(0.5)
        assert "1 de 3" in str(app.query_one("#specs").render())

    _drive(env, scenario)


def test_tecla_s_pide_la_idea_y_abre_con_origen_watch(env):
    _fake_spec(env)

    async def scenario(app, pilot):
        await pilot.press("s")
        await pilot.pause(0.2)
        assert isinstance(app.screen, AskText)
        await pilot.press(*"hola", "enter")
        await pilot.pause(0.4)

    _drive(env, scenario)
    [(idea, kw)] = FakeSpecApp.calls
    assert idea == "hola" and kw["origin"] == "watch" and not kw["conv_id"]


def test_tecla_s_ofrece_retomar_la_conversacion_abierta(env):
    _fake_spec(env)
    conv = service.spec_new(service.load(), "mi idea")

    async def scenario(app, pilot):
        await pilot.press("s")
        await pilot.pause(0.2)
        assert isinstance(app.screen, Confirm)
        await pilot.press("y")
        await pilot.pause(0.4)

    _drive(env, scenario)
    [(idea, kw)] = FakeSpecApp.calls
    assert idea == "mi idea" and kw["conv_id"] == conv and kw["origin"] == "watch"


def test_tecla_s_abre_la_spec_app_real_sin_romper_el_bucle(env):
    """La pantalla de spec real se apila sobre watch (mismo tema, sin suspender) y vuelve."""
    from .test_spec_conversation import install_flow

    exe = install_flow(env)

    class QuickSpecScreen(spec_screen.SpecScreen):
        def __init__(self, ctx, idea, **kw):
            super().__init__(ctx, idea, exe=exe, **kw)

        def on_mount(self):
            super().on_mount()
            QuickSpecScreen.ran = True
            self.set_timer(1.0, self._close)

    QuickSpecScreen.ran = False
    env.monkeypatch.setattr(spec_screen, "SpecScreen", QuickSpecScreen)
    env.monkeypatch.setattr(service, "preflight", lambda ctx, confirm=None: None)

    async def scenario(app, pilot):
        await pilot.press("s")
        await pilot.pause(0.2)
        await pilot.press(*"hola", "enter")
        for _ in range(30):  # apilada sobre watch (puede tener una pregunta encima)
            await pilot.pause(0.1)
            if any(isinstance(s, QuickSpecScreen) for s in app.screen_stack):
                break
        assert any(isinstance(s, QuickSpecScreen) for s in app.screen_stack)
        assert app.check_action("quit", ()) is False  # las teclas de watch no actúan debajo
        await pilot.pause(2)
        assert QuickSpecScreen.ran
        assert len(app.screen_stack) == 1  # volvió a la vista principal
        assert not app._exception

    _drive(env, scenario)
    assert env.conn.execute("SELECT origin FROM conversation").fetchone()["origin"] == "watch"
