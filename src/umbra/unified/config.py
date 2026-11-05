"""Resolución de perfiles y rutinas: proyecto > ~/.umbra > paquetes (~/.umbra/packs/*) > valores
por defecto de umbra."""

import os
import tomllib
from pathlib import Path

import yaml

from umbra.contracts.profile import Profile
from umbra.contracts.routine import Routine

DEFAULTS = Path(__file__).resolve().parent.parent / "defaults"


class ConfigError(Exception):
    pass


def umbra_home() -> Path:
    return Path(os.environ.get("UMBRA_HOME", Path.home() / ".umbra"))


def packs() -> list[Path]:
    """Paquetes instalados (`umbra pack sync`): perfiles, rutinas y playbooks privados o de un
    equipo, fuera de cualquier repo. En orden alfabético; el primero gana si dos repiten."""
    base = umbra_home() / "packs"
    return sorted(d for d in base.iterdir() if d.is_dir()) if base.is_dir() else []


def _bases(udir: Path, kind: str) -> list[Path]:
    """De más a menos prioridad."""
    return [udir / kind, umbra_home() / kind, *(p / kind for p in packs()), DEFAULTS / kind]


def _search(udir: Path, kind: str, filename: str) -> Path:
    for base in _bases(udir, kind):
        if (base / filename).exists():
            return base / filename
    raise ConfigError(f"no se encontró {kind[:-1]} '{filename}'")


def load_profile(udir: Path, name: str) -> Profile:
    path = _search(udir, "profiles", f"{name}.toml")
    data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    return Profile(**data, source=path)


def load_routine(udir: Path, name: str) -> Routine:
    path = _search(udir, "routines", f"{name}.yaml")
    return Routine(**yaml.safe_load(path.read_text(encoding="utf-8-sig")))


def list_names(udir: Path, kind: str, suffix: str) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for base in reversed(_bases(udir, kind)):  # el último gana
        if base.is_dir():
            for p in base.glob(f"*{suffix}"):
                found[p.stem] = p
    return dict(sorted(found.items()))
