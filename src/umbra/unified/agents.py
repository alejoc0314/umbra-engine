"""Registro de agentes por manifiesto (agents/<nombre>/agent.toml) y sello de verificación."""

import hashlib
import json
import shutil
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from umbra.unified.config import umbra_home
from umbra.unified.store import now

BUILTIN = ("claude-code", "codex")
MANIFEST = "agent.toml"
SEAL = "verified.json"


class AgentManifest(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    adapter: Literal["script"] = "script"
    command: list[str] = Field(min_length=1)
    description: str = ""


class AgentNotVerified(Exception):
    pass


def search_dirs(udir: Path | None) -> list[Path]:
    dirs = [umbra_home() / "agents"]
    if udir:
        dirs.insert(0, udir / "agents")  # el del proyecto gana
    return dirs


def find(name: str, udir: Path | None) -> Path | None:
    for base in search_dirs(udir):
        if (base / name / MANIFEST).exists():
            return base / name
    return None


def load_manifest(agent_dir: Path) -> AgentManifest:
    text = (agent_dir / MANIFEST).read_text(encoding="utf-8-sig")  # tolera BOM
    return AgentManifest(**tomllib.loads(text))


def _digest(agent_dir: Path) -> str:
    return hashlib.sha256((agent_dir / MANIFEST).read_bytes()).hexdigest()


def is_verified(agent_dir: Path) -> bool:
    seal = agent_dir / SEAL
    return seal.exists() and json.loads(seal.read_text())["sha256"] == _digest(agent_dir)


def seal(agent_dir: Path) -> None:
    (agent_dir / SEAL).write_text(json.dumps({"sha256": _digest(agent_dir), "at": now()}))


def register(source: Path, udir: Path | None, project: bool) -> tuple[AgentManifest, Path]:
    manifest = load_manifest(source)  # valida antes de copiar nada
    if manifest.name in BUILTIN:
        raise ValueError(f"'{manifest.name}' es un agente integrado")
    target = ((udir if project else umbra_home()) / "agents" / manifest.name)
    if target.resolve() != source.resolve():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(SEAL, "__pycache__"))
    return manifest, target


def listing(udir: Path | None) -> list[dict]:
    rows = [{"name": n, "adapter": n, "builtin": True, "verified": True,
             "available": shutil.which("claude" if n == "claude-code" else n) is not None,
             "path": None} for n in BUILTIN]
    seen = set()
    for base in search_dirs(udir):
        for manifest in sorted(base.glob(f"*/{MANIFEST}")) if base.is_dir() else []:
            d = manifest.parent
            if d.name in seen:
                continue
            seen.add(d.name)
            m = load_manifest(d)
            exe = m.command[0].replace("{agent_dir}", str(d))
            rows.append({"name": m.name, "adapter": m.adapter, "builtin": False,
                         "verified": is_verified(d),
                         "available": shutil.which(exe) is not None or Path(exe).exists(),
                         "path": d.as_posix()})
    return rows
