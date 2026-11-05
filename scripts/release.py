"""Publicar una versión de umbra-engine (herramienta de quien desarrolla umbra, no de la CLI).

    uv run python scripts/release.py prepare minor   # PR con el número nuevo y el CHANGELOG
    uv run python scripts/release.py publish         # tras mezclarlo: etiqueta vX.Y.Z + release

Cada PR deja en «## Sin publicar» del CHANGELOG qué cambia, en lenguaje llano. `prepare` lo
convierte en la versión nueva; `publish` etiqueta lo que hay en main y crea la release de GitHub,
que es lo que instala `umbra self-update`.
"""

import re
import subprocess
import sys
from pathlib import Path

from umbra.unified import version

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "src" / "umbra" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
_VERSION = re.compile(r'^__version__ = "([^"]+)"', re.M)


def sh(*args: str, capture: bool = False) -> str:
    proc = subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8",
                          capture_output=capture)
    if proc.returncode != 0:
        sys.exit(f"falló: {' '.join(args)}\n{(proc.stderr or '').strip()}")
    return (proc.stdout or "").strip()


def current(text: str) -> str:
    return _VERSION.search(text).group(1)


def prepare(part: str) -> None:
    sh("git", "fetch", "-q", "origin")
    if sh("git", "status", "--porcelain", capture=True):
        sys.exit("hay cambios sin commitear")
    if sh("git", "rev-parse", "HEAD", capture=True) != sh("git", "rev-parse", "origin/main",
                                                          capture=True):
        sys.exit("ponte en main actualizado: git switch main && git pull")
    init = INIT.read_text(encoding="utf-8")
    new = version.bump(current(init), part)
    try:
        CHANGELOG.write_text(version.roll_changelog(CHANGELOG.read_text(encoding="utf-8"), new),
                             encoding="utf-8")
    except version.VersionError as e:
        sys.exit(str(e))
    INIT.write_text(_VERSION.sub(f'__version__ = "{new}"', init, count=1), encoding="utf-8")
    branch = f"release/v{new}"
    sh("git", "switch", "-c", branch)
    sh("git", "commit", "-qam", f"release: v{new}")
    sh("git", "push", "-q", "-u", "origin", branch)
    notes = version.changelog_section(CHANGELOG.read_text(encoding="utf-8"), new)
    sh("gh", "pr", "create", "--base", "main", "--title", f"release: v{new}", "--body",
       f"{notes}\n\nAl mezclarlo: `uv run python scripts/release.py publish`.")
    print(f"PR de v{new} abierto. Al mezclarlo: uv run python scripts/release.py publish")


def publish() -> None:
    sh("git", "fetch", "-q", "--tags", "origin")
    new = current(sh("git", "show", "origin/main:src/umbra/__init__.py", capture=True))
    tag = f"v{new}"
    if sh("git", "tag", "--list", tag, capture=True):
        sys.exit(f"{tag} ya está publicada")
    notes = version.changelog_section(sh("git", "show", "origin/main:CHANGELOG.md",
                                         capture=True), new)
    if not notes:
        sys.exit(f"el CHANGELOG de main no tiene la sección {tag}: ¿falta mezclar el PR?")
    sh("git", "tag", "-a", tag, "-m", tag, "origin/main")
    sh("git", "push", "-q", "origin", tag)
    sh("gh", "release", "create", tag, "--title", tag, "--notes", notes, "--verify-tag")
    print(f"{tag} publicada. Para instalarla: umbra self-update")


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["prepare", ("major" | "minor" | "patch") as part]:
            prepare(part)
        case ["publish"]:
            publish()
        case _:
            sys.exit(__doc__)
