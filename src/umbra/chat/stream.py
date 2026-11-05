"""Hablar con `claude` por stream-json: arranque, envío de mensajes y eventos tipados."""

import json
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from umbra.blocks.process import background_kwargs, kill_tree, resolve


@dataclass
class Init:
    session_id: str
    skills: list[str] = field(default_factory=list)


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolUse:
    name: str
    target: str = ""


@dataclass
class TurnEnd:
    total_cost: Decimal
    is_error: bool = False
    text: str = ""


Event = Init | TextDelta | ToolUse | TurnEnd


def parse_event(line: str) -> list[Event]:
    """Una línea del stream → eventos (vacío si no interesa o no es JSON)."""
    try:
        ev = json.loads(line, parse_float=Decimal)
    except ValueError:
        return []
    if not isinstance(ev, dict):
        return []
    kind = ev.get("type")
    if kind == "system" and ev.get("subtype") == "init":
        skills = ev.get("skills") or ev.get("slash_commands") or []
        return [Init(str(ev.get("session_id", "")), [str(s) for s in skills])]
    if kind == "stream_event":
        delta = (ev.get("event") or {}).get("delta") or {}
        if delta.get("type") == "text_delta":
            return [TextDelta(str(delta.get("text", "")))]
    if kind == "assistant":
        out = []
        for block in (ev.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                inp = block.get("input") or {}
                target = next((str(inp[k]) for k in ("file_path", "path", "pattern", "command")
                               if k in inp), "")
                out.append(ToolUse(str(block.get("name", "")), target))
        return out
    if kind == "result":
        return [TurnEnd(Decimal(str(ev.get("total_cost_usd") or 0)),
                        bool(ev.get("is_error")), str(ev.get("result") or ""))]
    return []


class Stream:
    def __init__(self, cwd: Path, settings_path: Path | None = None, resume: str | None = None,
                 system_prompt_file: Path | None = None, max_budget: Decimal | None = None,
                 exe: str = "claude"):
        cmd = [resolve(exe), "-p", "--input-format", "stream-json",
               "--output-format", "stream-json", "--include-partial-messages", "--verbose",
               "--setting-sources", "project"]  # sin plugins ni hooks globales de la persona
        if settings_path:
            cmd += ["--settings", str(settings_path)]
        if system_prompt_file:
            cmd += ["--append-system-prompt-file", str(system_prompt_file)]
        if resume:
            cmd += ["--resume", resume]
        if max_budget is not None:
            cmd += ["--max-budget-usd", str(max_budget)]
        self.cmd = cmd
        self.proc = subprocess.Popen(
            cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", **background_kwargs())

    def send(self, text: str) -> None:
        msg = {"type": "user", "message": {"role": "user", "content": text}}
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def events(self) -> Iterator[Event]:
        """Eventos hasta que el proceso cierra stdout; sin TurnEnd = murió a mitad de turno."""
        for line in self.proc.stdout:
            yield from parse_event(line)

    def close(self, timeout: float = 5) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            kill_tree(self.proc.pid)
            self.proc.wait()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
