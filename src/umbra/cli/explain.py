"""`umbra explain`: por qué una tarea está como está y qué puedes hacer, en lenguaje llano."""

import typer
from rich.console import Group
from rich.padding import Padding
from rich.text import Text

from umbra.cli import context
from umbra.unified.explain import Explanation, explain_number
from umbra.unified.output import emit

JsonOpt = typer.Option(False, "--json", help="Salida en JSON")
MARKS = {"hecho": ("✓", "green"), "en curso": ("▶", "cyan"), "detenida": ("■", "yellow"),
         "falló": ("✗", "red"), "cancelada": ("○", "dim"), "en pausa": ("‖", "yellow"),
         "pendiente": ("·", "dim")}
STATE_STYLE = {"Detenida": "bold yellow", "Falló": "bold red", "Espera": "bold cyan",
               "Integrada": "bold green", "Trabajando": "bold cyan"}
STATE_KEY = {"Detenida": "blocked", "Falló": "failed", "Espera": "waiting", "Integrada": "done",
             "Trabajando": "running", "En cola": "queued", "En pausa": "paused"}


def renderable(exp: Explanation, compact: bool = False, technical: bool = False,
               colors: dict | None = None) -> Group:
    """`colors`: clave de estado (theme.STATE_KEYS) → color; sin él, los estilos de la CLI."""
    style = next((s for k, s in STATE_STYLE.items() if exp.state.startswith(k)), "bold")
    if colors:
        key = next((k for p, k in STATE_KEY.items() if exp.state.startswith(p)), None)
        style = f"bold {colors[key]}" if key and key in colors else "bold"
    parts = [Text.assemble((f"Tarea {exp.task} · ", "bold"), exp.title),
             Text.assemble("Estado: ", (exp.state, style))]
    if exp.progress:
        line = Text("Etapas: ")
        for i, (name, mark) in enumerate(exp.progress):
            sym, color = MARKS.get(mark, ("·", "dim"))
            line.append(f"{sym} {name}", style=color)
            if i < len(exp.progress) - 1:
                line.append("  →  ", style="dim")
        parts.append(line)
    parts += _about(exp.about, compact, technical)
    parts += [Text(""), Text(exp.headline, style="bold")]
    if exp.why:
        parts += [Text(""), Text("Por qué", style="bold underline"),
                  Padding(Text(exp.why), (0, 0, 0, 2))]
    if exp.details:
        parts += [Text(""), Text("Qué pasó", style="bold underline")]
        parts += [Padding(Text(f"• {d}"), (0, 0, 0, 2)) for d in exp.details]
    if exp.actions:
        parts += [Text(""), Text("Qué puedes hacer", style="bold underline")]
        for i, a in enumerate(exp.actions, 1):
            parts.append(Padding(Text(f"{i}. {a.what}"), (0, 0, 0, 2)))
            if a.command and not compact:
                parts.append(Padding(Text(a.command, style="cyan"), (0, 0, 0, 5)))
            elif a.command:
                parts[-1] = Padding(Text.assemble(f"{i}. {a.what}  ", (a.command, "cyan")),
                                    (0, 0, 0, 2))
    parts += _agent_notes(exp.about, compact)
    return Group(*parts)


def _section(title: str) -> list:
    return [Text(""), Text(title, style="bold underline")]


def _indent(text: str | Text, level: int = 2) -> Padding:
    return Padding(text if isinstance(text, Text) else Text(text), (0, 0, 0, level))


def _clip(text: str, limit: int) -> str:
    """Recorta conservando los saltos de línea (los pasos de un plan siguen legibles)."""
    text = "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _about(info: dict, compact: bool, technical: bool = False) -> list:
    """Lo que se pidió: en palabras de la persona y, en modo técnico o si no hay otra cosa, las
    indicaciones para el agente con sus criterios, alcance, prioridad y dependencias."""
    if not info:
        return []
    parts = _section("De qué trata")
    plain = info.get("about") and not technical
    if plain:
        parts.append(_indent(info["about"]))
        if not compact and info["description"]:
            parts += _section("Indicaciones técnicas para el agente")
            parts.append(_indent(_clip(info["description"], 1500)))
    else:
        parts.append(_indent(info["description"] or Text("(sin descripción)", style="dim")))
    if plain and compact and info["acceptance"]:
        parts.append(_indent(Text(f"Se comprobará con {len(info['acceptance'])} criterios "
                                  "concretos (t: detalle técnico).", style="dim")))
    elif info["acceptance"]:
        parts.append(_indent(Text("Se considera hecha cuando:", style="bold"), 2))
        parts += [_indent(f"• {c}", 4) for c in info["acceptance"]]
    else:
        parts.append(_indent(Text("Sin criterios de aceptación: conviene añadirlos con "
                                  "umbra task edit.", style="yellow")))
    facts = [f"Prioridad {info['priority']}"]
    if info["scope"] and not (plain and compact):
        facts.append("Archivos: " + ", ".join(info["scope"]))
    if info["spec_version"]:
        facts.append(f"Viene de la spec v{info['spec_version']}")
    parts.append(_indent(Text(" · ".join(facts), style="dim")))
    if origin := info.get("origin"):
        frs = f" ({', '.join(origin['requirements'])})" if origin["requirements"] else ""
        parts.append(_indent(Text(f"Viene de la historia {origin['story']} de "
                                  f"{origin['spec_dir']}{frs}.", style="dim")))
        if origin["misaligned"]:
            parts.append(_indent(Text(
                "Aviso: la historia cambió en spec.md después de crear esta tarea; revisa con "
                f"`umbra spec tasks {origin['spec_dir']}`.", style="yellow")))
    for label, items in (("Depende de", info["depends_on"]), ("Desbloquea", info["unblocks"])):
        if items:
            parts.append(_indent(Text.assemble((f"{label}: ", "bold"), "; ".join(
                f"{t['number']} {t['title']} ({t['status'].lower()})" for t in items))))
    return parts


def _agent_notes(info: dict, compact: bool) -> list:
    """Lo que planeó y lo que hizo el agente, si ya trabajó en ella."""
    limit = 500 if compact else 2000
    parts = []
    if info.get("plan"):
        parts += _section("Cómo lo planteó el planificador")
        parts.append(_indent(_clip(info["plan"], limit)))
    if info.get("work"):
        parts += _section("Qué hizo el agente")
        parts.append(_indent(_clip(info["work"], limit)))
    return parts


def explain(number: int, as_json: bool = JsonOpt) -> None:
    """Explica en lenguaje llano por qué una tarea está como está y qué puedes hacer."""
    ctx = context.load(as_json)
    task = context.task_by_number(ctx, number, as_json)
    exp = explain_number(ctx.conn, ctx.udir, task)
    emit(exp.as_dict(), as_json, lambda c: c.print(renderable(exp)))
