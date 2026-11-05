import json
from pathlib import Path

from umbra.routines import engine as eng
from umbra.routines import worker
from umbra.unified import project


def feature_task(env):
    env.umbra("task", "add", "Sumar correctamente", "-d", "add debe sumar",
              "-a", "add(2, 3) == 5")


def run_feature(env):
    env.umbra("run", "1", "-r", "feature", "--foreground")
    return env.run()["status"]


def test_feature_routine_runs_five_stages(env):
    env.mode("noop", "ok", "noop")
    feature_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    assert env.attempts() == [("plan", "done"), ("build", "done"), ("review", "done"),
                              ("verify", "done"), ("scan", "done")]
    plan_call, build_call, verify_call = env.claude_calls()
    assert '"plan": "modo noop"' in build_call["prompt"]
    tools = plan_call["args"][plan_call["args"].index("--allowedTools") + 1]
    assert "Edit" not in tools and "acceptEdits" not in plan_call["args"]  # planner solo lee
    review = env.codex_calls()[0]
    assert review["args"][review["args"].index("-s") + 1] == "read-only"
    assert "+    return a + b" in review["prompt"]  # el revisor recibe el diff
    assert len(env.prs()) == 1


def test_review_finding_sends_back_to_build(env):
    env.mode("noop", "ok", "ok", "noop")
    env.codex_mode("high", "clean")
    feature_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    assert [s for s, _ in env.attempts()] == ["plan", "build", "review", "build", "review",
                                              "verify", "scan"]
    assert "falta validar entradas" in env.claude_calls()[2]["prompt"]
    finding = env.conn.execute("SELECT severity, file, line FROM finding").fetchone()
    assert tuple(finding) == ("high", "calc.py", 1)


def plain_feature(env):
    env.plain_routine()  # sin escalada ni árbitro: el significado original de estas pruebas


def test_persistent_findings_block(env):
    plain_feature(env)
    env.mode("noop", "ok")
    env.codex_mode("high")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    assert [s for s, _ in env.attempts()].count("review") == 3
    assert env.prs() == []


def test_verify_unmet_criterion_reworks(env):
    env.mode("noop", "ok", "unmet", "ok", "noop")
    feature_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    assert [s for s, _ in env.attempts()] == ["plan", "build", "review", "verify", "build",
                                              "review", "verify", "scan"]


def test_plan_questions_block_before_build(env):
    env.mode("blocked")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    assert env.attempts() == [("plan", "blocked")]


def test_invalid_codex_output_falls_back_to_the_claude_reviewer(env):
    env.mode("noop", "ok", "noop")
    env.codex_mode("invalid")
    feature_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"  # Codex falló; revisó Claude en su lugar
    reviews = [a for a in env.attempts() if a[0] == "review"]
    assert reviews == [("review", "error"), ("review", "done")]


def test_read_only_stage_cannot_touch_workspace(env):
    env.mode("noop", "ok", "touch")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"


def test_pause_and_resume(env):
    feature_task(env)
    env.monkeypatch.setattr(worker, "spawn", lambda root: None)
    env.umbra("run", "1")
    env.umbra("pause", "1")
    assert worker.work(env.root) == 0 and env.run()["status"] == "PAUSED"
    env.umbra("resume", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"


def test_cancel_waiting_run_closes_pr(env):
    feature_task(env)
    env.umbra("run", "1", "--foreground")
    wt = Path(env.run()["worktree"])
    env.umbra("cancel", "1")
    assert env.run()["status"] == "CANCELLED"
    assert env.prs()[0]["state"] == "CLOSED" and not wt.exists()


def test_cancel_during_run_stops_at_safe_point(env):
    feature_task(env)
    original = eng.Engine.build

    def build_then_cancel(self, run_id, stage, wt):
        outcome = original(self, run_id, stage, wt)
        eng.cancel(self, run_id)  # el humano cancela mientras BUILD corre
        return outcome

    env.monkeypatch.setattr(eng.Engine, "build", build_then_cancel)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "CANCELLED"
    assert env.prs() == [] and not Path(env.run()["worktree"]).exists()


def test_retry_blocked_run_with_fresh_cycles(env):
    env.mode("broken")
    feature_task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    env.mode("ok")
    env.umbra("retry", "1", "--from", "build", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    statuses = [s for _, s in env.attempts()]
    assert statuses == ["tests_failed"] * 6 + ["done"]  # 3 con cada perfil, luego el reintento
    types = [e["type"] for e in json.loads(env.umbra("log", "1", "--json").output)]
    assert "run.retried" in types


def test_policy_intersects_profile_actions(env):
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace("[policy]\n", '[policy]\nactions = ["read"]\n'))
    engine = eng.Engine(env.root, env.root / ".umbra", env.conn, project.load_project(env.root))
    assert engine.profile("builder-tdd").actions == ["read"]


def test_reviewer_and_builder_remember_earlier_rounds(env):
    env.mode("noop", "ok", "ok", "ok", "noop")
    env.codex_mode("high:ronda uno", "high:ronda dos", "clean")
    feature_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    first, second, third = env.codex_calls()
    assert "ronda uno" not in first["prompt"]
    assert "ronda uno" in second["prompt"]  # el revisor sabe qué pidió antes
    assert "ronda dos" in third["prompt"]
    third_build = env.claude_calls()[3]["prompt"]
    pending, history = third_build.split("ya corregidos")
    assert "ronda dos" in pending and "ronda uno" in history


def test_retry_after_findings_block_rebuilds_with_the_blocking_finding(env):
    plain_feature(env)
    env.mode("noop", "ok", "ok", "ok", "ok", "noop")
    env.codex_mode("high:uno", "high:dos", "high:la que bloquea", "clean")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    env.umbra("retry", "1", "--foreground")  # sin --from: debe volver a BUILD, no a REVIEW
    assert env.run()["status"] == "WAITING_APPROVAL"
    stages = [s for s, _ in env.attempts()]
    assert stages[-4:] == ["build", "review", "verify", "scan"]
    assert stages.count("review") == 4
    assert "la que bloquea" in env.claude_calls()[4]["prompt"]  # no la de la ronda anterior
