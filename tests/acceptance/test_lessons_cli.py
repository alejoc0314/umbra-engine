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
