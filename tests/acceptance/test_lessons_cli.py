"""La persona decide sobre cada lección desde la CLI (spec 035, US4)."""

import json

from tests.acceptance.test_e2 import run_feature
from tests.acceptance.test_task_context import context_task, events


def lesson_json(env, *args, ok=True):
    result = env.umbra("lesson", *args, "--json", ok=ok)
    return result, (json.loads(result.output) if ok else None)


def proposed_lesson(env):
    env.mode("noop", "ok", "ok", "noop")
    env.codex_mode("high:falta validar entradas", "clean")
    context_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"


def test_list_and_show(env):
    proposed_lesson(env)
    _, items = lesson_json(env, "list")
    assert [(i["id"], i["status"]) for i in items] == [("L1", "proposed")]
    assert items[0]["origins"] == 1 and "falta validar entradas" in items[0]["text"]
    _, shown = lesson_json(env, "show", "1")
    assert shown["origins_detail"][0]["kind"] == "review_rejected"
    assert shown["history"][0]["action"] == "proposed" and shown["applied_in"] == []
    text = env.umbra("lesson", "list").output
    assert "L1" in text and "propuesta" in text


def test_approved_lesson_reaches_the_next_task_and_retired_does_not(env):
    proposed_lesson(env)
    _, out = lesson_json(env, "approve", "L1", "--text", "Valida siempre las entradas")
    assert out["status"] == "approved" and out["text"] == "Valida siempre las entradas"

    env.umbra("task", "add", "Restar en calc.py", "-d", "sub de calc.py debe restar")
    env.umbra("run", "2", "-r", "feature", "--foreground", ok=False)
    used = events(env, "explore.ready")[-1]["lessons"]
    assert [(x["id"], x["text"]) for x in used] == [(1, "Valida siempre las entradas")]
    assert any("Valida siempre las entradas" in c["prompt"] for c in env.claude_calls()[4:])

    _, out = lesson_json(env, "retire", "L1", "--reason", "ya no aplica")
    assert out["status"] == "retired"
    env.umbra("task", "add", "Multiplicar en calc.py", "-d", "mul de calc.py debe multiplicar")
    env.umbra("run", "3", "-r", "feature", "--foreground", ok=False)
    assert events(env, "explore.ready")[-1]["lessons"] == []
    _, shown = lesson_json(env, "show", "L1")
    assert [a["task"] for a in shown["applied_in"]] == [2]
    approved = [h for h in shown["history"] if h["action"] == "approved"][0]
    assert "falta validar entradas" in approved["before"] and approved["channel"] == "cli"
    assert "L1" not in [i["id"] for i in lesson_json(env, "list")[1]]
    assert "L1" in [i["id"] for i in lesson_json(env, "list", "--all")[1]]
    assert [i["id"] for i in lesson_json(env, "list", "--status", "retired")[1]] == ["L1"]


def test_invalid_decisions_fail_with_a_clear_message(env):
    proposed_lesson(env)
    result, _ = lesson_json(env, "retire", "L1", ok=False)
    assert result.exit_code != 0 and "propuesta" in result.output
    result, _ = lesson_json(env, "approve", "L99", ok=False)
    assert result.exit_code != 0 and "L99 no existe" in result.output
    result, _ = lesson_json(env, "show", "siete", ok=False)
    assert result.exit_code != 0
    _, out = lesson_json(env, "discard", "1", "--reason", "no aplica")
    assert out["status"] == "discarded"
    result, _ = lesson_json(env, "approve", "1", ok=False)
    assert result.exit_code != 0 and "descartada" in result.output


def test_watch_lessons_panel_decides(env):
    from textual.widgets import Input, Static

    from tests.acceptance.test_watch_actions import drive, modal
    from umbra.cli.modals import AskText, LessonsScreen
    from umbra.management import lessons

    proposed_lesson(env)
    env.umbra("task", "add", "Otra", "-d", "otra cosa")

    async def scenario(app, pilot, notes):
        assert "1 lección por decidir" in str(app.query_one("#status", Static).render())
        await pilot.press("l")
        await modal(app, pilot, LessonsScreen)
        screen = app.screen
        assert screen.current()["id"] == "L1"
        await pilot.press("x")  # retirar una propuesta no aplica
        assert any("no aplica" in n for n in notes)
        await pilot.press("a")
        await modal(app, pilot, AskText)
        app.screen.query_one(Input).value = "Valida las entradas en watch"
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert any("L1 aprobada" in n for n in notes)
        assert screen.current()["status"] == "approved"
        await pilot.press("escape")

    drive(env, scenario)
    db = lessons.open_db()
    row = db.execute("SELECT text, status FROM lesson WHERE number = 1").fetchone()
    assert tuple(row) == ("Valida las entradas en watch", "approved")
    channel = db.execute("SELECT channel FROM lesson_history WHERE action = 'approved'"
                         ).fetchone()[0]
    assert channel == "watch"


def test_the_chat_can_only_look_at_lessons():
    from umbra.chat import launcher
    allowed = [c for c in launcher.QUERY + launcher.STATEFUL if c.startswith("lesson")]
    assert allowed == ["lesson list", "lesson show"]


