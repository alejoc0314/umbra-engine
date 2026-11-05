"""Escalada automática de modelo y árbitro (spec 016)."""

import json


def task(env):
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")


def feature(env):
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace('default_routine = "quick"',
                                           'default_routine = "feature"'))


def test_build_escalates_to_a_stronger_profile_when_cycles_run_out(env):
    env.mode("broken", "broken", "broken", "ok")  # el constructor normal agota sus 3 intentos
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"  # sin ningún retry a mano
    profiles = [r[0] for r in env.conn.execute(
        "SELECT profile FROM attempt WHERE stage = 'build' ORDER BY started_at")]
    assert profiles == ["builder"] * 3 + ["builder-strong"]
    strong = env.claude_calls()[-1]["args"]
    assert strong[strong.index("--model") + 1] == "claude-fable-5-1"
    assert strong[strong.index("--effort") + 1] == "xhigh"
    event = json.loads(env.conn.execute("SELECT payload FROM event WHERE type = 'stage.escalated'"
                                        ).fetchone()[0])
    assert event["profile"] == "builder-strong" and event["reason"] == "tests_failing"
    assert "perfil más fuerte" in env.umbra("log", "1").output


def test_after_escalation_the_task_still_blocks_if_nothing_works(env):
    env.mode("broken")
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    statuses = [r[0] for r in env.conn.execute(
        "SELECT status FROM attempt WHERE stage = 'build' ORDER BY started_at")]
    assert statuses == ["tests_failed"] * 6  # 3 con cada perfil
    exp = json.loads(env.umbra("explain", "1", "--json").output)
    assert exp["code"] == "tests_failing"


def test_arbiter_decides_when_builder_and_reviewer_disagree(env):
    feature(env)
    env.codex_mode("high:falta validar entradas")  # el revisor insiste en cada ronda
    # plan, build, (review) build, (review) build, (review) árbitro, verify
    env.mode("noop", "ok", "ok", "ok", "noop", "noop")
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    stages = [s for s, _ in env.attempts()]
    assert stages.count("review") == 3 and "arbiter" in stages
    assert stages.index("arbiter") > stages.index("review")
    arb = env.claude_calls()[-2]  # el árbitro: solo lectura y con los hallazgos en el sobre
    assert "falta validar entradas" in arb["prompt"]
    assert "Edit" not in arb["args"][arb["args"].index("--allowedTools") + 1]
    out = env.umbra("log", "1").output
    assert "arbitra" in out and "descartó todos" in out


def test_findings_escalate_the_builder_when_there_is_no_arbiter(env):
    feature(env)
    (env.root / ".umbra" / "routines").mkdir(exist_ok=True)
    (env.root / ".umbra" / "routines" / "feature.yaml").write_text(
        "name: feature\nstages:\n  - name: build\n    profile: builder-tdd\n"
        "    max_fix_cycles: 0\n    escalation: [builder-strong]\n"
        "  - name: review\n    profile: reviewer-strict\n    max_fix_cycles: 0\n"
        "  - name: ship\n", encoding="utf-8")
    env.codex_mode("high:falta validar entradas", "clean")  # el fuerte convence al revisor
    env.mode("ok")
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    profiles = [r[0] for r in env.conn.execute(
        "SELECT profile FROM attempt WHERE stage = 'build' ORDER BY started_at")]
    assert profiles == ["builder-tdd", "builder-strong"]
    event = json.loads(env.conn.execute("SELECT payload FROM event WHERE type = 'stage.escalated'"
                                        ).fetchone()[0])
    assert event["reason"] == "findings"
