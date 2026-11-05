"""`codex` falso (`codex exec`). Modo por FAKE_CODEX_MODE (lista, una entrada por llamada)."""

import json
import os
import sys
from pathlib import Path

state_dir = Path(os.environ["FAKE_STATE_DIR"])
state_dir.mkdir(parents=True, exist_ok=True)
calls_file = state_dir / "codex_calls.json"
calls = json.loads(calls_file.read_text()) if calls_file.exists() else []
args = sys.argv[1:]
calls.append({"args": args, "prompt": sys.stdin.read()})
calls_file.write_text(json.dumps(calls))

modes = os.environ.get("FAKE_CODEX_MODE", "clean").split(",")
mode = modes[min(len(calls), len(modes)) - 1]
last = Path(args[args.index("-o") + 1])

print(json.dumps({"type": "thread.started", "thread_id": "thread-fake"}))
if mode == "error":
    print(json.dumps({"type": "turn.failed", "error": {"message": "boom"}}))
    sys.exit(1)
findings = []
if mode.startswith(("high", "medium")):  # "high:<mensaje>" para distinguir rondas
    severity = mode.partition(":")[0]
    message = mode.partition(":")[2] or "falta validar entradas"
    findings = [{"severity": severity, "message": message, "file": "calc.py",
                 "line": 1, "rule": None}]
body = "no es json" if mode == "invalid" else json.dumps(
    {"status": "done", "summary": f"revisión {mode}", "findings": findings, "questions": []})
last.write_text(body)
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 50, "output_tokens": 10}}))
