import asyncio
import json
import sys
from pathlib import Path

from textual.widgets import DataTable, RichLog

from umbra.actions.commands import isolated
from umbra.actions.secrets import scan_diff
from umbra.cli.watch import WatchApp


def task(env):
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")


def test_secret_in_diff_blocks_without_pr(env):  # SC-002
    env.mode("noop", "secret", "noop")
    task(env)
    env.umbra("run", "1", "-r", "feature", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    finding = env.conn.execute("SELECT severity, rule, file FROM finding").fetchone()
    assert tuple(finding) == ("critical", "aws-access-key", "config.py")
    assert env.prs() == []


def test_failing_sast_command_sends_back_to_build(env):
    cfg = env.root / ".umbra" / "project.toml"
    sast = (f"'\"{sys.executable}\" -c \"import sys,pathlib; "
            "sys.exit(1 if chr(66)+chr(65)+chr(68) in pathlib.Path(chr(99)+chr(97)+chr(108)+"
            "chr(99)+chr(46)+chr(112)+chr(121)).read_text() else 0)\"'")
    cfg.write_text(cfg.read_text().replace("[policy]\n", f"sast = {{ run = {sast} }}\n\n"
                                           '[scan]\ncommands = ["sast"]\n\n[policy]\n'))
    env.mode("noop", "bad", "noop", "ok", "noop")
    task(env)
    env.umbra("run", "1", "-r", "feature", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    stages = [s for s, _ in env.attempts()]
    assert stages == ["plan", "build", "review", "verify", "scan", "build", "review", "verify",
                      "scan"]
    rule = env.conn.execute("SELECT rule FROM finding WHERE severity = 'high'").fetchone()[0]
    assert rule == "sast:sast"


def test_repo_agent_config_requires_trust(env):
    (env.root / ".mcp.json").write_text("{}")
    task(env)
    result = env.umbra("run", "1", "--foreground", ok=False)
    assert result.exit_code == 5 and ".mcp.json" in result.output
    env.umbra("run", "1", "--foreground", "--trust-repo-config")
    assert env.run()["status"] == "WAITING_APPROVAL"


def test_metrics_after_a_delivery(env):
    task(env)
    env.umbra("run", "1", "--foreground")
    env.umbra("approve", "1", input="y\n")
    data = json.loads(env.umbra("metrics", "--json").output)
    s = data["summary"]
    assert s["merged"] == 1 and s["first_pass_rate"] == 1.0
    assert s["cost_per_delivery"] == "0.0500" and data["runs"][0]["time_to_pr_s"] >= 0


def test_watch_shows_tasks_attempts_and_events(env):
    task(env)
    env.umbra("run", "1", "--foreground")

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.2)
        async with app.run_test() as pilot:
            await pilot.pause(0.3)
            tasks = app.query_one("#tasks", DataTable)
            attempts = app.query_one("#attempts", DataTable)
            log = app.query_one("#log", RichLog)
            assert tasks.row_count == 1 and attempts.row_count == 1
            assert len(log.lines) > 3
            await pilot.press("q")

    asyncio.run(scenario())


def test_watch_does_not_refresh_in_a_loop(env, monkeypatch):
    """Regresión: redibujar movía el cursor → RowHighlighted → refresh → bucle infinito."""
    task(env)
    env.umbra("task", "add", "Otra", "-a", "x")
    env.umbra("run", "1", "--foreground")
    calls = {"n": 0}
    original = WatchApp.refresh_data

    def counting(self, *args, **kwargs):
        calls["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(WatchApp, "refresh_data", counting)

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.5)
        async with app.run_test() as pilot:
            await pilot.pause(1.2)
            assert calls["n"] <= 5  # inicial + ~2 del intervalo, no cientos
            assert app.selected == 1
            await pilot.press("down")  # el usuario elige la tarea 2
            await pilot.pause(0.3)
            assert app.selected == 2
            assert app.query_one("#attempts", DataTable).row_count == 0  # la 2 no ha corrido
            assert calls["n"] <= 7
            await pilot.press("q")

    asyncio.run(scenario())


def test_secret_scanner_patterns():
    diff = ("+++ b/a.py\n@@ -0,0 +1,3 @@\n+key = 'ghp_" + "a" * 36 + "'\n"
            "+-----BEGIN RSA PRIVATE KEY-----\n+ok = 1\n")
    rules = [(f.rule, f.line) for f in scan_diff(diff)]
    assert rules == [("github-token", 1), ("private-key", 2)]
    assert scan_diff("+++ b/a.py\n@@ -1 +1 @@\n-AKIAABCDEFGHIJKLMNOP\n+x = 1\n") == []


def test_docker_isolation_command(tmp_path):
    assert isolated("pytest -q", tmp_path, {}) == "pytest -q"
    cmd = isolated("pytest -q", tmp_path, {"isolation": "docker", "image": "python:3.13"})
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert cmd[cmd.index("--network") + 1] == "none" and "--pids-limit" in cmd
    assert cmd[-4:] == ["python:3.13", "sh", "-c", "pytest -q"]
    assert f"{Path(tmp_path).resolve()}:/work" in cmd
