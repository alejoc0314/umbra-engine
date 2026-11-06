"""Operaciones sobre tareas, compartidas por la CLI, `umbra watch` y el chat.

Cada función hace exactamente lo que hace el comando del mismo nombre. Los errores se lanzan
como OpError (mensaje para la persona + código de salida); cada interfaz decide cómo mostrarlos.
"""

import getpass
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from umbra.actions import commands, git, policy
from umbra.blocks import process, worktree
from umbra.contracts.plan import PlanOutput, ProposedTask
from umbra.management import memory, planning, specfile
from umbra.management.planning import pending_dependencies
from umbra.routines import engine as eng
from umbra.routines import parts, worker
from umbra.routines.parts import fingerprint
from umbra.unified import config as cfg
from umbra.unified import explain as ex
from umbra.unified import project
from umbra.unified.events import add_event
from umbra.unified.store import ACTIVE_RUN_STATES, new_id, now, open_store
from umbra.unified.store import _unpriced as store_unpriced

DEFAULT_ROUTINE = "feature"
REPO_AGENT_CONFIG = (".claude/settings.json", ".claude/settings.local.json", ".mcp.json")


class OpError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


@dataclass
class Ctx:
    root: Path
    udir: Path
    conn: object
    config: dict

    @property
    def members(self) -> dict[str, Path]:
        """Repos del espacio de trabajo (spec 032); vacío en un proyecto de un repo."""
        return project.members(self.root, self.config)


def load(start: Path | None = None) -> Ctx:
    try:
        root, udir = project.umbra_dir(start or Path.cwd())
    except (project.NotARepo, project.NotInitialized) as e:
        raise OpError(str(e), 2) from e
    return Ctx(root, udir, open_store(udir), project.load_project(root))


