import json

from tests.unit.test_e1_units import make_req
from umbra.adapters.codex import build_command, parse, sandbox_for, strict_schema
from umbra.contracts.envelope import output_schema


def test_strict_schema_requires_everything():
    schema = strict_schema(output_schema())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    finding = schema["$defs"]["Finding"]
    assert set(finding["required"]) == set(finding["properties"])
    assert "default" not in json.dumps(schema)


def test_sandbox_follows_actions():
    assert sandbox_for(["read"]) == "read-only"
    assert sandbox_for(["read", "edit"]) == "workspace-write"


def test_build_command(tmp_path):
    req = make_req(tmp_path, actions=["read"], model="gpt-5")
    cmd = build_command(req, tmp_path / "s.json", tmp_path / "l.json")
    assert cmd[:3] == ["codex", "exec", "--json"]
    assert cmd[cmd.index("-s") + 1] == "read-only" and cmd[-1] == "-"
    assert cmd[cmd.index("-m") + 1] == "gpt-5"
    assert "-c" not in cmd


def test_build_command_sets_reasoning_effort(tmp_path):
    req = make_req(tmp_path, actions=["read"], reasoning_effort="medium")
    cmd = build_command(req, tmp_path / "s.json", tmp_path / "l.json")
    assert cmd[cmd.index("-c") + 1] == 'model_reasoning_effort="medium"'


def test_parse_ok_failed_and_missing():
    events = "\n".join(json.dumps(e) for e in [
        {"type": "thread.started", "thread_id": "t1"},
        {"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 3}}])
    ok = parse(events, '{"status": "done", "summary": "s", "findings": [], "questions": []}')
    assert ok.ok and ok.session_id == "t1" and ok.input_tokens == 7 and ok.estimated
    failed = parse(json.dumps({"type": "turn.failed", "error": {"message": "x"}}), None)
    assert not failed.ok and failed.error == "x"
    assert not parse(events, None).ok
    assert "inválida" in parse(events, "nope").error


def test_build_command_resumes_a_cut_session(tmp_path):
    import dataclasses
    req = dataclasses.replace(make_req(tmp_path, actions=["read"]), resume_session="t-9")
    cmd = build_command(req, tmp_path / "s.json", tmp_path / "l.json")
    assert cmd[:4] == ["codex", "exec", "resume", "--json"]
    assert 'sandbox_mode="read-only"' in cmd and "-s" not in cmd  # resume no acepta -s
    assert cmd[-2:] == ["t-9", "-"]
