"""Takeover (spec 017): la persona arregla a mano en su editor y umbra retoma."""

import sys
import time
from pathlib import Path

from tests.acceptance.test_watch_actions import drive, settle, sync_worker
from tests.conftest import git
from umbra.cli.watch import AskText


def fake_editor(env) -> Path:
    """Un «editor» que solo anota la ruta que le pasan."""
    env.state.mkdir(exist_ok=True)
    log = env.state / "editor.txt"
    script = env.state / "editor.py"
    script.write_text("import sys, pathlib\n"
                      f"pathlib.Path({str(log)!r}).write_text(sys.argv[1])\n")
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace(
        'command = "code"', f"command = '\"{sys.executable}\" \"{script}\"'"))
    return log


def blocked_task(env):
    env.mode("broken")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"


def fix_by_hand(env):
    wt = Path(env.run()["worktree"])
    (wt / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    return wt


def test_open_launches_the_editor_on_the_worktree(env):
    log = fake_editor(env)
    blocked_task(env)
    out = env.umbra("open", "1").output
    assert "umbra done 1" in out
    for _ in range(200):  # el editor arranca en segundo plano (lento con la suite en paralelo)
        if log.exists():
            break
        time.sleep(0.1)
    assert Path(log.read_text()) == Path(env.run()["worktree"])
    assert "Lo abriste en tu editor" in env.umbra("log", "1").output


def test_done_records_a_human_attempt_and_resumes(env):
    blocked_task(env)
    calls_before = len(env.claude_calls())
    fix_by_hand(env)
    out = env.umbra("done", "1", "-m", "faltaba sumar", "--foreground").output
    assert "sigue desde ship" in out
    assert env.run()["status"] == "WAITING_APPROVAL"
    assert len(env.claude_calls()) == calls_before  # ningún constructor volvió a correr
    human = env.conn.execute("SELECT stage, status, profile FROM attempt WHERE agent = 'human'"
                             ).fetchall()
    assert [tuple(r) for r in human] == [("build", "done", "takeover")]
    tests = env.conn.execute("SELECT exit_code, tested_sha FROM artifact WHERE attempt_id ="
                             " (SELECT id FROM attempt WHERE agent = 'human')").fetchone()
    assert tests["exit_code"] == 0 and tests["tested_sha"] == env.run()["head_sha"]
    assert git(Path(env.run()["worktree"]), "log", "-1", "--format=%s").stdout.strip() \
        == "humano: faltaba sumar"
    log = env.umbra("log", "1").output
    before, after = log.split("Tu arreglo: faltaba sumar")
    assert "Claude Code empieza" in before and "Claude Code empieza" not in after
    assert "takeover" in env.umbra("evidence", "1", "--raw").output


def test_done_with_red_tests_keeps_the_task_stopped(env):
    blocked_task(env)
    wt = Path(env.run()["worktree"])
    (wt / "calc.py").write_text("def add(a, b):\n    return a * b\n")
    result = env.umbra("done", "1", "-m", "intento", ok=False)
    assert result.exit_code != 0 and "en rojo" in result.output
    assert env.run()["status"] == "BLOCKED"
    assert env.conn.execute("SELECT status FROM attempt WHERE agent = 'human'").fetchone()[0] \
        == "tests_failed"


def test_done_without_changes_does_nothing(env):
    blocked_task(env)
    result = env.umbra("done", "1", "-m", "nada", ok=False)
    assert result.exit_code != 0 and "no hay cambios" in result.output
    assert env.conn.execute("SELECT COUNT(*) FROM attempt WHERE agent = 'human'").fetchone()[0] \
        == 0


def test_o_opens_and_then_resumes_from_watch(env):
    log = fake_editor(env)
    blocked_task(env)
    sync_worker(env)

    async def scenario(app, pilot, notes):
        assert app._kind == "blocked" and not app._decision.get("takeover")
        await pilot.press("o")
        await settle(app, pilot)
        for _ in range(100):  # el editor falso arranca en segundo plano
            if log.exists():
                break
            await pilot.pause(0.1)
        assert log.exists() and app._decision.get("takeover")
        fix_by_hand(env)
        await pilot.press("o")
        await pilot.pause(0.2)
        assert isinstance(app.screen, AskText)
        for ch in "arreglo":
            await pilot.press(ch)
        await pilot.press("enter")
        await settle(app, pilot)
        assert env.run()["status"] == "WAITING_APPROVAL"
        assert any('umbra done 1 -m "arreglo"' in n for n in notes)

    drive(env, scenario)
