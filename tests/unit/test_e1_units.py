import json
from decimal import Decimal
from pathlib import Path

import pytest

from umbra.actions.policy import check_diff, is_test_file
from umbra.adapters.base import AgentRun
from umbra.adapters.claude_code import allowed_tools, build_command, parse_stream
from umbra.blocks import lease
from umbra.contracts.envelope import Envelope, TaskInfo
from umbra.contracts.profile import Profile
from umbra.unified.store import open_store


@pytest.mark.parametrize("path,expected", [
    ("tests/test_a.py", True), ("src/test_a.py", True), ("a_test.go", True),
    ("web/app.spec.ts", True), ("web/app.test.js", True), ("__tests__/x.js", True),
    ("src/calc.py", False), ("docs/testing.md", False),
])
def test_is_test_file(path, expected):
    assert is_test_file(path) is expected


def codes(changes, edits=None):
    return [v.code for v in check_diff(changes, test_edits=edits)]


def test_check_diff_rules():
    assert codes([("A", "tests/test_new.py"), ("M", "src/a.py")]) == []
    assert codes([("D", "tests/test_a.py")]) == ["test_deleted"]
    assert codes([("M", "tests/test_a.py")]) == ["test_changed"]  # sin detalle: se bloquea
    assert codes([("A", ".github/workflows/ci.yml")]) == ["protected_path"]
    assert check_diff([("D", "tests/test_a.py")])[0].message == \
        "test existente borrado: tests/test_a.py"


def test_adding_tests_to_an_existing_file_is_allowed():
    m = [("M", "sandbox/tests/test_calc.py")]
    added = ["", "", "def test_power():", "    assert power(2, 3) == 8"]
    assert codes(m, {m[0][1]: ([], added)}) == []
    # ampliar un import conserva lo que había: también vale (caso real de la tarea 4)
    assert codes(m, {m[0][1]: (["from sandbox.calc import add"],
                               ["import pytest", "from sandbox.calc import add, mean"])}) == []


def test_weakening_existing_tests_is_blocked():
    m = [("M", "tests/test_calc.py")]
    changed = check_diff(m, test_edits={m[0][1]: (["    assert add(2, 3) == 5"],
                                                  ["    assert add(2, 3) is not None"])})
    assert [v.code for v in changed] == ["test_changed"] and "assert add(2, 3) == 5" in \
        changed[0].message
    # quitar un nombre del import tampoco es "ampliar"
    assert codes(m, {m[0][1]: (["from calc import add, sub"], ["from calc import add"])}) == \
        ["test_changed"]
    for skip in ("@pytest.mark.skip", "    pytest.skip('x')", "it.skip('a', () => {})",
                 "describe.only('x', () => {})", "$this->markTestSkipped();"):
        assert codes(m, {m[0][1]: ([], [skip])}) == ["test_skipped"], skip


def test_lease_contention_and_fencing(tmp_path):
    conn = open_store(tmp_path)
    t1 = lease.acquire(conn, "w", "a")
    assert t1 == 1 and lease.acquire(conn, "w", "b") is None
    assert lease.holds(conn, "w", t1)
    lease.acquire(conn, "w", "a", ttl=-1)  # el dueño lo deja vencer
    t2 = lease.acquire(conn, "w", "b")
    assert t2 == 3 and not lease.holds(conn, "w", t1)  # el token viejo ya no publica


def make_req(tmp_path, **profile):
    prof = Profile(name="builder", agent="claude-code", roles=["build"],
                   **({"actions": ["read", "edit", "run_tests"], "model": "sonnet"} | profile))
    env = Envelope(run_id="r", stage="build", attempt_id="a", input_sha="s",
                   task=TaskInfo(number=1, title="t"))
    return AgentRun(env, prof, tmp_path, tmp_path / "log", ["pytest -q"])


def test_build_command_maps_profile(tmp_path):
    cmd = build_command(make_req(tmp_path))
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
    tools = cmd[cmd.index("--allowedTools") + 1]
    assert "Bash(pytest -q *)" in tools and "Edit" in tools
    assert "--bare" not in cmd  # usa el login de la suscripción
    assert "--fallback-model" not in cmd
    cmd = build_command(make_req(tmp_path, model="claude-fable-5-1",
                                 fallback_model="claude-opus-5-5"))
    assert cmd[cmd.index("--fallback-model") + 1] == "claude-opus-5-5"


def test_shell_allows_commands_but_never_git_that_changes_things(tmp_path):
    cmd = build_command(make_req(tmp_path, actions=["read", "shell"]))
    assert "Bash" in cmd[cmd.index("--allowedTools") + 1].split(",")
    denied = cmd[cmd.index("--disallowedTools") + 1]
    assert "Bash(git push:*)" in denied and "Bash(git commit:*)" in denied
    assert "--disallowedTools" not in build_command(make_req(tmp_path))


def test_read_only_profile_has_no_edit_or_bash():
    assert allowed_tools(["read"], ["pytest -q"]) == ["Read", "Glob", "Grep"]


def test_parse_stream_ok_error_and_invalid():
    ok = json.dumps({"type": "result", "is_error": False, "session_id": "s",
                     "total_cost_usd": 0.1, "structured_output": {"summary": "x"}})
    res = parse_stream("noise\n" + ok)
    assert res.ok and res.cost == Decimal("0.1") and res.output.summary == "x"
    err = parse_stream(json.dumps({"type": "result", "is_error": True, "result": "boom"}))
    assert not err.ok and err.error == "boom"
    bad = parse_stream(json.dumps({"type": "result", "structured_output": {"status": "??"}}))
    assert not bad.ok and "inválida" in bad.error
    assert not parse_stream("").ok


def test_cost_is_rounded_decimal():
    line = '{"type": "result", "total_cost_usd": 0.10419219999999998, "structured_output": {}}'
    assert str(parse_stream(line).cost) == "0.104192"


def test_prompt_names_exact_allowed_commands(tmp_path):
    from umbra.adapters.base import render_prompt
    req = make_req(tmp_path)
    assert "`pytest -q`" in render_prompt(req.envelope, ["pytest -q"])
    assert "No tienes permitido" in render_prompt(req.envelope, [])


def test_profile_instructions_path():
    p = Profile(name="x", agent="a", roles=[], instructions="x.md", source=Path("/p/x.toml"))
    assert p.instructions_path() == Path("/p/x.md")
