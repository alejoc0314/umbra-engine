"""Paquetes: perfiles, rutinas y playbooks que viven fuera del repo de umbra (lo privado de un
equipo, p. ej. un diseñador con su herramienta). Cada paquete es un repo git clonado en
`~/.umbra/packs/<nombre>/` con las carpetas `profiles/`, `routines/` y `playbooks/` que necesite.
umbra los busca después del proyecto y de `~/.umbra`, y antes de sus valores por defecto."""

import re
from pathlib import Path

from umbra.management.playbooks import PlaybookError, git_sync
from umbra.unified import config as cfg


class PackError(Exception):
    pass


def home() -> Path:
    return cfg.umbra_home() / "packs"


def name_from(url: str) -> str:
    """`git@github.com:equipo/umbra-equipo.git` → `umbra-equipo`."""
    name = re.split(r"[/:\\]", url.rstrip("/\\"))[-1].removesuffix(".git")
    if not re.fullmatch(r"[\w.-]+", name):
        raise PackError(f"no puedo sacar un nombre de «{url}»: usa --name")
    return name


def sync(url: str, name: str | None = None) -> tuple[str, Path]:
    """Clona o pone al día un paquete. Devuelve («clonado»|«actualizado», carpeta)."""
    dest = home() / (name or name_from(url))
    try:
        return git_sync(url, dest), dest
    except PlaybookError as e:
        raise PackError(str(e)) from e


def installed() -> list[dict]:
    """Cada paquete con lo que aporta."""
    out = []
    for pack in cfg.packs():
        out.append({"name": pack.name, "path": pack.as_posix(),
                    "profiles": sorted(p.stem for p in (pack / "profiles").glob("*.toml")),
                    "routines": sorted(p.stem for p in (pack / "routines").glob("*.yaml")),
                    "playbooks": sorted(d.name for d in (pack / "playbooks").glob("*")
                                        if (d / "playbook.toml").is_file())})
    return out
