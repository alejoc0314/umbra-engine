"""Motor de la conversación de requisitos: fases, permisos, preguntas y costo (sin pantalla)."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from fnmatch import fnmatch
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator

from umbra.chat.stream import Event, Init, Stream, TextDelta, TurnEnd
from umbra.unified.store import new_id, now

PHASES = ("specify", "clarify", "spec_review", "plan", "plan_review", "tasks", "done",
          "discarded")
TRANSITIONS = {
    ("specify", "next"): "clarify",
    ("specify", "skip_clarify"): "spec_review",
    ("clarify", "next"): "spec_review",
    ("spec_review", "approve"): "plan",
    ("spec_review", "changes"): "clarify",
    ("plan", "next"): "plan_review",
    ("plan_review", "approve"): "tasks",
    ("plan_review", "changes"): "plan",
    ("tasks", "next"): "done",
}
DEFAULT_MAX_COST = Decimal(5)
FEATURE_JSON = ".specify/feature.json"
_SPEC = ["specs/*/spec.md", "specs/*/checklists/*"]
WRITES: dict[str, list[str]] = {
    "specify": _SPEC, "clarify": _SPEC,
    "plan": [f"specs/*/{n}" for n in ("plan.md", "research.md", "data-model.md",
                                      "quickstart.md", "contracts/*")],
    "tasks": ["specs/*/tasks.md"],
    "spec_review": [], "plan_review": [],
}
MESSAGES = {"specify": "/speckit-specify", "clarify": "/speckit-clarify",
            "plan": "/speckit-plan", "tasks": "/speckit-tasks"}


def next_phase(phase: str, event: str = "next") -> str:
    if event == "discard" and phase not in ("done", "discarded"):
        return "discarded"
    try:
        return TRANSITIONS[(phase, event)]
    except KeyError:
        raise ValueError(f"transición inválida: {phase} --{event}-->") from None


def phase_settings(phase: str, script: str = "ps") -> dict:
    """Contenido de `--settings`: permisos de la fase; todo lo no listado queda denegado."""
    shell = "PowerShell" if script == "ps" else "Bash"
    allow = ["Read", "Glob", "Grep", "Skill", f"{shell}(.specify/scripts/**)",
             f"Write({FEATURE_JSON})", f"Edit({FEATURE_JSON})"]
    for glob in WRITES.get(phase, []):
        allow += [f"Write({glob})", f"Edit({glob})"]
    deny = ["WebFetch", "WebSearch", "Task", "NotebookEdit"]  # lo no listado se deniega en -p
    return {"permissions": {"allow": allow, "deny": deny}}


RETRO = ("\n\nEste proyecto ya existía antes de umbra (ver specs/000-linea-base/ y la constitución "
         "en .specify/memory/constitution.md). Antes de especificar el cambio, lee el código del "
         "área que toca la idea y añade a la spec una sección «## Cómo funciona hoy»: qué hace, "
         "sus reglas y qué tests la cubren, con rutas reales. La spec describe el cambio sobre "
         "esa base y respeta la constitución.")


def phase_message(phase: str, idea: str | None = None, comment: str | None = None,
                  root: Path | None = None) -> str:
    """El mensaje de la fase. En un proyecto que pasó por el onboarding, la spec documenta
    primero cómo funciona hoy lo que va a cambiar (spec retroactiva, justo a tiempo)."""
    if comment:
        return f"Cambios pedidos: {comment}"
    cmd = MESSAGES[phase]
    if phase != "specify" or not idea:
        return cmd
    retro = RETRO if root and (root / "specs" / "000-linea-base").is_dir() else ""
    return f"{cmd} {idea}{retro}{workspace_note(root)}"


def workspace_note(root: Path | None) -> str:
    """En un espacio de trabajo (spec 032), cada historia dice en qué repo se hace."""
    from umbra.unified import project
    try:
        members = project.members(root, project.load_project(root)) if root else {}
    except project.NotInitialized:
        return ""
    if not members:
        return ""
    repos = []
    for name, path in members.items():
        try:
            stack = project.load_project(path).get("project", {}).get("stack", "?")
        except project.NotInitialized:
            stack = "?"
        repos.append(f"{name} ({stack})")
    return ("\n\nEste proyecto es un espacio de trabajo con varios repos, cada uno en su carpeta: "
            f"{', '.join(repos)}. Cada historia de usuario MUST llevar, debajo de su título, una "
            "línea `**Repo**: <nombre>` con el repo donde se hace. Ordena las historias para que "
            "lo que un repo necesita de otro vaya antes (por ejemplo, el endpoint del back antes "
            "de la pantalla del front): cada historia espera a que la anterior esté integrada. "
            "Si un cambio solo tiene sentido completo en varios repos a la vez (un campo que "
            "viaja de la base de datos a la pantalla), la historia los nombra todos: "
            "`**Repo**: api, front`; un agente los trabaja juntos y se integran juntos.")


# --- preguntas -------------------------------------------------------------------------------

class Question(BaseModel):
    question: str
    options: list[str] = Field(min_length=2, max_length=5)
    recommended: int | None = None

    @model_validator(mode="after")
    def _in_range(self):
        if self.recommended is not None and not 0 <= self.recommended < len(self.options):
            raise ValueError("recommended fuera de rango")
        return self


_FENCE = "```umbra-question"


def parse_question(text: str) -> tuple[str, Question | None]:
    """(texto sin el bloque, pregunta). Bloque ausente o inválido → texto completo y None."""
    start = text.rfind(_FENCE)
    if start < 0:
        return text, None
    end = text.find("```", start + len(_FENCE))
    if end < 0:
        return text, None
    try:
        q = Question.model_validate(json.loads(text[start + len(_FENCE):end]))
    except (ValueError, ValidationError):
        return text, None
    return (text[:start] + text[end + 3:]).strip(), q


# --- costo y límite --------------------------------------------------------------------------

def turn_cost(total: Decimal, cost_seen: Decimal) -> Decimal:
    return max(total - cost_seen, Decimal(0))


def max_cost_usd(config: dict, section: str = "spec", default: Decimal = DEFAULT_MAX_COST
                 ) -> Decimal:
    raw = config.get(section, {}).get("max_cost_usd", default)
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        value = Decimal(0)
    if isinstance(raw, bool) or not value.is_finite() or value <= 0:
        raise ValueError(
            f"[{section}] max_cost_usd debe ser un número mayor que 0 en .umbra/project.toml")
    return value


def spent(conn, conv_id: str) -> Decimal:
    rows = conn.execute("SELECT cost FROM usage WHERE conversation_id = ?", (conv_id,))
    return sum((Decimal(r["cost"]) for r in rows), Decimal(0))


def over_budget(conn, conv_id: str, max_cost: Decimal) -> bool:
    return spent(conn, conv_id) >= max_cost


def record_turn(conn, conv_id: str, total: Decimal) -> Decimal:
    """Guarda el costo del turno (acumulado − cost_seen) y el nuevo cost_seen; lo devuelve."""
    seen = Decimal(conn.execute(
        "SELECT cost_seen FROM conversation WHERE id = ?", (conv_id,)).fetchone()["cost_seen"])
    cost = turn_cost(total, seen)  # acumulado menor = sesión nueva: diferencia 0, se reinicia
    with conn:
        conn.execute(
            "INSERT INTO usage (id, agent, cost, invocation_id, conversation_id)"
            " VALUES (?, 'claude', ?, ?, ?)", (new_id(), str(cost), new_id(), conv_id))
        conn.execute("UPDATE conversation SET cost_seen = ?, updated_at = ? WHERE id = ?",
                     (str(total), now(), conv_id))
    return cost


# --- archivos de otra fase -------------------------------------------------------------------

def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    files = [p for p in (root / "specs").rglob("*") if p.is_file()]
    files.append(root / FEATURE_JSON)
    out = {}
    for p in files:
        if p.is_file():
            st = p.stat()
            out[p.relative_to(root).as_posix()] = (st.st_mtime_ns, st.st_size)
    return out


def stray_files(root: Path, before: dict, phase: str) -> tuple[list[str], list[str]]:
    """(nuevos, modificados) tras el turno que no corresponden a la fase."""
    new, changed = [], []
    for rel, sig in snapshot(root).items():
        if rel == FEATURE_JSON or before.get(rel) == sig:
            continue
        if any(fnmatch(rel, g) for g in WRITES.get(phase, [])):
            continue
        (changed if rel in before else new).append(rel)
    return new, changed


def purge_stray(root: Path, before: dict, phase: str) -> list[str]:
    """Borra los archivos nuevos de otra fase (solo bajo specs/) y avisa; los modificados solo
    se avisan (sin git no hay cómo restaurarlos)."""
    new, changed = stray_files(root, before, phase)
    warnings = []
    for rel in new:
        if rel.startswith("specs/"):
            (root / rel).unlink()
            warnings.append(f"Se borró {rel}: no corresponde a la fase {phase}.")
    warnings += [f"{rel} cambió y no corresponde a la fase {phase}." for rel in changed]
    return warnings


# --- conversación ----------------------------------------------------------------------------

def new_conversation(conn, idea: str, origin: str = "cli") -> str:
    cid, ts = new_id(), now()
    with conn:
        conn.execute(
            "INSERT INTO conversation (id, idea, phase, origin, created_at, updated_at)"
            " VALUES (?, ?, 'specify', ?, ?, ?)", (cid, idea, origin, ts, ts))
    return cid


def phase_of(conn, conv_id: str) -> str:
    return conn.execute("SELECT phase FROM conversation WHERE id = ?",
                        (conv_id,)).fetchone()["phase"]


def advance(conn, conv_id: str, event: str = "next") -> str:
    phase = next_phase(phase_of(conn, conv_id), event)
    with conn:
        conn.execute("UPDATE conversation SET phase = ?, updated_at = ? WHERE id = ?",
                     (phase, now(), conv_id))
    return phase


@dataclass
class TurnResult:
    text: str = ""
    question: Question | None = None
    cost: Decimal = Decimal(0)
    session_id: str | None = None
    error: bool = False
    paused: bool = False
    warnings: list[str] = field(default_factory=list)


def run_turn(conn, root: Path, conv_id: str, stream: Stream, message: str, max_cost: Decimal,
             on_event: Callable[[Event], None] | None = None) -> TurnResult:
    """Un turno: envía, lee eventos, registra session_id y costo, limpia archivos ajenos y
    pausa si se superó el límite (la fase no cambia)."""
    res = TurnResult()
    if over_budget(conn, conv_id, max_cost):
        res.paused = True
        res.warnings.append(_pause_msg(max_cost))
        return res
    phase = phase_of(conn, conv_id)
    before = snapshot(root)
    stream.send(message)
    chunks, ended = [], False
    for ev in stream.events():
        if on_event:
            on_event(ev)
        if isinstance(ev, Init):
            res.session_id = ev.session_id
            with conn:
                conn.execute("UPDATE conversation SET session_id = ?, updated_at = ?"
                             " WHERE id = ?", (ev.session_id, now(), conv_id))
        elif isinstance(ev, TextDelta):
            chunks.append(ev.text)
        elif isinstance(ev, TurnEnd):
            ended = True
            res.cost = record_turn(conn, conv_id, ev.total_cost)
            res.error = ev.is_error
            chunks = [ev.text] if ev.text else chunks
            break
    if not ended:
        res.error = True
        res.warnings.append("claude terminó sin cerrar el turno.")
    res.text, res.question = parse_question("".join(chunks))
    res.warnings += purge_stray(root, before, phase)
    if over_budget(conn, conv_id, max_cost):
        res.paused = True
        res.warnings.append(_pause_msg(max_cost))
    return res


def spec_dir_from_feature(root: Path) -> Path | None:
    """Carpeta de la spec que dejó `speckit-specify` en `.specify/feature.json`."""
    try:
        folder = json.loads((root / FEATURE_JSON).read_text(encoding="utf-8"))["feature_directory"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return Path(folder) if isinstance(folder, str) and folder else None


def set_spec_dir(conn, conv_id: str, spec_dir: Path) -> None:
    with conn:
        conn.execute("UPDATE conversation SET spec_dir = ?, updated_at = ? WHERE id = ?",
                     (spec_dir.as_posix(), now(), conv_id))


def _pause_msg(max_cost: Decimal) -> str:
    return (f"Se superó el límite de ${max_cost} para esta conversación; queda en pausa. "
            "Sube [spec] max_cost_usd en .umbra/project.toml para continuar.")