def interactive() -> bool:
    """Aprobar o rechazar exige una persona en una terminal (no scripts ni el chat)."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def actor() -> str:
    return getpass.getuser()


def engine(ctx: Ctx, origin: str = "cli", run_id: str | None = None) -> eng.Engine:
    """Con `run_id`, el engine del repo de esa ejecución (en un espacio, el de su tarea)."""
    if run_id:
        return eng.for_run(ctx.root, ctx.udir, ctx.conn, ctx.config, run_id, origin=origin)
    return eng.Engine(ctx.root, ctx.udir, ctx.conn, ctx.config, origin=origin)


def task_repos(task) -> list[str]:
    return json.loads(task["repos"] or "[]")


def member(ctx: Ctx, name: str) -> tuple[Path, dict]:
    """(raíz, configuración) de un repo del espacio por su nombre."""
    check_repos(ctx, [name], f"«{name}»")
    try:
        return ctx.members[name], project.repo_config(ctx.config, ctx.members[name])
    except project.NotInitialized as e:
        raise OpError(str(e), 2) from e


def run_parts(ctx: Ctx, run_row) -> list:
    """Lo de la ejecución en cada repo (una parte si es de un solo repo)."""
    e = engine(ctx, run_id=run_row["id"])
    return e.parts(e.run_row(run_row["id"]))


def run_diff(ctx: Ctx, run_row) -> tuple[str, str]:
    """(numstat, patch) de una ejecución, en el repo (o los repos) de su tarea."""
    ps = run_parts(ctx, run_row)
    return parts.numstat(ps), parts.diff(ps)


def diff_stat(ctx: Ctx, run_row) -> str:
    return parts.diff_stat(run_parts(ctx, run_row))


def check_repos(ctx: Ctx, repos: list[str], what: str) -> None:
    """En un espacio, cada tarea dice en qué repo se hace; fuera de un espacio, ninguna."""
    members = ctx.members
    if not members:
        if repos:
            raise OpError(f"{what} declara repos ({', '.join(repos)}) pero este proyecto es un "
                          "solo repo, no un espacio de trabajo", 2)
        return
    valid = ", ".join(members)
    if not repos:
        raise OpError(f"{what} no dice en qué repo del espacio se hace (repos: {valid})", 2)
    if bad := [r for r in repos if r not in members]:
        raise OpError(f"{what} nombra repos que no están en el espacio: {', '.join(bad)} "
                      f"(repos: {valid})", 2)


def repo_targets(ctx: Ctx, task) -> dict[str, tuple[Path, dict]]:
    """Los repos donde trabaja la tarea: {nombre: (raíz, configuración)}, en el orden del
    espacio; en un proyecto de un repo (o una tarea de un solo repo), {"": ...}."""
    repos = task_repos(task) if ctx.members else []
    if len(repos) < 2:
        return {"": repo_of(ctx, task)}
    check_repos(ctx, repos, f"la tarea {task['number']}")
    return {r: member(ctx, r) for r in ctx.members if r in repos}


def repo_of(ctx: Ctx, task) -> tuple[Path, dict]:
    """Repo donde trabaja la tarea y su configuración; en un proyecto de un repo, el proyecto."""
    if not ctx.members:
        return ctx.root, ctx.config
    repos = task_repos(task)
    check_repos(ctx, repos, f"la tarea {task['number']}")
    if len(repos) > 1:
        return ctx.root, ctx.config  # tarea entre repos (spec 033): trabaja sobre el espacio
    return member(ctx, repos[0])


def set_task_repos(ctx: Ctx, number: int, repos: list[str], origin: str = "cli") -> list[str]:
    task = task_row(ctx, number)
    check_repos(ctx, repos, f"la tarea {number}")
    if task["status"] not in ("draft", "accepted") or ctx.conn.execute(
            "SELECT 1 FROM run WHERE task_id = ?", (task["id"],)).fetchone():
        raise OpError(f"la tarea {number} ya se ejecutó: su repo no se puede cambiar")
    ctx.conn.execute("UPDATE task SET repos = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(repos), now(), task["id"]))
    add_event(ctx.conn, None, "task.repos", origin, task=number, repos=repos)
    return repos


def task_row(ctx: Ctx, number: int):
    row = ctx.conn.execute("SELECT * FROM task WHERE number = ?", (number,)).fetchone()
    if not row:
        raise OpError(f"no existe la tarea {number}", 2)
    return row


def latest_run(ctx: Ctx, number: int):
    row = ctx.conn.execute(
        "SELECT r.* FROM run r JOIN task t ON t.id = r.task_id WHERE t.number = ?"
        " ORDER BY r.created_at DESC LIMIT 1", (number,)).fetchone()
    if not row:
        raise OpError(f"la tarea {number} no tiene ejecuciones", 2)
    return row


def dispatch(root: Path, foreground: bool) -> None:
    ensure_bridge(root)
    if foreground:
        worker.work(root)
    else:
        worker.spawn(root)


def ensure_bridge(root: Path) -> None:
    """Con Telegram configurado, un puente (uno para todos tus repos) lee el teléfono."""
    from umbra.blocks import telegram
    from umbra.routines import bridge
    try:
        if telegram.settings(project.load_project(root)) and not bridge.alive():
            bridge.spawn(root)
    except Exception:  # ponytail: el puente es un extra; nunca frena encolar una tarea
        pass


# ---------- tareas ----------
def set_task_status(ctx: Ctx, numbers: list[int], status: str, from_: tuple[str, ...],
                    origin: str = "cli") -> list[int]:
    rows = [task_row(ctx, n) for n in numbers]
    for t in rows:  # se valida todo antes de cambiar nada
        if t["status"] not in from_:
            raise OpError(f"la tarea {t['number']} está en {t['status']}")
    for t in rows:
        ctx.conn.execute("UPDATE task SET status = ?, revision = revision + 1, updated_at = ?"
                         " WHERE id = ?", (status, now(), t["id"]))
        add_event(ctx.conn, None, f"task.{status}", origin, number=t["number"])
    return [t["number"] for t in rows]


def accept(ctx: Ctx, numbers: list[int], origin: str = "cli") -> list[int]:
    return set_task_status(ctx, numbers, "accepted", ("draft",), origin)


def drop(ctx: Ctx, numbers: list[int], origin: str = "cli") -> list[int]:
    return set_task_status(ctx, numbers, "dropped", ("draft", "accepted"), origin)


def _spec_stories(ctx: Ctx, spec_dir: Path):
    """(carpeta relativa, cuerpo de spec.md, historias, pasos de tasks.md)."""
    folder = spec_dir if spec_dir.is_absolute() else ctx.root / spec_dir
    spec_file = folder / "spec.md"
    if not spec_file.is_file():
        raise OpError(f"no encuentro spec.md en {spec_dir}; indica la carpeta de la spec", 2)
    body = spec_file.read_text(encoding="utf-8")
    stories = specfile.parse_stories(body)
    if not stories:
        raise OpError("la spec no tiene historias de usuario; usa `umbra plan <spec>` para que "
                      "un agente proponga las tareas", 2)
    try:
        rel = folder.resolve().relative_to(ctx.root.resolve()).as_posix()
    except ValueError:
        raise OpError(f"la carpeta de la spec debe estar dentro del repositorio: {spec_dir}",
                      2) from None
    if rel in ("", "."):
        raise OpError("la spec no puede estar en la raíz del repositorio; muévela a una "
                      "carpeta propia (por ejemplo specs/001-nombre)", 2)
    tasks_file = folder / "tasks.md"
    steps = (specfile.parse_steps(tasks_file.read_text(encoding="utf-8"))
             if tasks_file.is_file() else {})
    return rel, body, stories, steps


def _proposed(s, steps: dict, rel: str, depends_on: list[int]) -> ProposedTask:
    mine = steps.get(s.id, [])
    desc = s.text + (("\n\nPasos:\n" + "\n".join(mine)) if mine else "")
    desc += f"\n\nPlan técnico: {rel}/plan.md"
    return ProposedTask(
        title=f"Historia {s.id[2:]}: {s.title}", about=specfile.story_about(s.text),
        description=desc, acceptance=s.scenarios, scope=specfile.step_paths(mine),
        priority=s.priority, depends_on=depends_on, repos=s.repos)


def spec_tasks(ctx: Ctx, spec_dir: Path, origin: str = "cli") -> dict:
    """Crea una tarea en borrador por historia de la spec (sin duplicar las ya creadas)."""
    rel, body, stories, steps = _spec_stories(ctx, spec_dir)
    have = {r["story"]: r["number"] for r in ctx.conn.execute(
        "SELECT story, number FROM task WHERE spec_dir = ?", (rel,))}
    new = sorted((s for s in stories if s.id not in have), key=lambda s: (s.priority, s.id))
    existing = sorted(have.values())
    if not new:
        return {"spec_dir": rel, "created": [], "existing": existing}
    for s in new:  # en un espacio, cada historia dice su repo; se valida todo antes de crear nada
        check_repos(ctx, s.repos, f"la historia {s.id[2:]} ({s.title})")

    proposed, trace = [], []
    for i, s in enumerate(new):
        proposed.append(_proposed(s, steps, rel, [i - 1] if i else []))
        trace.append({"spec_dir": rel, "story": s.id, "requirements": s.requirements,
                      "story_hash": s.story_hash})
    last = ctx.conn.execute(
        "SELECT id FROM task WHERE spec_dir = ? ORDER BY number DESC LIMIT 1", (rel,)).fetchone()
    try:
        created = planning.insert_proposals(
            ctx.conn, None, PlanOutput(tasks=proposed, questions=[]), trace,
            {0: last["id"]} if last else None, (body, getpass.getuser(), rel))
    except (planning.PlanningError, sqlite3.IntegrityError) as e:
        raise OpError(f"no se pudieron crear las tareas: {e}", 4) from e
    add_event(ctx.conn, None, "spec.tasks", origin, spec_dir=rel, tasks=created)
    return {"spec_dir": rel, "created": created, "existing": existing}


def misaligned(ctx: Ctx, spec_dir: Path) -> list[dict]:
    """Tareas cuya historia cambió en spec.md desde que se crearon (compara `story_hash`).

    `updatable`: solo borrador o aceptada y sin ejecución activa; si no, `reason` dice por qué.
    """
    rel, _, stories, steps = _spec_stories(ctx, spec_dir)
    marks =",".join("?" * len(ACTIVE_RUN_STATES))
    out = []
    for s in stories:
        t = ctx.conn.execute("SELECT * FROM task WHERE spec_dir = ? AND story = ?",
                             (rel, s.id)).fetchone()
        if not t or t["story_hash"] == s.story_hash:
            continue
        running = ctx.conn.execute(
            f"SELECT 1 FROM run WHERE task_id = ? AND status IN ({marks})",
            (t["id"], *ACTIVE_RUN_STATES)).fetchone()
        reason = ("tiene una ejecución activa" if running else
                  f"está en {t['status']}" if t["status"] not in ("draft", "accepted") else "")
        p = _proposed(s, steps, rel, [])
        changes = {}
        for f in ("title", "about", "description", "acceptance", "scope"):
            old = t[f]
            if f in ("acceptance", "scope"):
                old = json.loads(old) if old else []
            new = getattr(p, f)
            if old != new:
                changes[f] = {"old": old, "new": new}
        out.append({"number": t["number"], "story": s.id, "title": t["title"],
                    "new_title": p.title, "status": t["status"], "changes": changes,
                    "updatable": not reason, "reason": reason})
    return sorted(out, key=lambda m: m["number"])


def spec_progress(ctx: Ctx) -> list[dict]:
    """Por spec: fase, historias hechas/total, desalineadas y costo (conversación + intentos)."""
    from umbra.unified.store import to_cost
    dirs = {r[0] for r in ctx.conn.execute(
        "SELECT spec_dir FROM task WHERE spec_dir IS NOT NULL UNION"
        " SELECT spec_dir FROM conversation WHERE spec_dir IS NOT NULL")}
    out = []
    for d in sorted(dirs):
        conv = ctx.conn.execute("SELECT id, phase FROM conversation WHERE spec_dir = ?"
                                " ORDER BY updated_at DESC", (d,)).fetchone()
        tasks = ctx.conn.execute("SELECT status FROM task WHERE spec_dir = ?", (d,)).fetchall()
        total = len(tasks)
        spec_file = ctx.root / d / "spec.md"
        if spec_file.is_file():
            total = max(total, len(specfile.parse_stories(spec_file.read_text(encoding="utf-8"))))
        try:
            stale = [{"story": m["story"], "number": m["number"]}
                     for m in misaligned(ctx, Path(d))]
        except OpError:
            stale = []
        cost, unpriced = Decimal(0), 0
        for row in ctx.conn.execute(
                "SELECT u.cost, u.estimated, u.input_tokens, u.output_tokens FROM usage u"
                " LEFT JOIN attempt a ON a.id = u.attempt_id LEFT JOIN run r ON r.id = a.run_id"
                " LEFT JOIN task t ON t.id = r.task_id"
                " WHERE t.spec_dir = ? OR u.conversation_id IN"
                " (SELECT id FROM conversation WHERE spec_dir = ?)", (d, d)):
            cost += Decimal(row["cost"])
            unpriced += store_unpriced(row)
        out.append({"spec_dir": d, "pr": spec_pr(ctx, d),
                    "phase": conv["phase"] if conv else None,
                    "conversation": conv["id"] if conv else None, "stories_total": total,
                    "stories_done": sum(t["status"] == "done" for t in tasks),
                    "misaligned": stale, "cost": to_cost(cost), "unpriced_tokens": unpriced})
    return out


def spec_open_conversation(ctx: Ctx):
    """La conversación abierta más reciente, o None."""
    try:
        return spec_resume_target(ctx, None)
    except OpError:
        return None


def spec_tasks_update(ctx: Ctx, spec_dir: Path, origin: str = "cli") -> dict:
    """Pone al día las tareas desalineadas que se pueden tocar; las demás se omiten."""
    rel, _, stories, steps = _spec_stories(ctx, spec_dir)
    by_id = {s.id: s for s in stories}
    stale = misaligned(ctx, spec_dir)
    for m in stale:
        if not m["updatable"]:
            continue
        s = by_id[m["story"]]
        p = _proposed(s, steps, rel, [])
        ctx.conn.execute(
            "UPDATE task SET title = ?, about = ?, description = ?, acceptance = ?, scope = ?,"
            " requirements = ?, story_hash = ?, revision = revision + 1, updated_at = ?"
            " WHERE spec_dir = ? AND story = ?",
            (p.title, p.about, p.description, json.dumps(p.acceptance, ensure_ascii=False),
             json.dumps(p.scope), json.dumps(s.requirements), s.story_hash, now(), rel, s.id))
        add_event(ctx.conn, None, "spec.tasks.updated", origin, number=m["number"])
    return {"updated": [m["number"] for m in stale if m["updatable"]],
            "skipped": [{"number": m["number"], "reason": m["reason"]}
                        for m in stale if not m["updatable"]]}


# ---------- ejecuciones ----------
def _trust(root: Path, config: dict, trust_repo_config: bool) -> None:
    risky = [p for p in REPO_AGENT_CONFIG if (root / p).exists()]
    trusted = config.get("policy", {}).get("trust_repo_agent_config", False)
    if risky and not (trusted or trust_repo_config):
        raise OpError(f"el repo {root.name} trae configuración de agentes que Claude Code cargará"
                      f" sin preguntar: {', '.join(risky)}. Revísala y usa --trust-repo-config o "
                      "[policy] trust_repo_agent_config = true", 5)


def _remote_base(root: Path, base_branch: str) -> str:
    sha = git.remote_base(root, base_branch)  # lo integrado en GitHub, no la copia local
    if sha is None:
        raise OpError(f"la rama base '{base_branch}' no existe o no tiene commits: haz un commit "
                      f"inicial (o ajusta base_branch en {root.name}/.umbra/project.toml)", 2)
    return sha


def spec_branch(ctx: Ctx, task) -> str | None:
    """Rama de la spec de la tarea (`spec/<carpeta>`), si trabaja dentro de una."""
    if task["spec_dir"] and ctx.config.get("spec", {}).get("branch", True):
        return f"spec/{Path(task['spec_dir']).name}"
    return None


def run(ctx: Ctx, numbers: list[int], routine: str | None = None, new: bool = False,
        trust_repo_config: bool = False, foreground: bool = False,
        origin: str = "cli", dispatch_worker: bool = True) -> list[dict]:
    routine_name = routine
    results = []
    for n in numbers:
        task = task_row(ctx, n)
        targets = repo_targets(ctx, task)  # {repo: (raíz, configuración)}; "" en un repo
        for root, config in targets.values():
            _trust(root, config, trust_repo_config)
        config = next(iter(targets.values()))[1]
        routine = routine_name or config.get("project", {}).get("default_routine",
                                                                DEFAULT_ROUTINE)
        try:
            cfg.load_routine(ctx.udir, routine)
        except cfg.ConfigError as e:
            raise OpError(str(e)) from e
        bases = {r: (c.get("project", {}).get("base_branch", "main"),
                     _remote_base(root, c.get("project", {}).get("base_branch", "main")))
                 for r, (root, c) in targets.items()}
        base_branch = next(iter(bases.values()))[0]
        if task["status"] != "accepted":
            raise OpError(f"la tarea {n} está en {task['status']}; solo se ejecutan tareas "
                          "aceptadas")
        if waiting := pending_dependencies(ctx.conn, task["id"]):
            raise OpError(f"la tarea {n} depende de tareas sin terminar: {waiting}")
        marks = ",".join("?" * len(ACTIVE_RUN_STATES))
        active = ctx.conn.execute(
            f"SELECT id, status FROM run WHERE task_id = ? AND status IN ({marks})",
            (task["id"], *ACTIVE_RUN_STATES)).fetchone()
        if active:
            results.append({"task": n, "run_id": active["id"], "status": active["status"],
                            "created": False})
            continue
        last = ctx.conn.execute("SELECT id, status FROM run WHERE task_id = ? ORDER BY"
                                " created_at DESC LIMIT 1", (task["id"],)).fetchone()
        if last and last["status"] in ("BLOCKED", "FAILED"):
            if not new:
                raise OpError(
                    f"la tarea {n} tiene una ejecución detenida. `umbra run` empezaría de cero y "
                    f"perdería el trabajo hecho. Para entender qué pasó: `umbra explain {n}`. "
                    f"Para continuar desde donde quedó: `umbra retry {n}`. Si de verdad quieres "
                    f"empezar de cero: `umbra run {n} --new`.", 4)
            eng.cancel(engine(ctx, origin, last["id"]), last["id"])  # cierra y limpia
        count = ctx.conn.execute("SELECT COUNT(*) FROM run WHERE task_id = ?",
                                 (task["id"],)).fetchone()[0]
        branch, shas = spec_branch(ctx, task), {}
        for r, (root, _) in targets.items():
            sha = bases[r][1]
            if branch:  # la tarea parte de (y se integra en) la rama de su spec
                sha = git.remote_base(root, branch)
                if sha is None:
                    git.run(root, "push", "-q", "origin", f"{bases[r][1]}:refs/heads/{branch}")
                    sha = bases[r][1]
            shas[r] = sha
        run_id = new_id()
        ctx.conn.execute(
            "INSERT INTO run (id, task_id, routine, status, base_sha, base_branch, branch,"
            " idempotency_key, created_at, updated_at)"
            " VALUES (?, ?, ?, 'QUEUED', ?, ?, ?, ?, ?, ?)",
            (run_id, task["id"], routine, fingerprint(shas), branch,
             f"{worktree.branch_name(n, task['title'])}-{run_id[:6]}",
             f"{task['id']}:{routine}:{count + 1}", now(), now()))
        if len(targets) > 1:  # tarea entre repos (spec 033): una parte por repo
            ctx.conn.executemany("INSERT INTO run_part (run_id, repo, base_sha) VALUES (?, ?, ?)",
                                 [(run_id, r, s) for r, s in shas.items()])
        add_event(ctx.conn, run_id, "run.queued", origin, task=n, routine=routine,
                  base_branch=branch or base_branch)
        results.append({"task": n, "run_id": run_id, "status": "QUEUED", "created": True})
    if dispatch_worker:
        dispatch(ctx.root, foreground)
    return results


def pause(ctx: Ctx, number: int, origin: str = "cli") -> str:
    run_row = latest_run(ctx, number)
    if not engine(ctx, origin).transition(run_row["id"], "PAUSED", ("QUEUED", "RUNNING")):
        raise OpError(f"no se puede pausar una ejecución en {run_row['status']}")
    add_event(ctx.conn, run_row["id"], "run.pause_requested", origin)
    return run_row["id"]


def resume(ctx: Ctx, number: int, foreground: bool = False, origin: str = "cli") -> str:
    run_row = latest_run(ctx, number)
    if not engine(ctx, origin).transition(run_row["id"], "QUEUED", ("PAUSED",)):
        raise OpError(f"solo se retoman ejecuciones pausadas (está en {run_row['status']})")
    add_event(ctx.conn, run_row["id"], "run.resumed", origin)
    dispatch(ctx.root, foreground)
    return run_row["id"]


def cancel(ctx: Ctx, number: int, origin: str = "cli") -> str:
    """Devuelve el estado anterior (RUNNING = se detendrá en el siguiente punto seguro)."""
    run_row = latest_run(ctx, number)
    try:
        eng.cancel(engine(ctx, origin, run_row["id"]), run_row["id"])
    except eng.ApprovalError as e:
        raise OpError(str(e)) from e
    return run_row["status"]


def retry_stages(ctx: Ctx, number: int) -> tuple[list[str], str]:
    """Etapas de la rutina y la sugerida para reintentar: donde quedó, salvo que la frenaran
    hallazgos (revisar otra vez el mismo código no cambia nada: toca corregir en BUILD)."""
    run_row = latest_run(ctx, number)
    stages = [s.name for s in cfg.load_routine(ctx.udir, run_row["routine"]).stages]
    blocked = _findings_block(ctx, run_row)
    if blocked and "build" in stages:
        stage = blocked["stage"]
        if not pending_findings(ctx, number) and stage in stages[:-1]:
            return stages, stages[stages.index(stage) + 1]  # todo decidido: sigue adelante
        return stages, "build"
    return stages, run_row["stage"] if run_row["stage"] in stages else stages[0]


def _findings_block(ctx: Ctx, run_row) -> dict | None:
    """El motivo del bloqueo si la ejecución se detuvo por hallazgos."""
    if run_row["status"] != "BLOCKED":
        return None
    row = ctx.conn.execute("SELECT payload FROM event WHERE run_id = ? AND type = 'run.blocked'"
                           " ORDER BY id DESC LIMIT 1", (run_row["id"],)).fetchone()
    payload = json.loads(row[0]) if row else {}
    return payload if payload.get("code") == "findings" else None


def open_findings(ctx: Ctx, number: int) -> list[dict]:
    """Todos los hallazgos abiertos de la última ejecución (también los que no frenan)."""
    run_row = latest_run(ctx, number)
    return [dict(r) for r in ctx.conn.execute(
        "SELECT f.id, f.severity, f.message, f.file, f.line, a.stage FROM finding f"
        " JOIN attempt a ON a.id = f.attempt_id WHERE a.run_id = ? AND f.status = 'open'"
        " ORDER BY a.started_at, f.rowid", (run_row["id"],))]


def pending_findings(ctx: Ctx, number: int) -> list[dict]:
    """Hallazgos que frenaron la ejecución y nadie ha decidido todavía."""
    run_row = latest_run(ctx, number)
    blocked = _findings_block(ctx, run_row)
    if not blocked:
        return []
    stage = blocked["stage"]
    routine = cfg.load_routine(ctx.udir, run_row["routine"])
    block_on = next((s.block_on for s in routine.stages if s.name == stage), "high")
    attempt = ctx.conn.execute(
        "SELECT id FROM attempt WHERE run_id = ? AND stage = ? AND status = 'findings'"
        " ORDER BY started_at DESC LIMIT 1", (run_row["id"], stage)).fetchone()
    if not attempt:
        return []
    return [dict(r) | {"stage": stage} for r in ctx.conn.execute(
        "SELECT id, severity, message, file, line FROM finding WHERE attempt_id = ?"
        " AND status = 'open' ORDER BY rowid", (attempt["id"],))
        if eng.SEVERITY[r["severity"]] >= eng.SEVERITY[block_on]]


def decide_findings(ctx: Ctx, number: int, which: list[int], decision: str, reason: str,
                    origin: str = "cli") -> dict:
    """La persona decide que hallazgos que frenaron la tarea no aplican o se harán después
    (en una tarea nueva en borrador). `which`: posiciones de `pending_findings` (1..n); vacío
    = todos."""
    if decision not in eng.DECIDED:
        raise OpError(f"decisión desconocida: {decision}")
    pending = pending_findings(ctx, number) or open_findings(ctx, number)
    if not pending:
        raise OpError(f"la tarea {number} no tiene hallazgos pendientes de decidir")
    if bad := [i for i in which if not 1 <= i <= len(pending)]:
        raise OpError(f"no hay hallazgos con esos números: {bad} (hay {len(pending)})")
    chosen = [pending[i - 1] for i in which] if which else pending
    run_row = latest_run(ctx, number)
    created = []
    for f in chosen:
        task = None
        if decision == "deferred":
            first = f["message"].split(". ")[0].rstrip(".")
            task = ctx.conn.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM task").fetchone()[0]
            where = f" ({f['file']}:{f['line']})" if f["file"] else ""
            ctx.conn.execute(
                "INSERT INTO task (id, number, title, about, description, acceptance, scope,"
                " priority, status, repos, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 3, 'draft', ?, ?, ?)",
                (new_id(), task, f"Pendiente de la tarea {number}: {first[:70]}",
                 f"Quedó pendiente de la revisión de la tarea {number}: {first}.",
                 f"{f['message']}{where}\n\nSurgió en la revisión de la tarea {number}; se "
                 f"decidió dejarlo para después ({reason}).",
                 json.dumps([f"Resuelto: {first}"], ensure_ascii=False),
                 json.dumps([f["file"]] if f["file"] else []),
                 task_row(ctx, number)["repos"], now(), now()))
            created.append(task)
        ctx.conn.execute("UPDATE finding SET status = ? WHERE id = ?", (decision, f["id"]))
        add_event(ctx.conn, run_row["id"], "finding.decided", origin, actor=actor(),
                  decision=decision, reason=reason, message=f["message"], task=task)
    remaining = len(pending) - len(chosen)
    _remember(ctx, origin)
    next_stage = retry_stages(ctx, number)[1] if run_row["status"] in ("BLOCKED", "FAILED") \
        else None
    return {"decided": len(chosen), "remaining": remaining, "tasks": created,
            "next_stage": next_stage}


def _remember(ctx: Ctx, origin: str) -> None:
    """Regenera `.umbra/aprendido.md` tras una decisión. Nunca frena la decisión."""
    try:
        memory.rebuild(ctx.conn, ctx.udir)
    except OSError as e:
        add_event(ctx.conn, None, "memory.failed", origin, error=str(e))


def _blocked_payload(ctx: Ctx, run_row) -> dict:
    row = ctx.conn.execute("SELECT payload FROM event WHERE run_id = ? AND type IN"
                           " ('run.blocked', 'run.failed') ORDER BY id DESC LIMIT 1",
                           (run_row["id"],)).fetchone()
    return json.loads(row[0]) if row else {}


def blocked_paths(ctx: Ctx, number: int) -> list[str]:
    """Rutas que la política bloqueó en la ejecución actual (en cualquiera de sus intentos)."""
    run_row = latest_run(ctx, number)
    paths: list[str] = []
    for r in ctx.conn.execute("SELECT payload FROM event WHERE run_id = ? AND type = 'run.blocked'"
                              " ORDER BY id", (run_row["id"],)):
        p = json.loads(r[0])
        if p.get("code") == "policy":
            paths += [v["path"] for v in p.get("details", {}).get("violations", [])
                      if v.get("path") and v["path"] not in paths]
    return paths


def allow_paths(ctx: Ctx, number: int, paths: list[str], origin: str = "cli") -> dict:
    """La persona autoriza cambiar, solo en esta tarea, rutas que la política protege; luego la
    ejecución detenida vuelve a Construir con ese permiso."""
    task = task_row(ctx, number)
    paths = [p.replace("\\", "/").strip() for p in paths if p.strip()]
    if not paths:
        raise OpError("indica al menos una ruta que autorizas a cambiar")
    current = json.loads(task["allowed_paths"] or "[]")
    merged = current + [p for p in paths if p not in current]
    ctx.conn.execute("UPDATE task SET allowed_paths = ?, revision = revision + 1, updated_at = ?"
                     " WHERE id = ?", (json.dumps(merged), now(), task["id"]))
    run_row = None
    try:
        run_row = latest_run(ctx, number)
    except OpError:
        pass
    add_event(ctx.conn, run_row["id"] if run_row else None, "policy.allowed", origin,
              actor=actor(), number=number, paths=paths)
    _remember(ctx, origin)  # antes de reanudar: el sobre del reintento ya trae lo aprendido
    resumed = None
    if run_row and run_row["status"] in ("BLOCKED", "FAILED"):
        resumed = retry(ctx, number, "build", origin=origin)
    return {"number": number, "allowed": merged, "resumed_from": resumed}


def answer(ctx: Ctx, number: int, text: str, origin: str = "cli") -> dict:
    """La persona responde las preguntas del agente; la ejecución sigue desde donde se detuvo."""
    text = text.strip()
    if not text:
        raise OpError("la respuesta está vacía")
    run_row = latest_run(ctx, number)
    if run_row["status"] not in ("BLOCKED", "FAILED"):
        raise OpError(f"la tarea {number} no está detenida (está en {run_row['status']})")
    add_event(ctx.conn, run_row["id"], "task.answered", origin, actor=actor(), answer=text)
    _remember(ctx, origin)  # antes de reanudar: el sobre del reintento ya trae lo aprendido
    payload = _blocked_payload(ctx, run_row)
    stage = payload.get("stage") if payload.get("code") == "agent_questions" else None
    stages = [s.name for s in cfg.load_routine(ctx.udir, run_row["routine"]).stages]
    resumed = retry(ctx, number, stage if stage in stages else None, origin=origin)
    return {"number": number, "resumed_from": resumed}


def _design_waiting(ctx: Ctx, number: int, *codes: str):
    run_row = latest_run(ctx, number)
    payload = _blocked_payload(ctx, run_row) if run_row["status"] == "BLOCKED" else {}
    if payload.get("code") not in codes:
        what = ("direcciones para elegir" if codes == ("design_choice",)
                else "un diseño esperando tu visto bueno")
        raise OpError(f"la tarea {number} no tiene {what}")
    return run_row, payload


def _taste(ctx: Ctx, text: str) -> None:
    from umbra.management import taste
    taste.record(ctx.root.name, text)


def design_approve(ctx: Ctx, number: int, origin: str = "cli") -> dict:
    """La persona da el visto bueno al diseño: Construir maqueta sobre él."""
    run_row, payload = _design_waiting(ctx, number, "design_review")
    images = payload.get("details", {}).get("images", [])
    rounds = ctx.conn.execute("SELECT COUNT(*) FROM event WHERE run_id = ? AND type ="
                              " 'design.changes'", (run_row["id"],)).fetchone()[0]
    add_event(ctx.conn, run_row["id"], "design.approved", origin, actor=actor(), images=images)
    title = latest_task_title(ctx, number)
    _taste(ctx, f"Aprobaste el diseño de «{title}» "
                + ("a la primera." if not rounds else f"tras {rounds} ronda(s) de cambios."))
    stages = [s.name for s in cfg.load_routine(ctx.udir, run_row["routine"]).stages]
    nxt = stages[stages.index("design") + 1] if "design" in stages[:-1] else None
    return {"number": number, "images": images, "resumed_from": retry(ctx, number, nxt,
                                                                       origin=origin)}


def design_changes(ctx: Ctx, number: int, text: str, origin: str = "cli") -> dict:
    """La persona pide cambios al diseño (o a las direcciones): el diseñador los aplica y
    vuelve a preguntar."""
    text = text.strip()
    if not text:
        raise OpError("di qué quieres cambiar del diseño")
    run_row, _ = _design_waiting(ctx, number, "design_review", "design_choice")
    add_event(ctx.conn, run_row["id"], "design.changes", origin, actor=actor(), text=text)
    _taste(ctx, f"Pediste en «{latest_task_title(ctx, number)}»: {text}")
    return {"number": number, "resumed_from": retry(ctx, number, "design", origin=origin)}


def design_pick(ctx: Ctx, number: int, option: int, origin: str = "cli") -> dict:
    """La persona elige una de las direcciones propuestas; el diseñador sigue esa línea."""
    run_row, payload = _design_waiting(ctx, number, "design_choice")
    options = payload.get("details", {}).get("options", [])
    if not 1 <= option <= len(options):
        raise OpError(f"elige una dirección entre 1 y {len(options)}")
    chosen = options[option - 1]
    others = [o["name"] for i, o in enumerate(options, 1) if i != option]
    add_event(ctx.conn, run_row["id"], "design.chosen", origin, actor=actor(), option=option,
              name=chosen["name"], images=chosen["images"], rejected=others)
    _taste(ctx, f"Elegiste la dirección «{chosen['name']}» frente a "
                + ", ".join(f"«{o}»" for o in others) + ".")
    return {"number": number, "chosen": chosen["name"],
            "resumed_from": retry(ctx, number, "design", origin=origin)}


def latest_task_title(ctx: Ctx, number: int) -> str:
    row = ctx.conn.execute("SELECT title FROM task WHERE number = ?", (number,)).fetchone()
    return row[0] if row else f"tarea {number}"


def retry(ctx: Ctx, number: int, from_: str | None = None, foreground: bool = False,
          origin: str = "cli") -> str:
    run_row = latest_run(ctx, number)
    if run_row["status"] not in ("BLOCKED", "FAILED", "WAITING_APPROVAL"):
        raise OpError(f"no se reintenta una ejecución en {run_row['status']}")
    stages, suggested = retry_stages(ctx, number)
    stage = from_ or suggested
    if stage not in stages:
        raise OpError(f"la rutina {run_row['routine']} no tiene la etapa '{stage}'")
    ctx.conn.execute("UPDATE run SET status = 'QUEUED', stage = ?, updated_at = ? WHERE id = ?",
                     (stage, now(), run_row["id"]))
    add_event(ctx.conn, run_row["id"], "run.retried", origin, stage=stage)
    dispatch(ctx.root, foreground)
    return stage


# ---------- proyecto nuevo con playbook ----------
def new_project(name: str, stack: str, parent: Path, remote: bool = True, context: bool = True,
                idea: str | None = None, origin: str = "cli") -> dict:
    """`umbra new`: repo listo para la primera tarea en minutos. git init + playbook (andamiaje,
    CI, convenciones, comandos) + .umbra + primer commit + repo en GitHub + CONTEXT.md."""
    from umbra.actions import gh
    from umbra.blocks.process import run_bounded
    from umbra.management import playbooks, projects
    try:
        book, folder = playbooks.load(stack)
    except playbooks.PlaybookError as e:
        raise OpError(str(e), 2) from e
    dest = parent / name
    if dest.exists() and any(dest.iterdir()):
        raise OpError(f"{dest} ya existe y no está vacío", 2)
    dest.mkdir(parents=True, exist_ok=True)
    git.run(dest, "init", "-q", "-b", "main")
    steps = []
    if scaffold := book.get("scaffold"):
        res = run_bounded(scaffold, dest, book.get("scaffold_timeout_s", 15 * 60))
        if res.exit_code != 0:
            raise OpError(f"el andamiaje `{scaffold}` falló (exit {res.exit_code}):\n"
                          + res.output[-1500:], 3)
        steps.append("andamiaje")
    for src, target in (book.get("files") or {}).items():
        out = dest / target
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists():  # el andamiaje manda; el playbook completa
            shutil.copyfile(folder / src, out)
    steps.append("archivos del playbook")
    project.init_project(dest, stack=stack, commands=book.get("commands") or {},
                         default_routine=book.get("default_routine"))
    steps.append(".umbra/project.toml")
    git.run(dest, "add", "-A")
    if git.has_changes(dest) or not git.head_or_none(dest):
        git.run(dest, "commit", "-q", "-m", f"umbra: proyecto nuevo ({stack})")
    result = {"root": dest.as_posix(), "stack": stack, "steps": steps, "remote": None,
              "context": False, "conversation": None}
    if remote:
        try:
            gh.repo_create(dest, name)
            result["remote"] = name
            steps.append("repo en GitHub")
        except gh.GhError as e:
            result["remote_error"] = str(e)
    ctx = load(dest)
    try:
        if context:
            result["context"] = bool(context_build(ctx, origin).get("changed", True))
            steps.append("CONTEXT.md")
        if idea:
            result["conversation"] = spec_new(ctx, idea, origin)
    except OpError as e:
        result["context_error"] = str(e)
    finally:
        ctx.conn.close()
    projects.register(dest, stack)
    return result


# ---------- adoptar una carpeta existente ----------
ADOPT_IGNORE = (".env", ".env.*", "node_modules/", "vendor/", ".venv/", "venv/", "__pycache__/",
                "*.log")


def adopt(folder: Path, origin: str = "cli") -> dict:
    """Pone umbra en una carpeta que ya existe. Si no era repo git, lo crea con un primer
    commit (con un .gitignore básico si no tenía, para no versionar secretos ni dependencias)."""
    if not folder.is_dir():
        raise OpError(f"no existe la carpeta {folder}", 2)
    steps = []
    if not (folder / ".git").exists():
        git.run(folder, "init", "-q", "-b", "main")
        steps.append("git init")
        ignore = folder / ".gitignore"
        if not ignore.exists():
            ignore.write_text("\n".join(ADOPT_IGNORE) + "\n", encoding="utf-8", newline="\n")
            steps.append(".gitignore básico")
    result = project.init_project(folder)
    steps.append(".umbra/project.toml" if result["created"] else "ya tenía umbra")
    if not git.head_or_none(folder):  # umbra necesita un commit del que partir
        git.run(folder, "add", "-A")
        git.run(folder, "commit", "-q", "--no-verify", "-m", "umbra: adopta el proyecto")
        steps.append("primer commit")
    ctx = load(folder)
    try:
        add_event(ctx.conn, None, "project.adopted", origin, steps=steps)
    finally:
        ctx.conn.close()
    return {**result, "steps": steps}


# ---------- MySQL local: consultar libre, cambiar solo con permiso de la persona ----------
def _db_dir(ctx: Ctx) -> Path:
    return ctx.udir / "artifacts" / "db"


def db_query(ctx: Ctx, sql: str, database: str | None = None) -> dict:
    from umbra.blocks import mysql
    try:
        return mysql.query(ctx.config, sql, database)
    except mysql.MySQLError as e:
        raise OpError(str(e), 2) from e


def db_propose(ctx: Ctx, sql: str, database: str | None = None, origin: str = "cli") -> dict:
    """Deja un cambio pendiente; solo `db_apply` (la persona) lo ejecuta."""
    import secrets
    if not sql.strip():
        raise OpError("el cambio está vacío", 2)
    change = {"id": secrets.token_hex(4), "sql": sql.strip(), "database": database,
              "proposed_at": now(), "origin": origin}
    path = _db_dir(ctx) / f"{change['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(change, ensure_ascii=False, indent=1), encoding="utf-8")
    add_event(ctx.conn, None, "db.proposed", origin, id=change["id"], sql=change["sql"],
              database=database)
    return change


def db_pending(ctx: Ctx) -> list[dict]:
    files = sorted(_db_dir(ctx).glob("*.json"), key=lambda f: f.stat().st_mtime)
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def _db_take(ctx: Ctx, change_id: str) -> tuple[dict, Path]:
    path = _db_dir(ctx) / f"{change_id}.json"
    if not re.fullmatch(r"[0-9a-f]{8}", change_id) or not path.exists():
        raise OpError(f"no hay un cambio pendiente {change_id} (umbra db list)", 2)
    return json.loads(path.read_text(encoding="utf-8")), path


def db_apply(ctx: Ctx, change_id: str, origin: str = "cli") -> dict:
    from umbra.blocks import mysql
    change, path = _db_take(ctx, change_id)
    try:
        affected = mysql.execute(ctx.config, change["sql"], change.get("database"))
    except mysql.MySQLError as e:
        add_event(ctx.conn, None, "db.failed", origin, id=change_id, error=str(e))
        raise OpError(f"el cambio falló y no se aplicó: {e}", 3) from e
    path.unlink()
    add_event(ctx.conn, None, "db.applied", origin, id=change_id, sql=change["sql"],
              affected=affected, user=actor())
    return {**change, "affected": affected}


def db_discard(ctx: Ctx, change_id: str, origin: str = "cli") -> dict:
    change, path = _db_take(ctx, change_id)
    path.unlink()
    add_event(ctx.conn, None, "db.discarded", origin, id=change_id)
    return change


# ---------- takeover: la persona arregla a mano y umbra retoma ----------
STOPPED = ("BLOCKED", "FAILED", "WAITING_APPROVAL")


def _workspace(ctx: Ctx, number: int) -> tuple[sqlite3.Row, Path]:
    run_row = latest_run(ctx, number)
    if run_row["status"] not in STOPPED:
        raise OpError(f"la tarea {number} no está detenida (está en {run_row['status']})")
    wt = Path(run_row["worktree"] or "")
    if not run_row["worktree"] or not wt.is_dir():
        raise OpError(f"la tarea {number} ya no tiene espacio de trabajo: empieza de cero", 2)
    return run_row, wt


def editor_command(config: dict) -> list[str]:
    cmd = (config.get("editor", {}).get("command") or os.environ.get("VISUAL")
           or os.environ.get("EDITOR") or "code")
    if os.name == "nt":  # sin modo posix se conservan las comillas: se quitan a mano
        return [part.strip('"') for part in shlex.split(cmd, posix=False)]
    return shlex.split(cmd)


def open_workspace(ctx: Ctx, number: int, origin: str = "cli") -> dict:
    """Abre el worktree de la tarea en el editor de la persona; queda registrado."""
    run_row, wt = _workspace(ctx, number)
    cmd = editor_command(ctx.config)
    try:
        subprocess.Popen([process.resolve(cmd[0]), *cmd[1:], str(wt)],
                         **process.background_kwargs())
    except OSError as e:
        raise OpError(f"no se pudo abrir el editor «{cmd[0]}»: {e}. Configura [editor] "
                      "command en .umbra/project.toml") from e
    add_event(ctx.conn, run_row["id"], "takeover.opened", origin, actor=actor(),
              editor=cmd[0], worktree=wt.as_posix())
    return {"number": number, "editor": cmd[0], "worktree": wt.as_posix()}


def resume_human(ctx: Ctx, number: int, message: str, foreground: bool = False,
                 origin: str = "cli") -> dict:
    """Confirma el arreglo de la persona como un intento más (con los tests como evidencia) y
    encola la ejecución desde la etapa siguiente a Construir."""
    message = message.strip()
    if not message:
        raise OpError("di en una línea qué arreglaste (-m)")
    run_row, wt = _workspace(ctx, number)
    run_id = run_row["id"]
    e = engine(ctx, origin, run_id)
    ps = e.parts(e.run_row(run_id))  # en una tarea entre repos, cada repo
    if any("test" not in commands.registered(p.config) for p in ps):
        raise OpError("no hay comando 'test' registrado en .umbra/project.toml")
    for p in ps:
        if git.has_changes(p.wt):
            git.commit_all(p.wt, f"humano: {message}")
    heads = e.heads(ps)
    head = fingerprint(heads)
    tested = ctx.conn.execute("SELECT tested_sha FROM artifact WHERE run_id = ? AND tested_sha"
                              " IS NOT NULL ORDER BY created_at DESC LIMIT 1", (run_id,)
                              ).fetchone()
    last = tested[0] if tested and len(ps) == 1 else None
    if head == (last or run_row["head_sha"] or run_row["base_sha"]):
        raise OpError("no hay cambios nuevos en el espacio de trabajo de la tarea")
    attempt_no = ctx.conn.execute(
        "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM attempt WHERE run_id = ? AND"
        " stage = 'build'", (run_id,)).fetchone()[0]
    attempt_id = new_id()
    ctx.conn.execute(
        "INSERT INTO attempt (id, run_id, stage, attempt_no, profile, agent, status, started_at)"
        " VALUES (?, ?, 'build', ?, 'takeover', 'human', 'running', ?)",
        (attempt_id, run_id, attempt_no, now()))
    add_event(ctx.conn, run_id, "takeover.done", origin, actor=actor(), message=message,
              attempt=attempt_id, sha=head)
    failed = None
    for p in ps:
        test = commands.run_registered(ctx.conn, p.config, "test", p.wt, ctx.udir, run_id,
                                       attempt_id, tested_sha=heads[p.repo])
        add_event(ctx.conn, run_id, "evidence.tests", origin, attempt=attempt_id,
                  sha=heads[p.repo], exit_code=test["exit_code"], command=test["command"],
                  **({"repo": p.repo} if p.repo else {}))
        failed = failed or (test if test["exit_code"] != 0 else None)
    ok = failed is None
    test = failed or test
    ctx.conn.execute("UPDATE attempt SET status = ?, ended_at = ? WHERE id = ?",
                     ("done" if ok else "tests_failed", now(), attempt_id))
    e.save_heads(run_id, heads)
    if not ok:
        raise OpError(f"tu arreglo deja los tests en rojo (`{test['command']}` terminó con "
                      f"exit {test['exit_code']}); la tarea sigue detenida:\n"
                      + test["output"][-1500:])
    stages = [s.name for s in cfg.load_routine(ctx.udir, run_row["routine"]).stages]
    after = stages[stages.index("build") + 1:] if "build" in stages else stages
    stage = next((s for s in after if s != "plan"), stages[-1])
    resumed = retry(ctx, number, stage, foreground, origin=origin)
    return {"number": number, "attempt": attempt_id, "resumed_from": resumed}


# ---------- evidencia y decisión humana ----------
def evidence(ctx: Ctx, number: int) -> dict:
    run_row = latest_run(ctx, number)
    rid = run_row["id"]
    data = {
        "run": {k: run_row[k] for k in ("id", "status", "stage", "base_sha", "head_sha",
                                        "branch")},
        "attempts": [dict(r) for r in ctx.conn.execute(
            "SELECT a.stage, a.attempt_no, a.profile, a.agent, a.status, a.started_at,"
            " a.ended_at, u.cost, u.estimated, u.input_tokens, u.output_tokens"
            " FROM attempt a LEFT JOIN usage u"
            " ON u.attempt_id = a.id WHERE a.run_id = ? ORDER BY a.started_at", (rid,))],
        "artifacts": [dict(r) for r in ctx.conn.execute(
            "SELECT kind, command, exit_code, tested_sha, path FROM artifact WHERE run_id = ?"
            " ORDER BY created_at", (rid,))],
        "approvals": [dict(r) for r in ctx.conn.execute(
            "SELECT decision, head_sha, actor, created_at FROM approval WHERE run_id = ?",
            (rid,))],
        "findings": [dict(r) for r in ctx.conn.execute(
            "SELECT f.severity, f.message, f.file, f.line, a.stage FROM finding f"
            " JOIN attempt a ON a.id = f.attempt_id WHERE a.run_id = ? ORDER BY a.started_at",
            (rid,))],
    }
    data["cost"] = str(sum((Decimal(a["cost"] or 0) for a in data["attempts"]), Decimal(0)))
    data["unpriced_tokens"] = sum(store_unpriced(a) for a in data["attempts"] if a["cost"])
    data["diff_stat"] = ""
    if run_row["worktree"] and Path(run_row["worktree"]).exists() and run_row["head_sha"]:
        try:
            data["diff_stat"] = diff_stat(ctx, run_row)
        except (git.GitError, OpError):
            pass
    pr = engine(ctx).pr_info(rid)
    data["pr"] = pr
    data["report"] = report(ctx, number, data)
    return data


TEST_COUNTS = re.compile(r"(\d+) (passed|failed|skipped|errors?)\b")


def report(ctx: Ctx, number: int, data: dict) -> dict:
    """Qué se hizo y cómo se comprobó, en lenguaje llano: datos exactos + el resumen del agente."""
    run_row, task = latest_run(ctx, number), task_row(ctx, number)
    rid, head = run_row["id"], run_row["head_sha"]
    eng_ = engine(ctx)
    ready = eng_.last_event(rid, "summary.ready")
    summary = json.loads(ready["payload"]) if ready else None
    if summary and summary["sha"] == head:
        what, by, plain = summary["summary"], "el agente de resumen", summary["observations"]
    else:
        what, by, plain = ex.about(ctx.conn, task, run_row)["work"], "el constructor", []

    tests = ctx.conn.execute(
        "SELECT exit_code, tested_sha, path FROM artifact WHERE run_id = ?"
        " AND kind = 'command:test' ORDER BY created_at DESC LIMIT 1", (rid,)).fetchone()
    test_info = None
    if tests:
        try:
            tail = Path(tests["path"]).read_text(encoding="utf-8", errors="replace")[-2000:]
        except OSError:
            tail = ""
        test_info = {"ok": tests["exit_code"] == 0, "current": tests["tested_sha"] == head,
                     "counts": {k.rstrip("s"): int(n) for n, k in TEST_COUNTS.findall(tail)}}

    attempts = data["attempts"]
    verify = next((a for a in reversed(attempts) if a["stage"] == "verify"
                   and a["status"] in ("done", "findings")), None)
    unmet = [] if not verify or verify["status"] == "done" else [
        r["message"] for r in ctx.conn.execute(
            "SELECT f.message FROM finding f JOIN attempt a ON a.id = f.attempt_id"
            " WHERE a.run_id = ? AND a.stage = 'verify' AND a.started_at = ?",
            (rid, verify["started_at"]))]

    fixed = [(r, f) for r in eng_.finding_rounds(rid) for f in r.findings]
    if len(plain) != len(fixed):
        plain = [f.message.split(". ")[0].rstrip(".") for _, f in fixed]
    observations = [{"text": text, "resolved": any(
        a["stage"] == r.stage and a["status"] == "done" and a["started_at"] > r.ended_at
        for a in attempts)} for (r, _), text in zip(fixed, plain, strict=True)]
    scan = next((a["status"] for a in reversed(attempts) if a["stage"] == "scan"), None)
    shots = ctx.conn.execute("SELECT COUNT(*) FROM artifact WHERE run_id = ? AND"
                             " kind = 'screenshot' AND tested_sha = ?", (rid, head)).fetchone()[0]

    changes = {"código": [0, 0, 0], "pruebas": [0, 0, 0], "documentación": [0, 0, 0]}
    if head and run_row["base_sha"]:
        try:
            numstat = parts.numstat(run_parts(ctx, run_row))
        except (git.GitError, OpError):
            numstat = ""
        for line in numstat.splitlines():
            added, removed, path = line.split("\t", 2)
            kind = ("pruebas" if policy.is_test_file(path) else "documentación"
                    if path.endswith(".md") or path.startswith(("docs/", "specs/")) else "código")
            changes[kind][0] += 1
            changes[kind][1] += int(added) if added.isdigit() else 0
            changes[kind][2] += int(removed) if removed.isdigit() else 0

    starts = [a["started_at"] for a in attempts]
    ends = [a["ended_at"] or now() for a in attempts]
    minutes = round((datetime.fromisoformat(max(ends))
                     - datetime.fromisoformat(min(starts))).total_seconds() / 60) if starts else 0
    return {
        "number": number, "title": task["title"],
        "state": ex.RUN_STATES.get(run_row["status"], run_row["status"]),
        "what": what, "what_by": by, "tests": test_info,
        "criteria": {"items": json.loads(task["acceptance"] or "[]"),
                     "checked": verify is not None, "unmet": unmet},
        "review_rounds": sum(1 for a in attempts if a["stage"] == "review"
                             and a["status"] in ("done", "findings")),
        "observations": observations, "scan": scan, "changes": changes,
        "screenshots": shots,
        "design": len(eng_.approved_design(rid)),
        "cost": data["cost"], "unpriced_tokens": data["unpriced_tokens"],
        "minutes": minutes, "attempts": len(attempts),
        "pr": " · ".join(f"{p['repo']}: {p['url']}" for p in (data.get("pr") or {})["repos"])
        if "repos" in (data.get("pr") or {}) else (data.get("pr") or {}).get("url"),
    }


def approve(ctx: Ctx, number: int, origin: str = "cli") -> dict:
    run_row = latest_run(ctx, number)
    if run_row["status"] != "WAITING_APPROVAL":
        raise OpError(f"la ejecución está en {run_row['status']}, no en WAITING_APPROVAL")
    try:
        result = eng.approve(engine(ctx, origin, run_row["id"]), run_row["id"], actor())
    except Exception as e:  # ApprovalError/GhError/GitError: la ejecución sigue en espera
        raise OpError(str(e)) from e
    repos = result.pop("repos", None) or [repo_of(ctx, task_row(ctx, number))]
    result["pulled"] = _pull(ctx, repos, origin)
    started = autopilot(ctx, origin)
    result["next"] = started[0] if started else None
    return result


def _pull(ctx: Ctx, repos: list[tuple[Path, dict]], origin: str) -> bool:
    """Tu copia local de la base de cada repo integrado, al día; y su mapa, sin frenar."""
    pulled = False
    for root, config in repos:
        base = config.get("project", {}).get("base_branch", "main")
        if git.fast_forward(root, base):
            pulled = True
            if config.get("context", {}).get("auto", True):
                threading.Thread(target=_context_after_merge, args=(ctx.root, origin, root),
                                 daemon=True).start()
    return pulled


def _context_after_merge(root: Path, origin: str, repo: Path | None = None) -> None:
    try:
        context_build(load(root), origin, None if repo == root else repo)
    except Exception:  # queda registrado por context_build; nunca rompe la aprobación
        pass


CONTEXT_FILE = "CONTEXT.md"


def context_build(ctx: Ctx, origin: str = "cli", repo: Path | None = None) -> dict:
    """El cartógrafo escribe `CONTEXT.md` sobre la raíz del repo; si cambió, lo deja en un commit
    de la rama actual. Si tocó cualquier otra cosa, se restaura y falla. En un espacio, sobre
    `repo` (o sobre cada uno de sus repos)."""
    from umbra.adapters import get_adapter
    from umbra.adapters.base import AgentRun
    from umbra.contracts.envelope import Envelope, StageOutput, TaskInfo
    from umbra.unified.store import to_cost

    if repo is None and ctx.members:
        results = {name: context_build(ctx, origin, path) for name, path in ctx.members.items()}
        return {"changed": any(r["changed"] for r in results.values()),
                "summary": "\n".join(f"{n}: {r['summary']}" for n, r in results.items()),
                "cost": to_cost(sum(Decimal(r["cost"]) for r in results.values())),
                "repos": results}
    ctx = Ctx(repo, ctx.udir, ctx.conn, ctx.config) if repo else ctx

    profile = cfg.load_profile(ctx.udir, "cartographer")
    before = set(git.run(ctx.root, "status", "--porcelain").splitlines())
    invocation = new_id()
    envelope = Envelope(run_id=f"context-{invocation[:8]}", stage="context",
                        attempt_id=invocation, input_sha=git.head(ctx.root),
                        task=TaskInfo(number=0, title="Mantener CONTEXT.md",
                                      description="Escribe o actualiza el mapa del repositorio."))
    req = AgentRun(envelope, profile, ctx.root,
                   ctx.udir / "artifacts" / f"{invocation}-context.jsonl",
                   output_model=StageOutput)
    result = get_adapter(profile.agent, ctx.udir).run(req)
    ctx.conn.execute(
        "INSERT INTO usage (id, agent, model, input_tokens, output_tokens, cost, estimated,"
        " invocation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (new_id(), profile.agent, result.model, result.input_tokens, result.output_tokens,
         to_cost(result.cost), int(result.estimated), invocation))
    after = set(git.run(ctx.root, "status", "--porcelain").splitlines())
    new = after - before
    others = [ln[3:] for ln in new if not ln.endswith(CONTEXT_FILE)]
    if others:  # solo puede escribir el mapa: lo demás se restaura y se registra
        for path in others:
            if git.ok(ctx.root, "ls-files", "--error-unmatch", path):
                git.ok(ctx.root, "checkout", "--", path)
            else:
                (ctx.root / path).unlink(missing_ok=True)
        add_event(ctx.conn, None, "context.failed", origin, error=f"tocó {', '.join(others)}")
        raise OpError(f"el cartógrafo tocó archivos que no debía: {', '.join(others)}")
    if not result.ok:
        add_event(ctx.conn, None, "context.failed", origin, error=result.error)
        raise OpError(result.error or "el cartógrafo falló")
    changed = any(ln.endswith(CONTEXT_FILE) for ln in new)
    if changed:
        git.run(ctx.root, "add", CONTEXT_FILE)
        git.run(ctx.root, "commit", "--no-verify", "-q", "-m", "umbra: CONTEXT.md al día",
                "--", CONTEXT_FILE)
    summary = result.output.summary if result.output else ""
    add_event(ctx.conn, None, "context.updated", origin, changed=changed, summary=summary)
    return {"changed": changed, "summary": summary, "cost": to_cost(result.cost)}


def waiting_tasks(ctx: Ctx) -> list[int]:
    """Tareas cuya última ejecución espera aprobación, en orden."""
    return [r[0] for r in ctx.conn.execute(
        "SELECT t.number FROM task t JOIN run r ON r.id = (SELECT id FROM run WHERE"
        " task_id = t.id ORDER BY created_at DESC LIMIT 1) WHERE r.status = 'WAITING_APPROVAL'"
        " ORDER BY t.number")]


def approve_all(ctx: Ctx, origin: str = "cli") -> dict:
    """Integra, una por una, todas las que esperan; se detiene en la primera que no se pueda."""
    done, failed = [], None
    for n in waiting_tasks(ctx):
        try:
            done.append((n, approve(ctx, n, origin)))
        except OpError as e:
            failed = (n, str(e))
            break
    return {"approved": [n for n, _ in done], "results": [r for _, r in done], "failed": failed}


def autopilot(ctx: Ctx, origin: str = "cli", dispatch_worker: bool = True,
              force: bool = False) -> list[int]:
    """Arranca las tareas aceptadas que ya pueden ir, hasta llenar `[blocks] parallel`.

    Aceptar una tarea es el consentimiento para ejecutarla; las que ya se intentaron y se
    detuvieron esperan a la persona. Devuelve los números que arrancaron."""
    if not force and not ctx.config.get("autopilot", {}).get("enabled", True):
        return []
    marks = ",".join("?" * len(ACTIVE_RUN_STATES))
    active = ctx.conn.execute(f"SELECT COUNT(*) FROM run WHERE status IN ({marks})",
                              ACTIVE_RUN_STATES).fetchone()[0]
    started: list[int] = []
    for t in ctx.conn.execute("SELECT * FROM task WHERE status = 'accepted'"
                              " ORDER BY priority, number").fetchall():
        if active + len(started) >= worker.parallel_limit(ctx.config):
            break
        if pending_dependencies(ctx.conn, t["id"]) or ctx.conn.execute(
                "SELECT 1 FROM run WHERE task_id = ?", (t["id"],)).fetchone():
            continue
        try:
            run(ctx, [t["number"]], origin="autopilot", dispatch_worker=False)
        except OpError as e:
            add_event(ctx.conn, None, "autopilot.skipped", origin, task=t["number"],
                      reason=str(e))
            break
        started.append(t["number"])
    if started and dispatch_worker:
        dispatch(ctx.root, False)
    return started


# ---------- specs: aprobación completa y modo noche ----------
def spec_ref(ctx: Ctx, ref: str) -> str:
    """`specs/001-x`, `001-x` o la ruta de la carpeta → el `spec_dir` como lo guardan las tareas."""
    text = str(ref).replace("\\", "/").rstrip("/")
    for cand in (text, f"specs/{text}", text.split("/")[-1], f"specs/{text.split('/')[-1]}"):
        if ctx.conn.execute("SELECT 1 FROM task WHERE spec_dir = ?", (cand,)).fetchone():
            return cand
    raise OpError(f"no hay tareas de la spec «{ref}»", 2)


def spec_pr(ctx: Ctx, spec_dir: str) -> dict | None:
    """El PR de la spec a la base (cuando todas sus historias están integradas) y su estado."""
    op = ctx.conn.execute("SELECT external_ref FROM operation WHERE operation_key = ?",
                          (f"spec:{spec_dir}:pr",)).fetchone()
    if not op:
        return None
    merged = ctx.conn.execute("SELECT external_ref FROM operation WHERE operation_key = ?"
                              " AND status = 'done'", (f"spec:{spec_dir}:merge",)).fetchone()
    return {**json.loads(op[0]), "state": "merged" if merged else "waiting",
            "merge_sha": merged[0] if merged else None}


def waiting_specs(ctx: Ctx) -> list[str]:
    out = []
    for r in ctx.conn.execute("SELECT operation_key FROM operation WHERE operation_key LIKE"
                              " 'spec:%:pr' ORDER BY updated_at"):
        d = r[0][len("spec:"):-len(":pr")]
        if (spec_pr(ctx, d) or {}).get("state") == "waiting":
            out.append(d)
    return out


def approve_spec(ctx: Ctx, ref: str, origin: str = "cli") -> dict:
    """La persona aprueba la spec completa: su PR (rama de spec → base) se integra."""
    from umbra.actions import gh
    spec_dir = spec_ref(ctx, ref)
    pr = spec_pr(ctx, spec_dir)
    if not pr:
        left = ctx.conn.execute("SELECT number FROM task WHERE spec_dir = ? AND status NOT IN"
                                " ('done', 'dropped') ORDER BY number", (spec_dir,)).fetchall()
        raise OpError(f"la spec {spec_dir} todavía no tiene PR: faltan por integrar las tareas "
                      f"{', '.join(str(r[0]) for r in left) or '(ninguna; reintenta)'}")
    if pr["state"] == "merged":
        raise OpError(f"la spec {spec_dir} ya está integrada (merge {pr['merge_sha'][:10]})")
    # en un espacio, un PR por repo, en el orden del espacio; cada uno con su clave: aprobar de
    # nuevo tras un fallo integra solo lo que faltaba
    prs = pr.get("repos") or [{"repo": None, "number": pr["number"], "url": pr["url"]}]
    merged, repos, merge_sha = [], [], None
    for part in prs:
        name = part["repo"]
        root, config = ((ctx.members[name], project.repo_config(ctx.config, ctx.members[name]))
                        if name else (ctx.root, ctx.config))
        key = f"spec:{spec_dir}:merge:{name}"
        if name and (done := _operation(ctx, key)):
            merge_sha = done
            merged.append(name)
            continue
        where = f" de {name}" if name else ""
        try:
            current = gh.view_pr(root, part["number"])
            if current["state"] != "MERGED":
                if current.get("mergeable") == "CONFLICTING":
                    raise OpError(f"el PR #{part['number']}{where} de la spec tiene conflictos con"
                                  " la base; resuélvelos en la rama de la spec y vuelve a aprobar")
                gh.merge_pr(root, part["number"], current["headRefOid"])
            final = gh.view_pr(root, part["number"])
            merge_sha = (final.get("mergeCommit") or {}).get("oid")
            if final["state"] != "MERGED" or not merge_sha:
                raise OpError(f"el proveedor no confirma el merge{where} (estado "
                              f"{final['state']})")
        except (OpError, gh.GhError) as e:
            if not merged:
                raise OpError(str(e)) from e
            add_event(ctx.conn, None, "spec.partial", origin, spec_dir=spec_dir, merged=merged,
                      pending=name, reason=str(e))
            raise OpError(f"integrado en {', '.join(merged)}; falta {name}: {e}. Cuando lo "
                          "resuelvas, aprueba de nuevo: solo se integra lo que falta") from e
        if name:
            _record_merge(ctx, key, merge_sha)
            merged.append(name)
        repos.append((root, config))
    _record_merge(ctx, f"spec:{spec_dir}:merge", merge_sha)
    add_event(ctx.conn, None, "spec.approved", origin, spec_dir=spec_dir, pr=pr["number"],
              merge_sha=merge_sha, actor=actor(), repos=merged)
    pulled = _pull(ctx, repos, origin)
    return {"spec_dir": spec_dir, "pr": pr["url"], "merge_sha": merge_sha, "pulled": pulled,
            "repos": [{"repo": p["repo"], "url": p["url"]} for p in prs if p["repo"]]}


def _operation(ctx: Ctx, key: str) -> str | None:
    row = ctx.conn.execute("SELECT external_ref FROM operation WHERE operation_key = ? AND"
                           " status = 'done'", (key,)).fetchone()
    return row[0] if row else None


def _record_merge(ctx: Ctx, key: str, merge_sha: str) -> None:
    ctx.conn.execute(
        "INSERT INTO operation (operation_key, kind, status, external_ref, updated_at)"
        " VALUES (?, 'merge', 'done', ?, ?) ON CONFLICT(operation_key) DO UPDATE SET"
        " status = 'done', external_ref = excluded.external_ref, updated_at = excluded.updated_at",
        (key, merge_sha, now()))


def night(ctx: Ctx, ref: str | None = None, origin: str = "cli") -> dict:
    """Deja todo encolado: acepta los borradores (de una spec o de todas) y arranca lo que quepa;
    el piloto automático encadena el resto a medida que se integran."""
    spec_dir = spec_ref(ctx, ref) if ref else None
    where, args = ("AND spec_dir = ?", (spec_dir,)) if spec_dir else ("", ())
    drafts = [r[0] for r in ctx.conn.execute(
        f"SELECT number FROM task WHERE status = 'draft' {where} ORDER BY number", args)]
    if drafts:
        accept(ctx, drafts, origin)
    started = autopilot(ctx, origin, force=True)  # la noche es consentimiento explícito
    waiting = [r[0] for r in ctx.conn.execute(
        "SELECT t.number FROM task t WHERE t.status = 'accepted' AND NOT EXISTS"
        f" (SELECT 1 FROM run WHERE task_id = t.id) {where} ORDER BY t.number", args)]
    return {"spec_dir": spec_dir, "accepted": drafts, "started": started, "waiting": waiting,
            "autopilot": bool(ctx.config.get("autopilot", {}).get("enabled", True)),
            "parallel": worker.parallel_limit(ctx.config)}


def reject(ctx: Ctx, number: int, reason: str, origin: str = "cli") -> None:
    run_row = latest_run(ctx, number)
    try:
        eng.reject(engine(ctx, origin, run_row["id"]), run_row["id"], actor(), reason)
    except eng.ApprovalError as e:
        raise OpError(str(e)) from e


# --- conversación de requisitos (spec new/resume) ---------------------------------------------

def spec_max_cost(ctx: Ctx) -> Decimal:
    from umbra.chat import elicit
    try:
        return elicit.max_cost_usd(ctx.config)
    except ValueError as e:
        raise OpError(str(e), 2) from e


def spec_new(ctx: Ctx, idea: str, origin: str = "spec") -> str:
    from umbra.chat import elicit
    conv_id = elicit.new_conversation(ctx.conn, idea, origin)
    spec_event(ctx, "started", conv_id, origin, idea=idea)
    return conv_id


def spec_event(ctx: Ctx, kind: str, conv_id: str, origin: str = "spec", **data) -> None:
    add_event(ctx.conn, None, f"spec.{kind}", origin, conversation=conv_id, **data)


def spec_resume_target(ctx: Ctx, ref: str | None):
    """Conversación a reabrir: la última abierta, o la de la spec `NNN` / ruta indicada."""
    rows = ctx.conn.execute("SELECT * FROM conversation ORDER BY updated_at DESC").fetchall()
    if ref is None:
        pool = [r for r in rows if r["phase"] not in ("done", "discarded")]
        if not pool:
            raise OpError("no hay conversaciones abiertas; empieza con `umbra spec new`", 2)
        return pool[0]
    if ref.isdigit():
        def match(d):
            m = re.match(r"\d+", Path(d).name)
            return bool(m) and int(m.group()) == int(ref)
    else:
        path = Path(ref)
        try:
            want = (path if path.is_absolute() else ctx.root / path).resolve() \
                .relative_to(ctx.root.resolve()).as_posix()
        except ValueError:
            want = path.as_posix()
        def match(d):
            return d == want
    for r in rows:
        if r["spec_dir"] and match(r["spec_dir"]):
            if r["phase"] in ("done", "discarded"):
                raise OpError(f"la conversación de {r['spec_dir']} ya terminó ({r['phase']})", 2)
            return r
    raise OpError(f"no hay una conversación para la spec {ref}", 2)


def _spec_lease(row) -> str:
    # ponytail: antes del plan no hay spec_dir; se usa el id de la conversación
    return f"spec:{row['spec_dir'] or row['id']}"


def spec_lock(ctx: Ctx, conv_id: str) -> tuple[str, int]:
    """Una pantalla por conversación; si está ocupada explica quién la tiene y hasta cuándo."""
    from umbra.blocks import lease
    row = ctx.conn.execute("SELECT id, spec_dir FROM conversation WHERE id = ?",
                           (conv_id,)).fetchone()
    name = _spec_lease(row)
    token = lease.acquire(ctx.conn, name, f"{actor()}@{os.getpid()}")
    if token is None:
        held = ctx.conn.execute("SELECT owner, expires_at FROM lease WHERE name = ?",
                                (name,)).fetchone()
        who = f"{held['owner']}, hasta {held['expires_at']}" if held else "otra sesión"
        raise OpError(f"Esta conversación ya está abierta en otra pantalla ({who}). Ciérrala "
                      "ahí o espera a que expire.", 4)
    return name, token


def spec_renew(ctx: Ctx, lock: tuple[str, int]) -> bool:
    from umbra.blocks import lease
    return lease.renew(ctx.conn, *lock)


def spec_unlock(ctx: Ctx, lock: tuple[str, int]) -> None:
    from umbra.blocks import lease
    lease.release(ctx.conn, *lock)


def _history_file(ctx: Ctx, conv_id: str) -> Path:
    return ctx.udir / "artifacts" / f"{conv_id}.jsonl"


def spec_log(ctx: Ctx, conv_id: str, text: str) -> None:
    path = _history_file(ctx, conv_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")


def spec_history(ctx: Ctx, conv_id: str) -> list[str]:
    path = _history_file(ctx, conv_id)
    if not path.is_file():
        return []
    return [json.loads(x)["text"] for x in path.read_text(encoding="utf-8").splitlines() if x]


def spec_script() -> str:
    return "ps" if sys.platform == "win32" else "sh"


def preflight(ctx: Ctx, confirm=None) -> None:
    """Comprueba `claude` y `.specify/`; ofrece `specify init` si la persona confirma."""
    if not shutil.which("claude"):
        raise OpError("No se encontró `claude`. Instala Claude Code y ejecuta `claude login`; "
                      "luego vuelve a intentarlo.", 2)
    if (ctx.root / ".specify").is_dir():
        return
    cmd = ["specify", "init", "--here", "--ai", "claude", "--script", spec_script()]
    if ctx.members:  # la carpeta de un espacio no es (ni debe volverse) un repo
        cmd.append("--no-git")
    text = " ".join(cmd)
    specify = shutil.which("specify")
    if not specify:
        raise OpError("Este proyecto no tiene `.specify/` y `specify` no está instalado. "
                      f"Instálalo con `uv tool install specify-cli` y ejecuta `{text}`.", 2)
    if not (confirm and confirm(f"Falta `.specify/`. ¿Ejecutar `{text}`?")):
        raise OpError(f"Falta `.specify/`. Ejecuta `{text}` y vuelve a intentarlo.", 2)
    proc = subprocess.run([specify, *cmd[1:]], cwd=ctx.root, capture_output=True, text=True)
    if proc.returncode != 0 or not (ctx.root / ".specify").is_dir():
        raise OpError(f"`specify init` falló: {(proc.stderr or proc.stdout).strip()}")
