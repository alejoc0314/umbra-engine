"""Diagnóstico de herramientas externas (git, gh, claude, codex)."""

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

TIMEOUT = 8


@dataclass(frozen=True)
class Probe:
    name: str
    kind: str  # "required" | "agent"
    version_args: tuple[str, ...]
    session_args: tuple[str, ...] | None = None
    session_json_key: str | None = None  # si la salida es JSON, clave booleana a leer


PROBES = (
    Probe("git", "required", ("--version",)),
    Probe("gh", "required", ("--version",), ("auth", "status")),
    Probe("claude", "agent", ("--version",), ("auth", "status", "--json"), "loggedIn"),
    Probe("codex", "agent", ("--version",), ("login", "status")),
)

_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?")


def _run(exe: str, args: tuple[str, ...]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            [exe, *args], capture_output=True, text=True, timeout=TIMEOUT,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def run_probe(probe: Probe, which=shutil.which, run=_run) -> dict:
    result = {"name": probe.name, "kind": probe.kind, "found": False,
              "version": None, "session": None}
    exe = which(probe.name)
    if not exe:
        return result
    result["found"] = True
    proc = run(exe, probe.version_args)
    if proc is not None:
        match = _VERSION.search(proc.stdout or proc.stderr or "")
        result["version"] = match.group(0) if match else None
    if probe.session_args:
        proc = run(exe, probe.session_args)
        if proc is not None:
            result["session"] = _session(proc, probe.session_json_key)
    return result


def _session(proc: subprocess.CompletedProcess, key: str | None) -> bool | None:
    if key is None:
        return proc.returncode == 0
    try:
        return bool(json.loads(proc.stdout).get(key))
    except (ValueError, AttributeError):
        return None


def diagnose(probes=PROBES, **kw) -> dict:
    tools = [run_probe(p, **kw) for p in probes]
    required_ok = all(t["found"] for t in tools if t["kind"] == "required")
    agent_ok = any(t["found"] for t in tools if t["kind"] == "agent")
    return {"ok": required_ok and agent_ok, "tools": tools}


def agent_available(name: str, **kw) -> bool:
    probe = next(p for p in PROBES if p.name == name)
    return run_probe(probe, **kw)["found"]
