"""Sistemas de diseño: un catálogo fuera de los repos y la elección de cada proyecto.

Cada sistema es una carpeta con `sistema.toml` (`nombre`, `descripcion`, `guias` y `starter`,
rutas relativas a la carpeta) en `~/.umbra/design/<sistema>/` o en un paquete
(`~/.umbra/packs/*/design/<sistema>/`). El proyecto declara el suyo con `[design] system` en
`.umbra/project.toml` (versionado); `"ninguno"` = sin sistema del catálogo."""

import re
import tomllib
from pathlib import Path

from umbra.unified import config as cfg

NONE = "ninguno"
FILE = "sistema.toml"


def catalog() -> dict[str, dict]:
    """sistema → {nombre, descripcion, guias (rutas absolutas), starter (ruta o None)}."""
    bases = [cfg.umbra_home() / "design", *(p / "design" for p in reversed(cfg.packs()))]
    found: dict[str, dict] = {}
    for base in reversed(bases):  # ~/.umbra gana a los paquetes
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            f = d / FILE
            if not f.is_file():
                continue
            try:
                data = tomllib.loads(f.read_text(encoding="utf-8-sig"))
            except tomllib.TOMLDecodeError:
                continue
            starter = data.get("starter")
            found[d.name] = {
                "nombre": data.get("nombre", d.name), "descripcion": data.get("descripcion", ""),
                "guias": [(d / g).as_posix() for g in data.get("guias", [])],
                "starter": (d / starter).as_posix() if starter else None}
    return found


def chosen(config: dict) -> str | None:
    return config.get("design", {}).get("system")


def needs_choice(config: dict) -> bool:
    """Hay catálogo y el proyecto aún no dijo qué sistema usa."""
    return not chosen(config) and bool(catalog())


def resolved(config: dict) -> dict:
    """`[design]` con el sistema elegido aplicado: sus guías antes de las del proyecto y su
    archivo base si el proyecto no define uno."""
    design = dict(config.get("design", {}))
    system = catalog().get(chosen(config) or "")
    if system:
        guides = [*system["guias"], *design.get("guides", [])]
        design["guides"] = list(dict.fromkeys(guides))
        design.setdefault("starter", system["starter"])
    return design


def choices() -> list[tuple[str, str]]:
    """(clave, etiqueta) para preguntar: los del catálogo y «ninguno»."""
    out = [(k, f"{v['nombre']}" + (f" — {v['descripcion']}" if v["descripcion"] else ""))
           for k, v in catalog().items()]
    return out + [(NONE, "Ninguno: umbra lo define o lo extrae del código")]


def set_system(root: Path, name: str) -> None:
    """Escribe `[design] system = "<name>"` en `.umbra/project.toml`, sin tocar lo demás."""
    if name != NONE and name not in catalog():
        raise ValueError(f"no conozco el sistema «{name}»; hay: "
                         + ", ".join([*catalog(), NONE]))
    path = root / ".umbra" / "project.toml"
    text = path.read_text(encoding="utf-8")
    line = f'system = "{name}"'
    section = re.search(r"^\[design\][ \t]*$", text, re.M)
    if not section:
        text = text.rstrip("\n") + f"\n\n[design]\n{line}\n"
    else:
        end = re.search(r"^\[", text[section.end():], re.M)
        stop = section.end() + (end.start() if end else len(text) - section.end())
        body = text[section.end():stop]
        if re.search(r"^system\s*=", body, re.M):
            body = re.sub(r"^system\s*=.*$", line, body, count=1, flags=re.M)
        else:
            body = f"\n{line}" + body
        text = text[:section.end()] + body + text[stop:]
    path.write_text(text, encoding="utf-8")
