"""umbra es open source: lo privado (Conecty, UMBRA Design, datos personales) vive fuera del repo,
en paquetes locales de ~/.umbra."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# el producto de diseño del equipo (no el comando `umbra design`, que es genérico)
PRIVATE = re.compile(r"(?i:conecty|umbra-design|umbradesign|Asus-116338)|UMBRA Design"
                     r"|9167996196")


def test_nothing_private_in_tracked_files():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    leaks = []
    for name in files:
        if name in ("uv.lock", "tests/unit/test_open_source.py"):
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        leaks += [f"{name}: {m.group(0)}" for m in PRIVATE.finditer(text)]
    assert not leaks, "referencias privadas en el repo:\n" + "\n".join(leaks)
