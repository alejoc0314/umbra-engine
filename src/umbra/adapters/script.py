"""Adaptador `script`: cualquier ejecutable que hable JSON por stdin/stdout.

Entrada (stdin): {"envelope", "profile", "instructions", "output_schema", "allowed_commands"}
Salida (stdout, última línea JSON): {"output": {...}, "session_id"?, "cost"?,
                                     "input_tokens"?, "output_tokens"?}
"""

import json
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from umbra.adapters.base import AgentResult, AgentRun
from umbra.blocks.process import run_bounded
from umbra.unified.agents import AgentManifest


class ScriptAdapter:
    def __init__(self, manifest: AgentManifest, agent_dir: Path):
        self.name = manifest.name
        self.command = [c.replace("{agent_dir}", str(agent_dir)) for c in manifest.command]

    def check(self) -> bool:
        from umbra.blocks.process import resolve
        return Path(resolve(self.command[0])).exists()

    def run(self, req: AgentRun) -> AgentResult:
        instructions = req.profile.instructions_path()
        payload = {
            "envelope": json.loads(req.envelope.model_dump_json()),
            "profile": req.profile.model_dump(mode="json", exclude={"source"}),
            "instructions": instructions.read_text(encoding="utf-8") if instructions else "",
            "output_schema": req.output_model.model_json_schema(),
            "allowed_commands": req.allowed_commands,
        }
        proc = run_bounded(self.command, req.workspace,
                           timeout_s=req.profile.limits.max_minutes * 60,
                           log_path=req.log_path, stdin=json.dumps(payload, ensure_ascii=False))
        if proc.timed_out:
            return AgentResult(ok=False, output=None, timed_out=True, estimated=True,
                               error=f"tiempo agotado ({req.profile.limits.max_minutes} min)")
        lines = [ln for ln in proc.output.splitlines() if ln.strip().startswith("{")]
        if proc.exit_code != 0 or not lines:
            return AgentResult(ok=False, output=None, estimated=True,
                               error=f"el agente terminó con exit {proc.exit_code} sin JSON")
        try:
            data = json.loads(lines[-1])
            output = req.output_model.model_validate(data["output"])
        except (ValueError, KeyError, ValidationError) as e:
            return AgentResult(ok=False, output=None, estimated=True,
                               error=f"salida inválida: {e}")
        return AgentResult(ok=True, output=output, session_id=data.get("session_id"),
                           cost=Decimal(str(data.get("cost", 0))),
                           estimated="cost" not in data,
                           input_tokens=data.get("input_tokens"),
                           output_tokens=data.get("output_tokens"))
