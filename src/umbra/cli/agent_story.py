"""Del registro en bruto de un agente (stream-json de Claude Code, JSON Lines de Codex) a frases
cortas: qué lee, qué edita, qué ejecuta y qué dice."""

import json
from pathlib import PurePath

VERBS = {"Read": "Lee", "Glob": "Busca archivos", "Grep": "Busca", "Edit": "Edita",
         "Write": "Escribe", "MultiEdit": "Edita", "Bash": "Ejecuta", "PowerShell": "Ejecuta",
         "WebFetch": "Consulta", "Task": "Delega", "Skill": "Usa la skill", "TodoWrite": "Anota"}
MAX_TEXT = 160


def _short(text: str, limit: int = MAX_TEXT) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _target(name: str, inp: dict) -> str:
    for key in ("file_path", "path", "notebook_path"):
        if key in inp:
            return PurePath(str(inp[key])).name
    if "command" in inp:
        return f"`{_short(str(inp['command']), 80)}`"
    if "pattern" in inp:
        return f"«{_short(str(inp['pattern']), 60)}»"
    if "skill" in inp:
        return str(inp["skill"])
    if "url" in inp:
        return str(inp["url"])
    return ""


def _claude(ev: dict) -> list[str]:
    kind = ev.get("type")
    if kind == "assistant":
        out = []
        for block in (ev.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and (text := block.get("text", "").strip()):
                out.append(f"💬 {_short(text)}")
            elif block.get("type") == "tool_use":
                name = str(block.get("name", ""))
                verb = VERBS.get(name, name)
                out.append(f"{verb} {_target(name, block.get('input') or {})}".strip())
        return out
    if kind == "user":
        for block in (ev.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result" \
                    and block.get("is_error"):
                return ["  ↳ falló"]
        return []
    if kind == "result":
        cost = ev.get("total_cost_usd")
        return [f"Terminó{f' (${cost:.2f})' if isinstance(cost, int | float) else ''}."]
    if kind == "rate_limit_event":
        return ["⏳ límite de uso: esperando."]
    return []


def _codex(ev: dict) -> list[str]:
    kind = ev.get("type")
    if kind == "thread.started":
        return ["Codex empieza."]
    if kind == "item.completed":
        item = ev.get("item") or {}
        t = item.get("type")
        if t == "agent_message":
            return [f"💬 {_short(str(item.get('text', '')))}"]
        if t == "command_execution":
            return [f"Ejecuta `{_short(str(item.get('command', '')), 80)}`"]
        if t == "file_change":
            files = ", ".join(PurePath(c.get("path", "")).name
                              for c in item.get("changes") or [] if isinstance(c, dict))
            return [f"Edita {files}".strip()]
        if t == "reasoning":
            return []
        return [f"{t}"] if t else []
    if kind == "turn.completed":
        return ["Terminó."]
    if kind in ("turn.failed", "error"):
        return [f"Falló: {_short(str((ev.get('error') or {}).get('message') or kind))}"]
    return []


def lines(raw: str) -> list[str]:
    """Frases a partir de líneas JSON en bruto; lo que no se reconoce se omite."""
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        out += _codex(ev) if str(ev.get("type", "")).startswith(
            ("thread.", "turn.", "item.")) else _claude(ev)
    return out
