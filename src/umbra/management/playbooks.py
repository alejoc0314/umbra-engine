"""Playbooks: cómo arranca un proyecto nuevo de cada stack (comandos, CI, convenciones).

Los de umbra viven en `defaults/playbooks/<stack>/`; los del equipo, en
`~/.umbra/playbooks/<stack>/` (un repo git que `umbra playbook sync <url>` clona o actualiza) y
tienen prioridad. Cada carpeta trae `playbook.toml` y los archivos que copia."""

import subprocess
import tomllib
from pathlib import Path

from umbra.unified import config as cfg


class PlaybookError(Exception):
    pass


def home() -> Path:
    return cfg.umbra_home() / "playbooks"


def available() -> dict[str, Path]:
    """stack → carpeta del playbook (los del equipo pisan a los de umbra)."""
    found: dict[str, Path] = {}
    for base in (cfg.DEFAULTS / "playbooks", home()):
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if (d / "playbook.toml").is_file():
                    found[d.name] = d
    return found


def load(stack: str) -> tuple[dict, Path]:
    folder = available().get(stack)
    if not folder:
        raise PlaybookError(f"no hay playbook para «{stack}»; hay: "
                            + ", ".join(available()) + f". Añade {home() / stack}/playbook.toml")
    try:
        data = tomllib.loads((folder / "playbook.toml").read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as e:
        raise PlaybookError(f"{folder / 'playbook.toml'} no es TOML válido: {e}") from e
    return data, folder


def sync(url: str) -> str:
    """Trae (o pone al día) los playbooks del equipo desde un repo git. Devuelve «clonado» o
    «actualizado»."""
    dest = home()
    if (dest / ".git").is_dir():
        proc = subprocess.run(["git", "-C", str(dest), "pull", "-q", "--ff-only"],
                              capture_output=True, text=True)
        what = "actualizado"
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(["git", "clone", "-q", url, str(dest)], capture_output=True,
                              text=True)
        what = "clonado"
    if proc.returncode != 0:
        raise PlaybookError(proc.stderr.strip() or proc.stdout.strip() or "git falló")
    return what
