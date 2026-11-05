"""Paralelismo, aprobación por spec y modo noche (spec 018)."""

import json

import pytest

from tests.acceptance.test_watch_actions import drive, settle, sync_worker
from tests.conftest import git
from umbra import service

SPEC = """# Demo

### User Story 1 - Sumar (Priority: P1)

Que add sume. FR-001

**Acceptance Scenarios**:

1. **Given** a, **When** b, **Then** add(2, 3) == 5

### User Story 2 - Multiplicar (Priority: P2)

Que exista mul. FR-002

**Acceptance Scenarios**:

1. **Given** d, **When** e, **Then** mul existe
"""
TASKS = "- [ ] T001 [US1] Arreglar `add`\n- [ ] T002 [US2] Añadir `mul`\n"


def configure(env, parallel=1, autopilot=True):
    cfg = env.root / ".umbra" / "project.toml"
    text = cfg.read_text().replace("parallel = 1", f"parallel = {parallel}")
    if autopilot:
        text = text.replace("[autopilot]\nenabled = false", "[autopilot]\nenabled = true")
    cfg.write_text(text)


@pytest.fixture
def spec(env):
    d = env.root / "specs" / "001-demo"
    d.mkdir(parents=True)
    (d / "spec.md").write_text(SPEC, encoding="utf-8")
    (d / "tasks.md").write_text(TASKS, encoding="utf-8")
    env.umbra("spec", "tasks", "specs/001-demo")  # dos borradores encadenados
    return d


def builds(env):
    return [tuple(r) for r in env.conn.execute(
        "SELECT started_at, ended_at FROM attempt WHERE stage = 'build' ORDER BY started_at")]


def test_two_independent_tasks_run_at_the_same_time(env):
    configure(env, parallel=2, autopilot=False)
    env.mode("slow")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("task", "add", "Sumar de nuevo", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "2", "--foreground")
    reasons = [json.loads(r[0]) for r in env.conn.execute(
        "SELECT payload FROM event WHERE type IN ('run.failed', 'run.blocked')")]
    assert env.run(1)["status"] == env.run(2)["status"] == "WAITING_APPROVAL", reasons
    (s1, e1), (s2, e2) = builds(env)
    assert s2 < e1, "la segunda empezó antes de que terminara la primera"


def test_with_parallel_one_tasks_still_go_one_at_a_time(env):
    env.mode("slow")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("task", "add", "Sumar de nuevo", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "2", "--foreground")
    (s1, e1), (s2, e2) = builds(env)
    assert s2 >= e1


def night(env):
    configure(env, parallel=1, autopilot=True)
    env.mode("ok", "append_mul")  # la primera arregla add; la segunda añade mul
    sync_worker(env)
    return env.umbra("night", "--spec", "specs/001-demo").output


def test_spec_tasks_integrate_alone_and_one_approval_merges_the_spec(env, spec):
    out = night(env)
    assert "aceptadas: 1, 2" in out and "en marcha: 1" in out
    # el worker (síncrono en la prueba) integró la 1 en la rama de la spec, el piloto automático
    # arrancó la 2 (dependía de la 1) y, con las dos integradas, abrió el PR de la spec
    assert env.run(1)["status"] == env.run(2)["status"] == "SUCCEEDED"
    assert env.run(1)["base_branch"] == env.run(2)["base_branch"] == "spec/001-demo"
    prs = env.prs()
    assert [(p["base"], p["state"]) for p in prs] == [
        ("spec/001-demo", "MERGED"), ("spec/001-demo", "MERGED"), ("main", "OPEN")]
    assert prs[2]["head"] == "spec/001-demo"
    assert prs[2]["title"] == "umbra spec 001-demo"
    assert env.conn.execute("SELECT COUNT(*) FROM approval").fetchone()[0] == 0
    ctx = service.load(env.root)
    progress = service.spec_progress(ctx)[0]
    assert progress["stories_done"] == 2 and progress["pr"]["state"] == "waiting"
    assert service.waiting_specs(ctx) == ["specs/001-demo"]
    assert "Integrada en spec/001-demo" in env.umbra("log", "2").output
    assert "la spec se aprueba completa" in env.umbra("explain", "2").output

    out = env.umbra("approve", "--spec", "001-demo", input="y\n").output
    assert "spec integrada" in out
    git(env.root, "fetch", "-q", "origin", "main")
    merged = git(env.root, "show", "origin/main:calc.py").stdout
    assert "return a + b" in merged and "def mul" in merged
    assert service.spec_pr(ctx, "specs/001-demo")["state"] == "merged"
    event = json.loads(env.conn.execute("SELECT payload FROM event WHERE type = 'spec.approved'"
                                        ).fetchone()[0])
    assert event["spec_dir"] == "specs/001-demo"
    again = env.umbra("approve", "--spec", "001-demo", input="y\n", ok=False)
    assert "ya está integrada" in again.output


def test_approve_spec_before_all_stories_are_integrated_explains(env, spec):
    configure(env, autopilot=False)
    result = env.umbra("approve", "--spec", "specs/001-demo", ok=False)
    assert "faltan por integrar" in result.output


def test_i_integrates_the_spec_from_watch(env, spec):
    night(env)

    async def scenario(app, pilot, notes):
        assert app._decision.get("spec_waiting")
        await pilot.press("I")
        await pilot.pause(0.2)
        await pilot.press("y")
        await settle(app, pilot)
        assert any("umbra approve --spec 001-demo" in n for n in notes)
        assert service.spec_pr(service.load(env.root), "specs/001-demo")["state"] == "merged"

    drive(env, scenario)


def test_night_from_watch_accepts_and_starts(env, spec):
    configure(env, autopilot=False)
    env.mode("ok")
    sync_worker(env)

    async def scenario(app, pilot, notes):
        await pilot.press("N")
        await pilot.pause(0.2)
        await pilot.press("y")
        await settle(app, pilot)
        assert any("umbra night" in n for n in notes)
        statuses = [r[0] for r in env.conn.execute("SELECT status FROM task ORDER BY number")]
        assert statuses == ["done", "accepted"]  # la 1 se integró; la 2 espera (autopilot off)

    drive(env, scenario)
