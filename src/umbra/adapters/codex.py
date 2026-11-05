"""Adaptador de Codex: `codex exec --json` (usa el login guardado de la CLI)."""

import json
import shutil
from pathlib import Path

from pydantic import BaseModel, ValidationError

from umbra.adapters.base import AgentResult, AgentRun, render_prompt
from umbra.blocks.process import run_bounded
from umbra.contracts.envelope import StageOutput


def strict_schema(node):
    """Esquema estricto (estilo structured outputs): todo requerido, sin propiedades extra."""
    if isinstance(node, dict):
        node = {k: strict_schema(v) for k, v in node.items() if k not in ("default", "title")}
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"])
        return node
    if isinstance(node, list):
        return [strict_schema(v) for v in node]
    return node


def sandbox_for(actions: list[str]) -> str:
    return "workspace-write" if "edit" in actions else "read-only"


def build_command(req: AgentRun, schema_file: Path, last_file: Path) -> list[str]:
    cmd = ["codex", "exec", "--json", "-s", sandbox_for(req.profile.actions),
           "--output-schema", str(schema_file), "-o", str(last_file)]
    if req.profile.model:
        cmd += ["-m", req.profile.model]
    if req.profile.reasoning_effort:  # si no, manda la config global del usuario (puede ser "max")
        cmd += ["-c", f'model_reasoning_effort="{req.profile.reasoning_effort}"']
    return [*cmd, "-"]  # prompt por stdin


def render(req: AgentRun) -> str:
    instructions = req.profile.instructions_path()
    head = instructions.read_text(encoding="utf-8") + "\n\n" if instructions else ""
    commands = req.allowed_commands if {"run_tests", "run_lint"} & set(req.profile.actions) \
        else []
    return head + render_prompt(req.envelope, commands)


def parse(jsonl: str, last_message: str | None,
          model: type[BaseModel] = StageOutput) -> AgentResult:
    session, tokens_in, tokens_out, error = None, 0, 0, None
    for line in jsonl.splitlines():
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        if kind == "thread.started":
            session = event.get("thread_id")
        elif kind == "turn.completed":
            usage = event.get("usage") or {}
            tokens_in += usage.get("input_tokens", 0)
            tokens_out += usage.get("output_tokens", 0)
        elif kind in ("turn.failed", "error"):
            error = (event.get("error") or {}).get("message") or event.get("message") or kind
    base = dict(session_id=session, estimated=True, input_tokens=tokens_in,
                output_tokens=tokens_out)
    if error:
        return AgentResult(ok=False, output=None, error=error, **base)
    if not last_message:
        return AgentResult(ok=False, output=None, error="codex no devolvió mensaje final", **base)
    try:
        output = model.model_validate_json(last_message)
    except ValidationError as e:
        return AgentResult(ok=False, output=None, error=f"salida inválida: {e}", **base)
    return AgentResult(ok=True, output=output, **base)


class CodexAdapter:
    name = "codex"

    def check(self) -> bool:
        return shutil.which("codex") is not None

    def run(self, req: AgentRun) -> AgentResult:
        schema_file = req.log_path.with_suffix(".schema.json")
        last_file = req.log_path.with_suffix(".last.json")
        schema_file.parent.mkdir(parents=True, exist_ok=True)
        schema_file.write_text(json.dumps(strict_schema(req.output_model.model_json_schema())),
                               encoding="utf-8")
        proc = run_bounded(build_command(req, schema_file, last_file), req.workspace,
                           timeout_s=req.profile.limits.max_minutes * 60,
                           log_path=req.log_path, stdin=render(req))
        if proc.timed_out:
            return AgentResult(ok=False, output=None, timed_out=True, estimated=True,
                               error=f"tiempo agotado ({req.profile.limits.max_minutes} min)")
        last = last_file.read_text(encoding="utf-8") if last_file.exists() else None
        return parse(proc.output, last, req.output_model)
