"""Versión instalada, versiones publicadas (etiquetas vX.Y.Z) e instalación estable.

La instalación de diario sale de una versión publicada, no de la carpeta donde se desarrolla
umbra: así lo que está a medias en una rama no afecta a las tareas en marcha.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from importlib import metadata

from umbra import __version__
from umbra.blocks import notify
from umbra.blocks.process import background_kwargs
from umbra.unified import config as cfg

REPO = os.environ.get("UMBRA_REPO", "https://github.com/alejoc0314/umbra-engine")
_TAG = re.compile(r"refs/tags/v(\d+\.\d+\.\d+)$")
UNRELEASED = "## Sin publicar"


class VersionError(Exception):
    pass


def parse(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(p) for p in version.lstrip("v").split("."))
    return major, minor, patch


def bump(version: str, part: str) -> str:
    major, minor, patch = parse(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise VersionError(f"parte desconocida: {part} (major, minor o patch)")


def is_dev() -> bool:
    """¿Instalado en modo editable, apuntando a una carpeta de desarrollo?"""
    try:
        direct = metadata.distribution("umbra-engine").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return True  # ejecutado desde el código fuente sin instalar
    return bool(direct and json.loads(direct).get("dir_info", {}).get("editable"))


def label() -> str:
    return f"v{__version__}" + (" (desarrollo)" if is_dev() else "")


def published(ls_remote: str) -> list[str]:
    """Versiones publicadas, de la más antigua a la más nueva."""
    found = {m.group(1) for line in ls_remote.splitlines()
             if (m := _TAG.search(line.split("\t")[-1].strip()))}
    return sorted(found, key=parse)


def latest(repo: str = REPO) -> str | None:
    proc = subprocess.run(["git", "ls-remote", "--tags", repo], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise VersionError("no se pudo consultar las versiones publicadas: "
                           + (proc.stderr.strip() or "git ls-remote falló"))
    versions = published(proc.stdout)
    return versions[-1] if versions else None


def notes(version: str, repo: str = REPO) -> str:
    """Notas de la versión publicada (vacío si no se pueden leer)."""
    slug = "/".join(repo.rstrip("/").split("/")[-2:])
    try:
        proc = subprocess.run(["gh", "release", "view", f"v{version}", "--repo", slug,
                               "--json", "body", "-q", ".body"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def install_spec(version: str, repo: str = REPO) -> str:
    return f"git+{repo}@v{version}"


def handoff_script(version: str, uv: str, log: str, repo: str = REPO) -> str:
    """PowerShell que instala después de que umbra se cierre: en Windows un programa en uso
    no se puede reemplazar, y umbra corre desde la misma instalación que va a cambiar."""
    ok = notify.toast_script("umbra actualizado", f"Ya estás en v{version}.")
    bad = notify.toast_script("umbra no se pudo actualizar",
                              f"Cierra umbra watch y vuelve a intentarlo. Detalle: {log}")
    q = lambda s: s.replace("'", "''")  # noqa: E731 — comilla simple de PowerShell
    return (f"Start-Sleep -Seconds 2\n"
            f"& '{q(uv)}' tool install --force '{q(install_spec(version, repo))}' *> '{q(log)}'\n"
            f"if ($LASTEXITCODE -eq 0) {{\n{ok}\n}} else {{\n{bad}\n}}\n")


def install(version: str) -> str:
    """Instala la versión publicada. Devuelve qué pasó, para contárselo a la persona."""
    uv = shutil.which("uv")
    if not uv:
        raise VersionError("no encuentro `uv` en el PATH; instálalo o añádelo y reintenta")
    if sys.platform != "win32":
        proc = subprocess.run([uv, "tool", "install", "--force", install_spec(version)])
        if proc.returncode != 0:
            raise VersionError("uv no pudo instalar la versión (mira el mensaje de arriba)")
        return f"Instalada v{version}."
    home = cfg.umbra_home()
    home.mkdir(parents=True, exist_ok=True)
    script, log = home / "self-update.ps1", home / "self-update.log"
    script.write_text(handoff_script(version, uv, str(log)), encoding="utf-8-sig")
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                      "Bypass", "-File", str(script)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **background_kwargs())
    return (f"Actualizando a v{version} en segundo plano: te aviso al terminar. Cierra umbra "
            "watch si lo tienes abierto (Windows no deja reemplazar un programa en uso).")


# ---------- CHANGELOG ----------
def changelog_section(text: str, version: str) -> str:
    """El texto de una versión en el CHANGELOG (sin su título)."""
    m = re.search(rf"^## v{re.escape(version)}\b.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def roll_changelog(text: str, version: str, today: date | None = None) -> str:
    """Convierte «Sin publicar» en la versión nueva y deja «Sin publicar» vacío encima."""
    m = re.search(rf"^{UNRELEASED}\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m or not m.group(1).strip():
        raise VersionError("el CHANGELOG no tiene nada en «Sin publicar»: escribe qué cambia")
    day = (today or date.today()).isoformat()
    head = f"{UNRELEASED}\n\n## v{version} — {day}\n\n{m.group(1).strip()}\n\n"
    return text[:m.start()] + head + text[m.end():]
