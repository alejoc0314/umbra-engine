"""Adaptador de Claude Code: `claude -p` con salida stream-json (usa el login del usuario)."""

import json
import shutil
import sys
from decimal import Decimal

from pydantic import BaseModel, ValidationError

from umbra.adapters.base import AgentResult, AgentRun, render_prompt
from umbra.blocks.process import run_bounded
from umbra.contracts.envelope import StageOutput


def _floats(node):
    """El stream se parsea con Decimal (costos exactos); la salida del agente vuelve a float."""
    if isinstance(node, dict):
        return {k: _floats(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_floats(v) for v in node]
    return float(node) if isinstance(node, Decimal) else node

ACTION_TOOLS = {
    "read": ["Read", "Glob", "Grep"],
    "search": ["Glob", "Grep"],
    "edit": ["Edit", "Write", "MultiEdit"],
    "shell": ["Bash"],
}
# con `shell`, el agente no publica ni reescribe historia: eso es del motor (y de la persona)
SHELL_DENY = [f"Bash(git {verb}:*)" for verb in
              ("commit", "push", "reset", "checkout", "switch", "clean", "stash", "rebase",
               "merge", "restore", "rm", "tag")]


def allowed_tools(actions: list[str], commands: list[str],
                  allowed_paths: list[str] | None = None) -> list[str]:
    tools: list[str] = []
    for action in actions:
        if action == "edit" and allowed_paths:  # editar solo esas rutas
            tools += [f"{t}({p})" for p in allowed_paths for t in ("Edit", "Write")]
            continue
        tools += ACTION_TOOLS.get(action, [])
    if {"run_tests", "run_lint"} & set(actions):
        for cmd in commands:
            tools += [f"Bash({cmd})", f"Bash({cmd} *)"]
    return list(dict.fromkeys(tools))


def playwright_server(screenshots_dir: str | None, files: bool = False) -> dict:
    """Servidor MCP de Playwright (sin cabeza); las capturas caen en `screenshots_dir`. Con
    `files`, puede abrir archivos locales (`file://`): las maquetas HTML del diseñador."""
    # network: browser_route simula peticiones (servicios externos que no existen en local);
    # storage: cookies y almacenamiento de la sesión
    args = ["-y", "@playwright/mcp@latest", "--headless", "--caps=network,storage"]
    if sys.platform == "win32":  # Edge viene con Windows; Chrome (el de Playwright) no siempre
        args += ["--browser", "msedge"]
    if files:
        args.append("--allow-unrestricted-file-access")
    if screenshots_dir:
        args += ["--output-dir", screenshots_dir]
    return {"command": "npx", "args": args}


def mcp_config(screenshots_dir: str | None) -> str:
    return json.dumps({"mcpServers": {"playwright": playwright_server(screenshots_dir)}})


def mcp_servers(req: AgentRun) -> dict[str, dict]:
    """Playwright si el perfil navega y hay app; más los servidores que declara el perfil, con
    `{profile_dir}` y `{workspace}` resueltos."""
    p = req.profile
    servers = {}
    if "browse" in p.actions and req.envelope.app_url:  # solo con una app que visitar
        servers["playwright"] = playwright_server(req.envelope.screenshots_dir)
    elif "render" in p.actions:  # el diseñador fotografía sus maquetas HTML
        servers["playwright"] = playwright_server(
            (req.workspace / "design" / "png").as_posix(), files=True)
    marks = {"{profile_dir}": p.source.parent.as_posix() if p.source else "",
             "{workspace}": req.workspace.as_posix()}

    def fill(text: str) -> str:
        for mark, value in marks.items():
            text = text.replace(mark, value)
        return text
    for name, s in p.mcp.items():
        server = {"command": fill(s.command), "args": [fill(a) for a in s.args]}
        if s.env:
            server["env"] = {k: fill(v) for k, v in s.env.items()}
        servers[name] = server
    return servers


def build_command(req: AgentRun) -> list[str]:
    p = req.profile
    # --setting-sources project: el agente no hereda plugins ni hooks globales de la persona
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose",
           "--setting-sources", "project",
           "--json-schema", json.dumps(req.output_model.model_json_schema())]
    if p.model:
        cmd += ["--model", p.model]
    if p.fallback_model:  # p. ej. Fable con Opus de respaldo si no está disponible
        cmd += ["--fallback-model", p.fallback_model]
    if p.effort:
        cmd += ["--effort", p.effort]
    if (instructions := p.instructions_path()) and instructions.exists():
        cmd += ["--append-system-prompt-file", str(instructions)]
    if "edit" in p.actions:
        cmd += ["--permission-mode", "acceptEdits"]
    tools = allowed_tools(p.actions, req.allowed_commands, p.allowed_paths)
    if servers := mcp_servers(req):  # solo estos: nada de los MCP globales de la persona
        cmd += ["--mcp-config", json.dumps({"mcpServers": servers}), "--strict-mcp-config"]
        tools += [f"mcp__{name}" for name in servers]
    if tools:
        cmd += ["--allowedTools", ",".join(tools)]
    if "shell" in p.actions:
        cmd += ["--disallowedTools", ",".join(SHELL_DENY)]
    cmd += ["--max-budget-usd", str(p.limits.max_cost_usd)]
    if req.resume_session:
        cmd += ["--resume", req.resume_session]
    return cmd


def parse_stream(text: str, model: type[BaseModel] = StageOutput) -> AgentResult:
    result = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                event = json.loads(line, parse_float=Decimal)  # costos sin ruido de float
            except ValueError:
                continue
            if event.get("type") == "result":
                result = event
    if result is None:
        return AgentResult(ok=False, output=None, error="claude no devolvió un evento result")
    usage = result.get("usage") or {}
    base = dict(
        session_id=result.get("session_id"),
        # claude ya suma en float; se redondea a micro-dólares para no arrastrar ruido
        cost=Decimal(str(result.get("total_cost_usd") or 0)).quantize(Decimal("0.000001")),
        model=next(iter(result.get("modelUsage") or {}), None),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )
    if result.get("is_error"):
        detail = (result.get("result") or result.get("error")
                  or "; ".join(str(e) for e in (result.get("errors") or []))
                  or f"claude devolvió un error sin detalle (subtipo {result.get('subtype')})")
        return AgentResult(ok=False, output=None, error=str(detail), **base)
    raw = result.get("structured_output")
    if raw is None and model is StageOutput:
        raw = {"summary": str(result.get("result") or "")}
    try:
        output = model.model_validate(_floats(raw))
    except ValidationError as e:
        return AgentResult(ok=False, output=None, error=f"salida inválida: {e}", **base)
    return AgentResult(ok=True, output=output, **base)


class ClaudeCodeAdapter:
    name = "claude-code"

    def check(self) -> bool:
        return shutil.which("claude") is not None

    def run(self, req: AgentRun) -> AgentResult:
        commands = req.allowed_commands if {"run_tests", "run_lint"} & set(req.profile.actions) \
            else []
        proc = run_bounded(build_command(req), req.workspace,
                           timeout_s=req.profile.limits.max_minutes * 60,
                           log_path=req.log_path, stdin=render_prompt(req.envelope, commands))
        if proc.timed_out:
            return AgentResult(ok=False, output=None, timed_out=True,
                               error=f"tiempo agotado ({req.profile.limits.max_minutes} min)")
        return parse_stream(proc.output, req.output_model)
