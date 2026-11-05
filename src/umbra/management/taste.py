"""Tu gusto: lo que elegiste, pediste y aprobaste en los diseños de todos tus proyectos.

Vive en `~/.umbra/gusto.md` (es tuyo, no de un repo) y el diseñador y el crítico lo reciben en
cada tarea. Se puede editar a mano: umbra solo añade líneas al final."""

from datetime import date
from pathlib import Path

from umbra.unified import config as cfg

FILE = "gusto.md"
CHARS = 5000  # lo más reciente: el gusto cambia
HEADER = ("# Gusto de la persona en diseño\n\n"
          "Lo que eligió, pidió y aprobó en sus proyectos. Úsalo para acertar a la primera; si "
          "algo se contradice, manda lo más reciente. (Lo escribe umbra; puedes editarlo.)\n\n")


def path() -> Path:
    return cfg.umbra_home() / FILE


def record(project: str, text: str) -> None:
    f = path()
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        f.write_text(HEADER, encoding="utf-8")
    line = " ".join(text.split())
    with f.open("a", encoding="utf-8") as out:
        out.write(f"- {date.today().isoformat()} · {project} · {line}\n")


def load() -> str:
    """Para el sobre del diseñador y el crítico (vacío si aún no hay nada)."""
    f = path()
    if not f.is_file():
        return ""
    text = f.read_text(encoding="utf-8", errors="replace")
    if len(text) <= CHARS:
        return text.strip()
    tail = text[-CHARS:]
    return (HEADER + tail[tail.find("\n") + 1:]).strip()  # sin una línea a medias
