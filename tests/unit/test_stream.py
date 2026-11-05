import json
import sys
from decimal import Decimal
from pathlib import Path

from umbra.chat.stream import Init, Stream, TextDelta, ToolUse, TurnEnd, parse_event

FAKES = Path(__file__).resolve().parent.parent / "fakes"
RECORDED = FAKES / "streams" / "specify_to_review.jsonl"


def fake_claude(tmp_path, monkeypatch, stream=RECORDED, effects=None) -> str:
    """Instala un `claude` falso (shim) y devuelve su ruta; el estado queda en tmp_path/state."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = FAKES / "claude_stream.py"
    if sys.platform == "win32":
        shim = bin_dir / "claude.cmd"
        shim.write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        shim = bin_dir / "claude"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        shim.chmod(0o755)
    monkeypatch.setenv("FAKE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("FAKE_STREAM", str(stream))
    monkeypatch.setenv("FAKE_TURN_FILES", json.dumps(effects or {}))
    return str(shim)


def calls(tmp_path):
    return json.loads((tmp_path / "state" / "claude_calls.json").read_text(encoding="utf-8"))


def test_eventos_tipados_y_arranque(tmp_path, monkeypatch):
    exe = fake_claude(tmp_path, monkeypatch)
    settings = tmp_path / "s.json"
    with Stream(tmp_path, settings, resume="abc", max_budget=Decimal("1.5"), exe=exe) as s:
        s.send("hola ñandú: áéíóú")
        evs = list(_until_end(s))
    assert [type(e) for e in evs] == [Init, TextDelta, ToolUse, TurnEnd]
    assert evs[0].session_id == "sess-1" and "speckit-specify" in evs[0].skills
    assert evs[2].target == "specs/001-x/spec.md"
    assert evs[3].total_cost == Decimal("0.10")
    call = calls(tmp_path)[0]
    assert call["message"] == "hola ñandú: áéíóú"
    for flag in ("-p", "--input-format", "--include-partial-messages", "--verbose"):
        assert flag in call["args"]
    assert call["args"][call["args"].index("--settings") + 1] == str(settings)
    assert call["args"][call["args"].index("--resume") + 1] == "abc"
    assert call["args"][call["args"].index("--max-budget-usd") + 1] == "1.5"
    assert s.proc.poll() is not None  # cierre limpio


def _until_end(s):
    for ev in s.events():
        yield ev
        if isinstance(ev, TurnEnd):
            return


def test_linea_no_json_ignorada_y_muerte_sin_result(tmp_path, monkeypatch):
    assert parse_event("no es json") == []
    assert parse_event("[1, 2]") == []
    only_init = tmp_path / "s.jsonl"
    only_init.write_text('{"type":"system","subtype":"init","session_id":"x"}\n', encoding="utf-8")
    exe = fake_claude(tmp_path, monkeypatch, stream=only_init)
    with Stream(tmp_path, exe=exe) as s:
        s.send("hola")
        s.proc.stdin.close()  # el falso termina al cerrarse stdin, sin emitir result
        evs = list(s.events())
    assert not any(isinstance(e, TurnEnd) for e in evs)
