"""La rama base avanza mientras una tarea espera (caso real: tareas 3 y 4 sobre calc.py)."""

import json

from tests.conftest import git


def two_tasks_touching_the_same_place(env):
    env.umbra("task", "add", "Multiplicar", "-a", "mul(2, 3) == 6")
    env.umbra("task", "add", "Dividir", "-a", "div(6, 3) == 2")
    env.mode("append_mul")
    env.umbra("run", "1", "--foreground")
    env.mode("append_div")
    env.umbra("run", "2", "--foreground")
    assert env.run(1)["status"] == env.run(2)["status"] == "WAITING_APPROVAL"
    env.umbra("approve", "1", input="y\n")  # la base del remoto avanza con la tarea 1


def remote_main(env):
    return git(env.root, "ls-remote", "origin", "refs/heads/main").stdout.split()[0]


def test_approving_a_conflicting_pr_stops_with_a_clear_reason(env):
    two_tasks_touching_the_same_place(env)
    result = env.umbra("approve", "2", input="y\n", ok=False)
    assert result.exit_code != 0 and "umbra retry 2 --from build" in result.output
    assert env.run(2)["status"] == "BLOCKED"
    assert env.conn.execute("SELECT COUNT(*) FROM approval a JOIN run r ON r.id = a.run_id"
                            " JOIN task t ON t.id = r.task_id WHERE t.number = 2"
                            ).fetchone()[0] == 0  # la aprobación no se registra
    exp = json.loads(env.umbra("explain", "2", "--json").output)
    assert exp["code"] == "base_conflict" and exp["headline"].startswith("Mientras esperaba")
    assert exp["actions"][0]["command"] == "umbra retry 2 --from build"


def test_retry_brings_the_base_in_resolves_and_reverifies(env):
    two_tasks_touching_the_same_place(env)
    env.umbra("approve", "2", input="y\n", ok=False)
    env.mode("resolve")
    env.umbra("retry", "2", "--from", "build", "--foreground")
    run = env.run(2)
    assert run["status"] == "WAITING_APPROVAL"
    assert run["base_sha"] == remote_main(env)  # políticas y diffs contra la base nueva
    prompt = env.claude_calls()[-1]["prompt"]
    assert "conflictos" in prompt and "AMBOS lados" in prompt
    types = [e["type"] for e in json.loads(env.umbra("log", "2", "--json").output)]
    assert "base.conflict" in types
    env.umbra("approve", "2", input="y\n")
    assert env.run(2)["status"] == "SUCCEEDED"
    final = git(env.root, "show", f"{remote_main(env)}:calc.py").stdout
    assert "def mul" in final and "def div" in final and "<<<<<<<" not in final


def test_unresolved_conflict_blocks_with_its_own_reason(env):
    two_tasks_touching_the_same_place(env)
    env.umbra("approve", "2", input="y\n", ok=False)
    env.mode("noop")  # el agente no toca los archivos en conflicto
    env.umbra("retry", "2", "--from", "build", "--foreground")
    assert env.run(2)["status"] == "BLOCKED"
    exp = json.loads(env.umbra("explain", "2", "--json").output)
    assert exp["code"] == "base_conflict_unresolved"


def test_new_runs_start_from_what_is_in_the_remote_not_the_stale_local_copy(env):
    env.umbra("task", "add", "Multiplicar", "-a", "x")
    env.mode("append_mul")
    env.umbra("run", "1", "--foreground")
    (env.root / "notas.md").write_text("borrador\n")
    git(env.root, "add", "notas.md")  # cambios sin guardar: approve no toca la copia local
    env.umbra("approve", "1", input="y\n")
    local_main = git(env.root, "rev-parse", "main").stdout.strip()
    assert local_main != remote_main(env)  # la copia local no se enteró del merge
    env.umbra("task", "add", "Otra", "-a", "y")
    env.mode("ok")
    env.umbra("run", "2", "--foreground")
    assert env.run(2)["base_sha"] == remote_main(env)


def test_clean_base_update_needs_no_conflict_resolution(env):
    env.umbra("task", "add", "Multiplicar", "-a", "x")
    env.umbra("task", "add", "Otra cosa", "-a", "y")
    env.mode("append_mul")
    env.umbra("run", "1", "--foreground")
    (env.root / "otro.txt").write_text("independiente")  # cambio que no choca
    git(env.root, "add", "otro.txt")
    git(env.root, "commit", "-q", "-m", "otro")
    git(env.root, "push", "-q", "origin", "HEAD:refs/heads/main")
    env.umbra("retry", "1", "--from", "build", "--foreground")
    assert env.run(1)["status"] == "WAITING_APPROVAL"
    types = [e["type"] for e in json.loads(env.umbra("log", "1", "--json").output)]
    assert "base.synced" in types and "base.conflict" not in types
    env.umbra("approve", "1", input="y\n")
    assert env.run(1)["status"] == "SUCCEEDED"
