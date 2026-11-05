import json

import pytest

from umbra.chat import hook, launcher
from umbra.management.dag import CycleError, topo_order
from umbra.unified import project


@pytest.fixture
def spec(env):
    path = env.root / "spec.md"
    path.write_text("# Calculadora\nNecesitamos modelo, API y docs.\n", encoding="utf-8")
    return path


def test_plan_creates_draft_tasks_with_dependencies(env, spec):
    env.mode("propose")
    result = json.loads(env.umbra("plan", str(spec), "--json").output)
    assert result == {"spec_version": 1, "questions": [], "tasks": [1, 2, 3]}
    tasks = json.loads(env.umbra("task", "list", "--json").output)
    assert [t["status"] for t in tasks] == ["draft"] * 3
    assert [t["waiting_on"] for t in tasks] == [[], [1], [2]]
    call = env.claude_calls()[0]
    assert "Necesitamos modelo" in call["prompt"] and "Edit" not in " ".join(call["args"])


def test_same_spec_reuses_version(env, spec):
    env.mode("propose_questions")
    first = json.loads(env.umbra("plan", str(spec), "--json").output)
    second = json.loads(env.umbra("plan", str(spec), "--json").output)
    assert first["spec_version"] == second["spec_version"] == 1
    assert first["questions"] == ["¿Qué base de datos?"] and first["tasks"] == []
    assert env.conn.execute("SELECT COUNT(*) FROM spec").fetchone()[0] == 1


def test_cyclic_proposal_creates_nothing(env, spec):  # T02
    env.mode("propose_cycle")
    result = env.umbra("plan", str(spec), ok=False)
    assert result.exit_code != 0 and "ciclo" in result.output
    assert env.conn.execute("SELECT COUNT(*) FROM task").fetchone()[0] == 0


def test_dependencies_gate_run_and_reject_cycles(env, spec):
    env.mode("propose")
    env.umbra("plan", str(spec))
    env.umbra("task", "accept", "1", "2", "3")
    assert "depende de tareas sin terminar: [1]" in env.umbra("run", "2", ok=False).output
    assert env.umbra("task", "deps", "1", "--on", "3", ok=False).exit_code == 4
    env.umbra("task", "deps", "3", "--on", "1")
    deps = json.loads(env.umbra("task", "deps", "3", "--on", "1", "--remove", "--json").output)
    assert deps["depends_on"] == [2]


def test_edit_uses_optimistic_revision(env):
    env.umbra("task", "add", "uno")
    env.umbra("task", "edit", "1", "--title", "uno bis", "--expect-revision", "1")
    stale = env.umbra("task", "edit", "1", "--title", "otro", "--expect-revision", "1", ok=False)
    assert stale.exit_code == 4 and "conflicto" in stale.output
    env.umbra("task", "drop", "1")
    assert env.conn.execute("SELECT title, status FROM task").fetchone()[:] == ("uno bis",
                                                                               "dropped")


def test_chat_settings_deny_approval_and_allow_safe_commands(env):
    config = project.load_project(env.root)
    settings = launcher.build_settings(config, "umbra")
    perms = settings["permissions"]
    assert "Bash(umbra approve *)" in perms["deny"] and "Bash(git push *)" in perms["deny"]
    assert "Edit(.umbra/project.toml)" in perms["deny"]
    assert "Bash(umbra exec test)" in perms["allow"] and "Bash(umbra status *)" in perms["allow"]
    assert "Bash(umbra run *)" in perms["ask"]
    assert not any("exec" in rule for rule in perms["ask"])  # ask taparía a los safe
    assert "_hook chat-event" in json.dumps(settings["hooks"])


def test_chat_settings_spec_commands(env):
    perms = launcher.build_settings(project.load_project(env.root), "umbra")["permissions"]
    expected = {"spec list": "allow", "spec tasks": "ask", "spec new": "deny",
                "spec resume": "deny"}
    for sub, bucket in expected.items():
        rule = f"Bash(umbra {sub} *)"
        assert rule in perms[bucket]
        assert not any(rule in perms[b] for b in perms if b != bucket)


def test_chat_launches_claude_with_umbra_context(env, monkeypatch):
    seen = {}

    def fake_run(cmd, cwd):
        seen["cmd"], seen["cwd"] = cmd, cwd
        return type("P", (), {"returncode": 0})()

    monkeypatch.setattr(launcher, "_run", fake_run)
    env.umbra("chat")
    cmd = seen["cmd"]
    assert "--append-system-prompt-file" in cmd and "--settings" in cmd and "-p" not in cmd
    prompt = (env.root / ".umbra/artifacts/chat/system-prompt.md").read_text(encoding="utf-8")
    assert "umbra approve" in prompt and seen["cwd"] == env.root


def test_chat_without_claude_fails_clearly(env, monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    result = env.umbra("chat", ok=False)
    assert result.exit_code == 2 and "claude" in result.output


def test_hook_records_chat_event(env):
    payload = {"tool_name": "Bash", "tool_input": {"command": "umbra status"},
               "cwd": str(env.root), "tool_response": {"interrupted": False}}
    hook.main(json.dumps(payload), env.root)
    row = env.conn.execute("SELECT type, origin, payload FROM event"
                           " WHERE type = 'chat.command'").fetchone()
    assert row["origin"] == "chat" and "umbra status" in row["payload"]
    hook.main("no es json", env.root)  # nunca rompe la sesión


def test_topo_order():
    assert topo_order([1, 2, 3], [(2, 1), (3, 2)]) == [1, 2, 3]
    with pytest.raises(CycleError):
        topo_order([1, 2], [(1, 2), (2, 1)])
    with pytest.raises(KeyError):
        topo_order([1], [(1, 9)])


def test_hook_records_session_id(env):
    payload = {"tool_name": "Bash", "tool_input": {"command": "umbra status"},
               "cwd": str(env.root), "session_id": "s1"}
    hook.main(json.dumps(payload), env.root)
    row = env.conn.execute("SELECT payload FROM event WHERE type = 'chat.command'").fetchone()
    assert json.loads(row["payload"])["session_id"] == "s1"
