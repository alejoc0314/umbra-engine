"""`umbra plan`: guardar la spec como versión inmutable y crear tareas propuestas en borrador."""

import hashlib
import json
import sqlite3
from pathlib import Path

from umbra.actions import git
from umbra.adapters import get_adapter
from umbra.adapters.base import AgentRun
from umbra.contracts.envelope import Envelope, TaskInfo
from umbra.contracts.plan import PlanOutput
from umbra.management.dag import CycleError, topo_order
from umbra.unified import config as cfg
from umbra.unified.events import add_event
from umbra.unified.store import new_id, now, to_cost


class PlanningError(Exception):
    pass


def save_spec(conn: sqlite3.Connection, body: str, author: str,
              dir: str | None = None) -> tuple[str, int, bool]:
    """Devuelve (spec_id, versión, creada). Mismo contenido = misma versión."""
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    row = conn.execute("SELECT id, version FROM spec WHERE content_hash = ?",
                       (digest,)).fetchone()
    if row:
        if dir:
            conn.execute("UPDATE spec SET dir = ? WHERE id = ? AND dir IS NULL",
                         (dir, row["id"]))
        return row["id"], row["version"], False
    version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM spec").fetchone()[0]
    spec_id = new_id()
    conn.execute("INSERT INTO spec (id, version, content_hash, body, author, created_at, dir)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (spec_id, version, digest, body, author, now(), dir))
    return spec_id, version, True


def propose(root: Path, udir: Path, conn, body: str, version: int,
            profile_name: str = "proposer") -> PlanOutput:
    profile = cfg.load_profile(udir, profile_name)
    existing = [f"#{r['number']} {r['title']} ({r['status']})"
                for r in conn.execute("SELECT number, title, status FROM task ORDER BY number")]
    invocation = new_id()
    envelope = Envelope(run_id=f"spec-v{version}", stage="propose", attempt_id=invocation,
                        input_sha=git.head(root),
                        task=TaskInfo(number=0, title=f"Proponer tareas para la spec v{version}",
                                      description=body),
                        feedback=existing)
    req = AgentRun(envelope, profile, root, udir / "artifacts" / f"{invocation}-propose.jsonl",
                   output_model=PlanOutput)
    result = get_adapter(profile.agent, udir).run(req)
    conn.execute(
        "INSERT INTO usage (id, agent, model, input_tokens, output_tokens, cost, estimated,"
        " invocation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (new_id(), profile.agent, result.model, result.input_tokens, result.output_tokens,
         to_cost(result.cost), int(result.estimated), invocation))
    if not result.ok:
        raise PlanningError(result.error or "el proponente falló")
    return result.output


def insert_proposals(conn, spec_id: str | None, plan: PlanOutput,
                     trace: list[dict] | None = None,
                     extra_deps: dict[int, str] | None = None,
                     spec: tuple[str, str, str] | None = None) -> list[int]:
    """Valida el DAG (existentes + propuestas) e inserta todo o nada.

    `spec` (opcional): (body, author, dir); guarda la spec dentro de la misma transacción.

    `trace` (opcional, paralela a plan.tasks): {spec_dir, story, requirements, story_hash}.
    `extra_deps` (opcional): índice de tarea propuesta → id de una tarea ya existente.
    """
    n = len(plan.tasks)
    for i, t in enumerate(plan.tasks):
        bad = [d for d in t.depends_on if d == i or not 0 <= d < n]
        if bad:
            raise PlanningError(f"la tarea propuesta {i} depende de índices inválidos: {bad}")
    existing_ids = [r[0] for r in conn.execute("SELECT id FROM task")]
    edges = [tuple(r) for r in conn.execute("SELECT task_id, depends_on_id FROM dependency")]
    edges += [(f"new{i}", f"new{d}") for i, t in enumerate(plan.tasks) for d in t.depends_on]
    edges += [(f"new{i}", dep) for i, dep in (extra_deps or {}).items()]
    try:
        topo_order(existing_ids + [f"new{i}" for i in range(n)], edges)
    except CycleError as e:
        raise PlanningError(str(e)) from e

    conn.execute("BEGIN IMMEDIATE")
    try:
        if spec:
            spec_id = save_spec(conn, *spec)[0]
        start = conn.execute("SELECT COALESCE(MAX(number), 0) FROM task").fetchone()[0]
        ids = []
        for i, t in enumerate(plan.tasks):
            ids.append(new_id())
            conn.execute(
                "INSERT INTO task (id, number, title, about, description, acceptance, scope,"
                " priority, status, spec_id, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)",
                (ids[i], start + i + 1, t.title, t.about, t.description,
                 json.dumps(t.acceptance, ensure_ascii=False), json.dumps(t.scope),
                 t.priority, spec_id, now(), now()))
            if trace:
                tr = trace[i]
                conn.execute(
                    "UPDATE task SET spec_dir = ?, story = ?, requirements = ?, story_hash = ?"
                    " WHERE id = ?",
                    (tr["spec_dir"], tr["story"],
                     json.dumps(tr.get("requirements", [])), tr.get("story_hash"), ids[i]))
        for i, t in enumerate(plan.tasks):
            for d in t.depends_on:
                conn.execute("INSERT INTO dependency (task_id, depends_on_id) VALUES (?, ?)",
                             (ids[i], ids[d]))
        for i, dep in (extra_deps or {}).items():
            conn.execute("INSERT INTO dependency (task_id, depends_on_id) VALUES (?, ?)",
                         (ids[i], dep))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    numbers = list(range(start + 1, start + n + 1))
    add_event(conn, None, "plan.proposed", "cli", spec=spec_id, tasks=numbers)
    return numbers


def pending_dependencies(conn, task_id: str) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT t.number FROM dependency d JOIN task t ON t.id = d.depends_on_id"
        " WHERE d.task_id = ? AND t.status != 'done' ORDER BY t.number", (task_id,))]


def would_cycle(conn, task_id: str, depends_on_id: str) -> bool:
    ids = [r[0] for r in conn.execute("SELECT id FROM task")]
    edges = [tuple(r) for r in conn.execute("SELECT task_id, depends_on_id FROM dependency")]
    try:
        topo_order(ids, [*edges, (task_id, depends_on_id)])
    except CycleError:
        return True
    return False