def test_harvest_twice_does_not_duplicate(env):
    proposed_lesson(env)
    assert lesson_json(env, "harvest")[1] == {"proposed": 0}
    assert lesson_json(env, "harvest")[1] == {"proposed": 0}
    assert len(lesson_json(env, "list", "--all")[1]) == 1


def test_watch_header_does_not_wait_for_lessons(env, monkeypatch):
    """Contar las lecciones (git y lessons.db) no frena la primera carga de watch: se cuenta
    aparte y la cabecera se actualiza en cuanto llega el número."""
    import threading
    import time

    from umbra import service
    from umbra.cli.watch_data import Loader

    env.conn.close()
    release = threading.Event()

    def slow(ctx):
        release.wait(5)
        return 3

    monkeypatch.setattr(service, "lesson_pending", slow)
    loader = Loader(env.root / ".umbra")
    try:
        start = time.monotonic()
        snap = loader.load(None, False, None, 0)
        assert time.monotonic() - start < 2
        assert snap.header.lessons == 0
        release.set()
        for _ in range(100):
            time.sleep(0.05)
            snap = loader.load(None, False, None, 0) or snap
            if snap.header.lessons == 3:
                break
        assert snap.header.lessons == 3
    finally:
        release.set()
        loader.close()


def test_watch_header_shows_lessons_as_soon_as_counted(env, monkeypatch):
    """La primera carga de watch no espera el conteo de lecciones (no retrasa el panel de
    decisión) y la cabecera lo muestra en cuanto llega, sin esperar al próximo refresco."""
    import asyncio
    import threading

    from textual.widgets import Static

    from umbra import service
    from umbra.cli.watch import WatchApp

    release = threading.Event()

    def slow(ctx):
        release.wait(10)
        return 3

    monkeypatch.setattr(service, "lesson_pending", slow)

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=60)  # sin refrescos durante la prueba
        async with app.run_test() as pilot:
            for _ in range(100):
                await pilot.pause(0.05)
                if app._header_text is not None:
                    break
            assert app._header_text is not None and "por decidir" not in app._header_text
            release.set()
            for _ in range(100):
                await pilot.pause(0.05)
                if "3 lecciones por decidir" in str(app.query_one("#status", Static).render()):
                    break
            assert "3 lecciones por decidir" in str(app.query_one("#status", Static).render())
            await pilot.press("q")

    try:
        asyncio.run(scenario())
    finally:
        release.set()


# ---------- US5: las lecciones son de la persona, no del repo (T041) ----------
def _git_status(root):
    from tests.conftest import git
    return git(root, "status", "--porcelain").stdout


def _open_umbra_in(env, root):
    from umbra.unified import project
    project.init_project(root)
    env.monkeypatch.chdir(root)


def test_lessons_stay_out_of_the_repo_and_follow_its_clones(env, tmp_path):
    from tests.conftest import git

    proposed_lesson(env)
    before = _git_status(env.root)
    lesson_json(env, "approve", "L1")
    assert _git_status(env.root) == before

    clone = tmp_path / "clon"
    git(tmp_path, "clone", "-q", str(env.root), str(clone))
    _open_umbra_in(env, clone)
    _, items = lesson_json(env, "list")
    assert [(i["id"], i["status"]) for i in items] == [("L1", "approved")]

    other = tmp_path / "otro"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    git(other, "config", "user.email", "o@umbra.local")
    git(other, "config", "user.name", "otro")
    (other / "b.txt").write_text("otro proyecto\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "otro")
    _open_umbra_in(env, other)
    assert lesson_json(env, "list", "--all")[1] == []


def test_export_and_import_bring_lessons_to_another_machine(env, tmp_path):
    import os

    proposed_lesson(env)
    lesson_json(env, "approve", "L1", "--text", "Valida siempre las entradas")
    _, shown = lesson_json(env, "show", "L1")

    to_stdout = env.umbra("lesson", "export").output
    assert json.loads(to_stdout)["lessons"][0]["text"] == "Valida siempre las entradas"
    path = tmp_path / "lecciones.json"
    _, out = lesson_json(env, "export", str(path))
    assert out == {"path": str(path), "count": 1}
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == 1

    home = os.environ["UMBRA_HOME"]
    for suffix in ("", "-wal", "-shm"):  # otra máquina: sin lessons.db
        f = os.path.join(home, "lessons.db" + suffix)
        if os.path.exists(f):
            os.remove(f)
    assert lesson_json(env, "list", "--all")[1] == []

    _, out = lesson_json(env, "import", str(path))
    assert out == {"created": 1, "merged": 0, "origins_added": 1}
    _, again = lesson_json(env, "show", "L1")
    for k in ("status", "text", "zone", "updated_at", "origins_detail", "history"):
        assert again[k] == shown[k]
    _, out = lesson_json(env, "import", str(path))
    assert out == {"created": 0, "merged": 1, "origins_added": 0}
    assert len(lesson_json(env, "list", "--all")[1]) == 1
    text = env.umbra("lesson", "import", str(path)).output
    assert "0 nuevas" in text and "1 ya existían" in text

    bad = tmp_path / "malo.json"
    bad.write_text("{no es json", encoding="utf-8")
    result, _ = lesson_json(env, "import", str(bad), ok=False)
    assert result.exit_code != 0 and "JSON" in result.output
