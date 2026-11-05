import subprocess

from umbra.unified.doctor import PROBES, diagnose, run_probe


def fake_run(outputs):
    def run(exe, args):
        out, code = outputs.get((exe, args), ("", 1))
        return subprocess.CompletedProcess([exe, *args], code, out, "")
    return run


ALL = {
    ("git", ("--version",)): ("git version 2.49.0.windows.1", 0),
    ("gh", ("--version",)): ("gh version 2.101.0 (2026-09-15)", 0),
    ("gh", ("auth", "status")): ("Logged in", 0),
    ("claude", ("--version",)): ("2.1.312 (Claude Code)", 0),
    ("claude", ("auth", "status", "--json")): ('{"loggedIn": true}', 0),
    ("codex", ("--version",)): ("codex-cli 0.163.0", 0),
    ("codex", ("login", "status")): ("Logged in using ChatGPT", 0),
}


def test_all_tools_present():
    result = diagnose(which=lambda n: n, run=fake_run(ALL))
    assert result["ok"]
    by_name = {t["name"]: t for t in result["tools"]}
    assert by_name["git"]["version"] == "2.49.0"
    assert by_name["git"]["session"] is None
    assert by_name["claude"]["session"] is True
    assert by_name["codex"]["version"] == "0.163.0"


def test_missing_required_tool_fails():
    result = diagnose(which=lambda n: None if n == "gh" else n, run=fake_run(ALL))
    assert not result["ok"]


def test_one_agent_is_enough():
    result = diagnose(which=lambda n: None if n == "codex" else n, run=fake_run(ALL))
    assert result["ok"]


def test_no_agent_fails():
    result = diagnose(which=lambda n: None if n in ("claude", "codex") else n, run=fake_run(ALL))
    assert not result["ok"]


def test_session_false_and_unknown():
    outputs = dict(ALL)
    outputs[("claude", ("auth", "status", "--json"))] = ('{"loggedIn": false}', 0)
    outputs[("codex", ("login", "status"))] = ("Not logged in", 1)
    claude = next(p for p in PROBES if p.name == "claude")
    codex = next(p for p in PROBES if p.name == "codex")
    assert run_probe(claude, which=lambda n: n, run=fake_run(outputs))["session"] is False
    assert run_probe(codex, which=lambda n: n, run=fake_run(outputs))["session"] is False
    outputs[("claude", ("auth", "status", "--json"))] = ("not json", 0)
    assert run_probe(claude, which=lambda n: n, run=fake_run(outputs))["session"] is None


def test_timeout_reports_unknown_version():
    git = next(p for p in PROBES if p.name == "git")
    result = run_probe(git, which=lambda n: n, run=lambda exe, args: None)
    assert result["found"] and result["version"] is None
