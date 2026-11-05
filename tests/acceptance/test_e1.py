import json
from pathlib import Path

from tests.conftest import git
from umbra.blocks import lease
from umbra.routines import worker
from umbra.unified.store import new_id, now


def queue_task(env, title="Sumar correctamente"):
    env.umbra("task", "add", title, "-d", "add debe sumar", "-a", "add(2, 3) == 5")


def test_happy_path_to_merge(env):
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    run = env.run()
    assert run["status"] == "WAITING_APPROVAL"
    art = env.conn.execute("SELECT * FROM artifact WHERE run_id = ?", (run["id"],)).fetchone()
    assert art["exit_code"] == 0 and art["tested_sha"] == run["head_sha"]
    assert len(env.prs()) == 1 and env.prs()[0]["headRefOid"] == run["head_sha"]
    # el agente recibió el sobre y los permisos del perfil
    call = env.claude_calls()[0]
    assert '"stage": "build"' in call["prompt"]
    assert "--allowedTools" in call["args"] and "acceptEdits" in call["args"]

    env.umbra("approve", "1", input="y\n")
    run = env.run()
    assert run["status"] == "SUCCEEDED"
    assert env.prs()[0]["state"] == "MERGED"
    assert env.conn.execute("SELECT status FROM task").fetchone()[0] == "done"
    assert not Path(run["worktree"]).exists()
    approval = env.conn.execute("SELECT * FROM approval").fetchone()
    assert approval["head_sha"] == run["head_sha"] and approval["decision"] == "approved"


def test_failing_tests_block_after_retries(env):  # T04
    env.mode("broken")
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    run = env.run()
    assert run["status"] == "BLOCKED"
    codes = [r[0] for r in env.conn.execute("SELECT exit_code FROM artifact")]
    assert len(codes) == 6 and all(c != 0 for c in codes)  # 3 intentos por perfil (escalada)
    assert env.prs() == []


def test_fix_cycle_sends_feedback(env):
    env.mode("broken", "ok")
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    second = env.claude_calls()[1]["prompt"]
    assert "exit code" in second


def test_deleting_a_test_is_blocked(env):  # T05
    env.mode("delete_test")
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    payload = env.conn.execute("SELECT payload FROM event WHERE type = 'run.blocked'").fetchone()
    assert "test existente borrado" in payload[0]
    assert env.prs() == []


def test_agent_timeout_is_bounded(env):
    profiles = env.root / ".umbra" / "profiles"
    toml = (Path(__file__).parents[2] / "src/umbra/defaults/profiles/builder.toml").read_text()
    (profiles / "builder.toml").write_text(toml.replace("max_minutes  = 20", "max_minutes = 0.03"))
    env.mode("sleep")
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    assert env.conn.execute("SELECT status FROM attempt").fetchone()[0] == "timeout"


def test_no_changes_and_questions_block(env):
    env.mode("noop")
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    env.mode("blocked")
    queue_task(env, "otra")
    env.umbra("run", "2", "--foreground")
    assert env.run(2)["status"] == "BLOCKED"


def test_run_is_idempotent(env):  # T03
    queue_task(env)
    env.monkeypatch.setattr(worker, "spawn", lambda root: None)
    first = json.loads(env.umbra("run", "1", "--json").output)
    second = json.loads(env.umbra("run", "1", "--json").output)
    assert first[0]["run_id"] == second[0]["run_id"] and second[0]["created"] is False
    assert env.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 1


def test_restart_during_build_resumes_without_duplicates(env):  # T06
    queue_task(env)
    env.monkeypatch.setattr(worker, "spawn", lambda root: None)
    env.umbra("run", "1")
    conn = env.conn
    run = env.run()
    # simular un worker muerto a mitad de BUILD: intento 'running' y lease de otro dueño vencido
    conn.execute("UPDATE run SET status = 'RUNNING', stage = 'build' WHERE id = ?", (run["id"],))
    conn.execute("INSERT INTO attempt (id, run_id, stage, attempt_no, status, started_at)"
                 " VALUES (?, ?, 'build', 1, 'running', ?)", (new_id(), run["id"], now()))
    lease.acquire(conn, worker.LEASE, "dead@host", ttl=-1)
    assert worker.work(env.root) == 1
    run = env.run()
    assert run["status"] == "WAITING_APPROVAL"
    statuses = [r[0] for r in conn.execute("SELECT status FROM attempt ORDER BY attempt_no")]
    assert statuses == ["interrupted", "done"]
    worker.work(env.root)  # relanzar no hace nada nuevo
    assert len(env.prs()) == 1


def test_live_lease_blocks_second_worker(env):
    queue_task(env)
    env.monkeypatch.setattr(worker, "spawn", lambda root: None)
    env.umbra("run", "1")
    lease.acquire(env.conn, worker.LEASE, "alive@host")
    assert worker.work(env.root) == 0
    assert env.run()["status"] == "QUEUED"


def test_pr_create_failure_reuses_existing_pr(env):  # T07
    env.monkeypatch.setenv("FAKE_GH_CREATE_FAIL", "1")
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    assert len(env.prs()) == 1


def test_commit_after_evaluation_invalidates_approval(env):  # T08
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    run = env.run()
    wt = Path(run["worktree"])
    (wt / "extra.txt").write_text("cambio no evaluado")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "extra")
    git(wt, "push", "-q", "origin", f"HEAD:refs/heads/{run['branch']}")
    result = env.umbra("approve", "1", input="y\n", ok=False)
    assert result.exit_code != 0 and "posteriores" in result.output
    assert env.run()["status"] == "WAITING_APPROVAL"
    assert env.conn.execute("SELECT COUNT(*) FROM approval").fetchone()[0] == 0


def test_approve_requires_interactive_terminal(env):
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    from umbra import service
    env.monkeypatch.setattr(service, "interactive", lambda: False)
    result = env.umbra("approve", "1", ok=False)
    assert result.exit_code == 3
    assert env.run()["status"] == "WAITING_APPROVAL"


def test_reject_closes_pr(env):
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    env.umbra("reject", "1", "-m", "no me gusta")
    assert env.run()["status"] == "CANCELLED"
    assert env.prs()[0]["state"] == "CLOSED"


def test_exec_registered_command(env):
    result = env.umbra("exec", "test", "--json", ok=False)
    assert result.exit_code == 1  # calc.add devuelve 0 en la base: el test falla
    data = json.loads(result.output)
    assert data["exit_code"] != 0 and "pytest" in data["command"]
    assert env.umbra("exec", "nope", ok=False).exit_code == 2


def test_log_and_evidence(env):
    queue_task(env)
    env.umbra("run", "1", "--foreground")
    events = json.loads(env.umbra("log", "1", "--json").output)
    types = [e["type"] for e in events]
    assert types[0] == "run.queued" and "pr.opened" in types and "evidence.tests" in types
    data = json.loads(env.umbra("evidence", "1", "--json").output)
    assert data["cost"] == "0.05" and data["artifacts"][0]["exit_code"] == 0
