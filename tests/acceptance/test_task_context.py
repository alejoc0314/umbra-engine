"""Cada tarea arranca con el contexto justo (spec 035, US1): Explorar arma el paquete y los
agentes lo reciben; si Explorar falla, la tarea sigue."""

import json

from tests.acceptance.test_e2 import run_feature
from umbra.management import explore

HEADER = "Contexto de esta tarea"


def context_task(env):
    env.umbra("task", "add", "Sumar correctamente", "-d", "add de calc.py debe sumar",
              "-a", "add(2, 3) == 5")


def events(env, type_):
    return [json.loads(r[0]) for r in env.conn.execute(
        "SELECT payload FROM event WHERE type = ? ORDER BY id", (type_,))]


def test_explore_builds_the_package_and_agents_receive_it(env):
    env.mode("noop", "ok", "noop")
    context_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    ready = events(env, "explore.ready")
    assert len(ready) == 1
    summary = ready[0]
    assert {"path": "calc.py", "repo": "", "why": "nombrado en la tarea"} in summary["files"]
    assert [t["path"] for t in summary["tests"]] == ["tests/test_calc.py"]
    assert summary["history"][0]["subject"] == "init"
    assert summary["chars"] <= summary["max_chars"]
    art = env.conn.execute("SELECT path, checksum, command FROM artifact WHERE kind = 'context'"
                           ).fetchall()
    assert len(art) == 1 and art[0]["command"] == "explore" and art[0]["checksum"]
    plan_call, build_call, _verify = env.claude_calls()
    for prompt in (plan_call["prompt"], build_call["prompt"], env.codex_calls()[0]["prompt"]):
        assert HEADER in prompt and "tests/test_calc.py" in prompt
    assert [s for s, _ in env.attempts()] == ["plan", "build", "review", "verify", "scan"]


def test_explore_failure_does_not_block_the_task(env, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("git se colgó")

    monkeypatch.setattr(explore, "explore", boom)
    env.mode("noop", "ok", "noop")
    context_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    failed = events(env, "explore.failed")
    assert failed and "git se colgó" in failed[0]["reason"]
    assert not events(env, "explore.ready")
    assert HEADER not in env.claude_calls()[1]["prompt"]


def test_review_rejection_proposes_a_lesson_that_is_not_applied(env):
    from umbra.management import lessons

    env.mode("noop", "ok", "ok", "noop")
    env.codex_mode("high:falta validar entradas", "clean")
    context_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    db = lessons.open_db()
    rows = db.execute("SELECT * FROM lesson").fetchall()
    assert [(r["number"], r["status"]) for r in rows] == [(1, "proposed")]
    assert "falta validar entradas" in rows[0]["text"]
    origins = db.execute("SELECT * FROM lesson_origin WHERE number = 1").fetchall()
    assert len(origins) == 1
    o = origins[0]
    assert (o["kind"], o["task"], o["stage"]) == ("review_rejected", 1, "review")
    assert "falta validar entradas" in o["detail"] and o["created_at"][:2] == "20"
    assert events(env, "lessons.proposed")[-1]["proposed"] == 1

    env.umbra("task", "add", "Restar en calc.py", "-d", "sub de calc.py debe restar")
    env.umbra("run", "2", "-r", "feature", "--foreground", ok=False)
    second = events(env, "explore.ready")[-1]
    assert {"path": "calc.py", "repo": "", "why": "nombrado en la tarea"} in second["files"]
    assert second["lessons"] == []
    later = env.claude_calls()[4:]
    assert later and all("Lecciones aprobadas" not in c["prompt"] for c in later)
