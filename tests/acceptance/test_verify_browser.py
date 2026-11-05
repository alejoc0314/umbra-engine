"""VERIFY con navegador (spec 020): umbra levanta la app, el verificador la visita y deja
capturas como evidencia."""

import json
import socket
import sys
from pathlib import Path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def with_dev(env) -> str:
    port = free_port()
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace(
        "[commands]\n",
        f"[commands]\ndev = {{ run = '\"{sys.executable}\" -m http.server {port} --bind "
        f"127.0.0.1', background = true, url = \"http://127.0.0.1:{port}\" }}\n").replace(
        'default_routine = "quick"', 'default_routine = "feature"'))
    return f"http://127.0.0.1:{port}"


def port_open(url: str) -> bool:
    host, port = url.rsplit("/", 1)[-1].split(":")
    try:
        with socket.create_connection((host, int(port)), timeout=1):
            return True
    except OSError:
        return False


def test_verify_sees_the_app_in_the_browser_and_keeps_screenshots(env):
    url = with_dev(env)
    env.mode("noop", "ok", "browse")  # plan, build, verify (la revisión la hace el Codex falso)
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL", env.umbra("explain", "1").output
    verify = env.claude_calls()[-1]
    args = verify["args"]
    assert "@playwright/mcp" in args[args.index("--mcp-config") + 1]
    assert "--strict-mcp-config" in args
    assert "mcp__playwright" in args[args.index("--allowedTools") + 1]
    assert url in verify["prompt"]
    shots = [tuple(r) for r in env.conn.execute(
        "SELECT kind, path, tested_sha FROM artifact WHERE kind = 'screenshot'")]
    assert len(shots) == 1 and shots[0][1].endswith("-shots/home.png")
    assert shots[0][2] == env.run()["head_sha"]
    assert Path(shots[0][1]).read_bytes().startswith(b"\x89PNG")
    assert ".umbra/artifacts" in shots[0][1] and "worktrees" not in shots[0][1]
    assert not port_open(url), "el servidor de desarrollo sigue levantado"
    events = [r[0] for r in env.conn.execute("SELECT type FROM event ORDER BY id")]
    assert events.index("dev.started") < events.index("evidence.screenshots") \
        < events.index("dev.stopped")
    started = json.loads(env.conn.execute("SELECT payload FROM event WHERE type = 'dev.started'"
                                          ).fetchone()[0])
    assert started["url"] == url and "http.server" in started["command"]
    log = env.umbra("log", "1").output
    assert "levantada en" in log and "1 captura del navegador" in log
    report = env.umbra("evidence", "1").output
    assert "Visto en el navegador: 1 captura" in report
    assert "captura sobre" in env.umbra("evidence", "1", "--raw").output
    # el servidor de desarrollo no entra en los comandos que el agente puede ejecutar
    build = env.claude_calls()[1]
    assert "http.server" not in build["prompt"]


def test_without_dev_the_verifier_works_as_before(env):
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace('default_routine = "quick"',
                                           'default_routine = "feature"'))
    env.mode("noop", "ok", "noop")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    args = env.claude_calls()[-1]["args"]
    assert "--mcp-config" not in args and "mcp__playwright" not in " ".join(args)
    assert env.conn.execute("SELECT COUNT(*) FROM artifact WHERE kind = 'screenshot'"
                            ).fetchone()[0] == 0


def test_dev_that_never_answers_blocks_with_a_clear_reason(env):
    port = free_port()
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace(
        "[commands]\n",
        f"[commands]\ndev = {{ run = '\"{sys.executable}\" -c \"import time; time.sleep(30)\"', "
        f"background = true, url = \"http://127.0.0.1:{port}\", ready_timeout_s = 2 }}\n"
    ).replace('default_routine = "quick"', 'default_routine = "feature"'))
    env.mode("noop", "ok", "browse")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    blocked = json.loads(env.conn.execute("SELECT payload FROM event WHERE type = 'run.blocked'"
                                          ).fetchone()[0])
    assert blocked["code"] == "dev_not_ready" and "no respondió" in blocked["reason"]
