"""`claude` falso para flujos de varias fases: cada fase abre un proceso nuevo, así que retoma
FAKE_STREAM y FAKE_TURN_FILES donde los dejó el proceso anterior (cuenta los turnos ya
registrados en claude_calls.json) y delega en claude_stream.py."""

import json
import os
import runpy
from pathlib import Path

state = Path(os.environ["FAKE_STATE_DIR"])
state.mkdir(parents=True, exist_ok=True)
calls = state / "claude_calls.json"
done = len(json.loads(calls.read_text(encoding="utf-8"))) if calls.exists() else 0

rest, seen = [], 0
for line in Path(os.environ["FAKE_STREAM"]).read_text(encoding="utf-8").splitlines():
    if seen >= done:
        rest.append(line)
    if line.startswith("{") and json.loads(line).get("type") == "result":
        seen += 1
rest_file = state / f"stream_from_{done}.jsonl"
rest_file.write_text("\n".join(rest) + "\n", encoding="utf-8")
effects = json.loads(os.environ.get("FAKE_TURN_FILES", "{}"))
os.environ["FAKE_STREAM"] = str(rest_file)
os.environ["FAKE_TURN_FILES"] = json.dumps(
    {str(int(k) - done): v for k, v in effects.items() if int(k) > done})
runpy.run_path(str(Path(__file__).with_name("claude_stream.py")), run_name="__main__")
