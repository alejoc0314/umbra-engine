"""Memoria del repo: lo que la persona decidió se destila en `.umbra/aprendido.md`.

Se genera íntegramente desde los eventos (`finding.decided`, `task.answered`,
`policy.allowed`); nunca se edita a mano. Los agentes lo reciben en `project_notes`."""

import json
import re
import sqlite3
from pathlib import Path

FILE = "aprendido.md"
LEARNED_CHARS = 4000
CONTEXT_CHARS = 6000
SECTIONS = (("waived", "Revisión: no pedir"), ("deferred", "Para después"),
            ("answers", "Respuestas dadas"), ("allowed", "Rutas autorizadas"))
HEADER = ("# Aprendido en este repo\n\n"
          "Archivo generado por umbra a partir de las decisiones de la persona responsable; "
          "no lo edites a mano (`umbra memory rebuild` lo regenera).\n")
_LOCATION = re.compile(r"\s*\([^()\s]+:\d+\)")


def normalize(text: str) -> str:
    """Texto comparable: minúsculas, sin `(archivo:línea)`, espacios colapsados, sin puntuación
    final."""
    text = _LOCATION.sub("", text.lower())
    return " ".join(text.split()).rstrip(".!?;:,")


def entries(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Decisiones registradas, agrupadas por sección y de más reciente a más antigua."""
    out: dict[str, list[dict]] = {key: [] for key, _ in SECTIONS}
    rows = conn.execute(
        "SELECT e.id, e.run_id, e.type, e.payload, e.created_at, t.number FROM event e"
        " LEFT JOIN run r ON r.id = e.run_id LEFT JOIN task t ON t.id = r.task_id"
        " WHERE e.type IN ('finding.decided', 'task.answered', 'policy.allowed')"
        " ORDER BY e.id DESC").fetchall()
    for r in rows:
        p = json.loads(r["payload"])
        base = {"task": r["number"], "date": r["created_at"][:10]}
        if r["type"] == "finding.decided":
            reason = p.get("reason") or ""
            if p.get("decision") == "deferred":
                reason = ", ".join(x for x in (reason, f"tarea {p['task']}" if p.get("task")
                                               else "") if x)
            key = "deferred" if p.get("decision") == "deferred" else "waived"
            out[key].append(base | {"text": p.get("message", ""), "reason": reason})
        elif r["type"] == "task.answered":
            out["answers"].append(base | {"text": _question(conn, r["run_id"], r["id"]),
                                          "reason": p.get("answer", "")})
        else:
            out["allowed"].append(base | {"task": p.get("number", r["number"]),
                                          "text": ", ".join(p.get("paths", [])),
                                          "reason": "autorizado cambiarlas"})
    return out


def _question(conn: sqlite3.Connection, run_id: str | None, before: int) -> str:
    row = conn.execute(
        "SELECT payload FROM event WHERE run_id = ? AND type = 'run.blocked' AND id < ?"
        " ORDER BY id DESC LIMIT 1", (run_id, before)).fetchone()
    if not row:
        return "(pregunta no registrada)"
    p = json.loads(row["payload"])
    if p.get("code") != "agent_questions":
        return "(pregunta no registrada)"
    questions = p.get("details", {}).get("questions") or []
    return " ".join(questions) if questions else (p.get("reason") or "(pregunta no registrada)")


def render(groups: dict[str, list[dict]]) -> str:
    parts = [HEADER]
    for key, title in SECTIONS:
        parts.append(f"\n## {title}\n")
        items = groups.get(key) or []
        if not items:
            parts.append("\n(nada todavía)\n")
            continue
        parts.append("\n" + "".join(
            f"- {' '.join(str(e['text']).split())} (tarea {e['task'] or '?'}, {e['date']}, "
            f"{' '.join(str(e['reason']).split())})\n" for e in items))
    return "".join(parts)


def rebuild(conn: sqlite3.Connection, udir: Path) -> Path:
    path = udir / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(entries(conn)), encoding="utf-8", newline="\n")
    return path


def load(udir: Path, limit: int = LEARNED_CHARS) -> str:
    """El archivo acotado a `limit` caracteres, recortando por líneas completas."""
    path = udir / FILE
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        return text
    cut = text.rfind("\n", 0, limit + 1)
    return text[:cut + 1] if cut > 0 else ""


def decided_messages(conn: sqlite3.Connection) -> set[str]:
    """Hallazgos (normalizados) que la persona ya decidió en cualquier tarea del repo."""
    return {normalize(r[0]) for r in conn.execute(
        "SELECT message FROM finding WHERE status IN ('waived', 'deferred')")}


def project_notes(root: Path, udir: Path) -> str | None:
    """Lo que todo agente recibe: el mapa del repo (`CONTEXT.md`) y lo aprendido."""
    blocks = []
    context = root / "CONTEXT.md"
    if context.is_file():
        blocks.append("# Mapa del repositorio\n\n"
                      + context.read_text(encoding="utf-8", errors="replace")[:CONTEXT_CHARS]
                      .rstrip())  # escrito a mano en otra codificación: no debe frenar nada
    if learned := load(udir).strip():
        blocks.append("# Aprendido en este repo\n\n" + learned)
    return "\n\n".join(blocks) if blocks else None
