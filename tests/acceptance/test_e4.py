import json
import shutil
import sys
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "agents" / "todo-reviewer"


@pytest.fixture
def todo_agent(env, tmp_path):
    """Copia del agente de ejemplo apuntando a este intérprete."""
    src = tmp_path / "todo-reviewer"
    shutil.copytree(EXAMPLE, src)
    manifest = src / "agent.toml"
    manifest.write_text(manifest.read_text().replace(
        '["python",', f"['{sys.executable}',"), encoding="utf-8")
    return src


def custom_routine(env):
    udir = env.root / ".umbra"
    (udir / "routines" / "custom.yaml").write_text(
        "name: custom\nstages:\n  - name: build\n    profile: builder\n"
        "  - name: review\n    profile: todo-review\n  - name: ship\n")
    (udir / "profiles" / "todo-review.toml").write_text(
        'name = "todo-review"\nagent = "todo-reviewer"\nroles = ["review"]\n'
        'actions = ["read"]\n')
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")


def test_third_agent_integrates_without_core_changes(env, todo_agent):
    env.umbra("agent", "add", str(todo_agent))
    listed = {a["name"]: a for a in json.loads(env.umbra("agent", "list", "--json").output)}
    assert listed["todo-reviewer"]["verified"] is False and listed["claude-code"]["builtin"]

    custom_routine(env)
    env.umbra("run", "1", "-r", "custom", "--foreground")
    assert env.run()["status"] == "FAILED"  # sin verificar no entra en rutinas
    reason = env.conn.execute("SELECT payload FROM event WHERE type = 'run.failed'").fetchone()
    assert "no verificado" in reason[0]

    result = json.loads(env.umbra("agent", "test", "todo-reviewer", "--json").output)
    assert result["verified"] and result["output"]["findings"][0]["rule"] == "todo-added"

    env.umbra("task", "add", "Sumar otra vez", "-a", "add(2, 3) == 5")
    env.umbra("run", "2", "-r", "custom", "--foreground")
    assert env.run(2)["status"] == "WAITING_APPROVAL"
    assert ("review", "done") in env.attempts(2)


def test_changed_manifest_invalidates_seal(env, todo_agent):
    env.umbra("agent", "add", str(todo_agent))
    env.umbra("agent", "test", "todo-reviewer")
    registered = Path(env.root.parent / "home" / "agents" / "todo-reviewer" / "agent.toml")
    registered.write_text(registered.read_text() + '\n# cambio\n')
    listed = {a["name"]: a for a in json.loads(env.umbra("agent", "list", "--json").output)}
    assert listed["todo-reviewer"]["verified"] is False


def test_invalid_output_is_not_verified(env, tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "agent.toml").write_text(
        f"name = 'bad-agent'\ncommand = ['{sys.executable}', '-c', 'print(\"hola\")']\n")
    env.umbra("agent", "add", str(bad), "--project")
    result = env.umbra("agent", "test", "bad-agent", ok=False)
    assert result.exit_code == 1 and "sin JSON" in result.output
    assert not (env.root / ".umbra" / "agents" / "bad-agent" / "verified.json").exists()


def test_invalid_manifest_is_rejected(env, tmp_path):
    bad = tmp_path / "worse"
    bad.mkdir()
    (bad / "agent.toml").write_text("name = 'Con Espacios'\ncommand = []\n")
    assert env.umbra("agent", "add", str(bad), ok=False).exit_code == 2
    assert env.umbra("agent", "test", "nadie", ok=False).exit_code == 2


def test_profiles_new_show_list_and_test(env):
    env.umbra("profile", "new", "mi-constructor", "--from", "builder-tdd", "--model", "opus")
    shown = json.loads(env.umbra("profile", "show", "mi-constructor", "--json").output)
    assert shown["model"] == "opus" and "TDD" in shown["instructions_text"]
    origins = {p["name"]: p["origin"]
               for p in json.loads(env.umbra("profile", "list", "--json").output)}
    assert origins["mi-constructor"] == "proyecto" and origins["planner"] == "paquete"
    env.mode("noop")
    tested = json.loads(env.umbra("profile", "test", "mi-constructor", "--json").output)
    assert tested["ok"]
    assert env.umbra("profile", "new", "mi-constructor", ok=False).exit_code == 4
