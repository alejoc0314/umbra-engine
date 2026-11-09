"""Agentes que se quedan sin tiempo: se corta por inactividad, se retoma la misma sesión una vez y,
si la etapa tiene respaldo, entra otro agente (no se detiene la tarea a la primera)."""

import json
from pathlib import Path

DEFAULTS = Path(__file__).parents[2] / "src" / "umbra" / "defaults" / "profiles"


def quick_profile(env, name: str) -> None:
    """El perfil, con un bloque de segundos: los agentes falsos se callan y se cortan rápido."""
    text = (DEFAULTS / f"{name}.toml").read_text(encoding="utf-8")
    text = "\n".join("max_minutes = 0.03" if line.startswith("max_minutes") else line
                     for line in text.splitlines())
    profiles = env.root / ".umbra" / "profiles"
    (profiles / f"{name}.toml").write_text(text + "\n", encoding="utf-8")
    if (md := DEFAULTS / f"{name}.md").is_file():  # sus instrucciones, al lado
        (profiles / md.name).write_text(md.read_text(encoding="utf-8"), encoding="utf-8")


def finished(env, stage: str) -> list[dict]:
    return [json.loads(r[0]) for r in env.conn.execute(
        "SELECT payload FROM event WHERE type = 'attempt.finished' ORDER BY id")
        if json.loads(r[0])["stage"] == stage]


def test_a_stuck_builder_resumes_its_session_and_the_task_goes_on(env):
    quick_profile(env, "builder")
    env.mode("stall")  # anuncia su sesión y se calla; retomado, termina
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL", env.umbra("explain", "1").output
    calls = env.claude_calls()
    assert "--resume" not in calls[0]["args"]
    resumed = calls[1]["args"]
    assert resumed[resumed.index("--resume") + 1] == "sesion-colgada"
    assert "exactamente donde quedaste" in calls[1]["prompt"]  # (el falso lee cp1252)
    builds = finished(env, "build")
    assert len(builds) == 1 and builds[0]["ok"] and builds[0]["resumed"]  # un solo intento


def test_a_stuck_reviewer_is_resumed_and_then_the_backup_reviews(env):
    quick_profile(env, "reviewer-strict")
    env.codex_mode("stall")  # Codex se cuelga, también al retomarlo
    env.mode("noop", "ok", "noop", "noop")  # plan, build, revisión de respaldo, verify
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--routine", "feature", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL", env.umbra("explain", "1").output
    codex = env.codex_calls()
    assert len(codex) == 2 and codex[1]["args"][:3] == ["exec", "resume", "--json"]
    assert "thread-fake" in codex[1]["args"]
    fallback = json.loads(env.conn.execute(
        "SELECT payload FROM event WHERE type = 'stage.fallback'").fetchone()[0])
    assert fallback["failed"] == "reviewer-strict" and fallback["profile"] == "reviewer-claude"
    assert "sin señales de vida (también tras retomar la sesión)" in fallback["error"]


def test_stuck_even_after_resuming_the_task_stops_and_says_why(env):
    quick_profile(env, "builder")
    env.mode("sleep")  # se calla sin anunciar sesión: no hay nada que retomar
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    assert len(env.claude_calls()) == 1
    assert "se quedó atascado" in env.umbra("explain", "1").output
