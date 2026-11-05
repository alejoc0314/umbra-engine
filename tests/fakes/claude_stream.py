"""`claude` falso para stream-json: por cada mensaje de usuario emite el siguiente turno de un
.jsonl grabado (FAKE_STREAM) hasta su `result`. FAKE_TURN_FILES = {"<turno>": {ruta: texto}}
escribe archivos al empezar ese turno (turno 1 = el primero). Termina al cerrarse stdin."""

import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")
state_dir = Path(os.environ["FAKE_STATE_DIR"])
state_dir.mkdir(parents=True, exist_ok=True)
calls_file = state_dir / "claude_calls.json"
lines = Path(os.environ["FAKE_STREAM"]).read_text(encoding="utf-8").splitlines()
effects = json.loads(os.environ.get("FAKE_TURN_FILES", "{}"))
pos, turn = 0, 0

for raw in sys.stdin:
    if not raw.strip():
        continue
    turn += 1
    msg = json.loads(raw)
    calls = json.loads(calls_file.read_text(encoding="utf-8")) if calls_file.exists() else []
    calls.append({"args": sys.argv[1:], "message": msg["message"]["content"], "cwd": os.getcwd()})
    calls_file.write_text(json.dumps(calls), encoding="utf-8")
    for rel, content in effects.get(str(turn), {}).items():
        Path(rel).parent.mkdir(parents=True, exist_ok=True)
        Path(rel).write_text(content, encoding="utf-8")
    while pos < len(lines):
        line = lines[pos]
        pos += 1
        print(line, flush=True)
        if line.startswith("{") and json.loads(line).get("type") == "result":
            break
