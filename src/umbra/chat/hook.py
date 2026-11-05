"""Hook PostToolUse de Claude Code: registra cada comando del chat como evento de umbra."""

import json
from pathlib import Path

from umbra.unified import project
from umbra.unified.events import add_event
from umbra.unified.store import open_store


def record(payload: dict, cwd: Path) -> bool:
    command = (payload.get("tool_input") or {}).get("command")
    if not command:
        return False
    try:
        _, udir = project.umbra_dir(Path(payload.get("cwd") or cwd))
    except (project.NotARepo, project.NotInitialized):
        return False
    response = payload.get("tool_response")
    add_event(open_store(udir), None, "chat.command", "chat", command=command,
              tool=payload.get("tool_name"), session_id=payload.get("session_id"),
              interrupted=(response or {}).get("interrupted") if isinstance(response, dict)
              else None)
    return True


def main(stdin_text: str, cwd: Path) -> None:
    try:
        record(json.loads(stdin_text or "{}"), cwd)
    except Exception:  # un hook nunca debe romper la sesión del chat
        pass
