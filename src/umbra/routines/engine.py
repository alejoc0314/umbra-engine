"""Máquina de estados de una ejecución. Cada paso es idempotente: retomar = re-ejecutar el paso."""

import hashlib
import json
import re
import shutil
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from umbra.actions import commands, gh, git, policy, secrets
from umbra.adapters import get_adapter
from umbra.adapters.base import AgentResult, AgentRun
from umbra.blocks import notify, telegram, worktree
from umbra.contracts.envelope import Envelope, Finding, StageOutput, TaskInfo
from umbra.contracts.profile import Profile
from umbra.contracts.routine import Stage
from umbra.contracts.summary import SummaryOutput
from umbra.management import memory
from umbra.unified import config as cfg
from umbra.unified.events import add_event
from umbra.unified.store import new_id, now, to_cost

TERMINAL = ("BLOCKED", "FAILED", "CANCELLED", "SUCCEEDED")
DESIGN_DIR = "design"  # lo único que el diseñador puede tocar
FEEDBACK_CHARS = 4000
MERGEABLE_POLLS = 5  # espera a que GitHub calcule si el PR se puede integrar
MERGEABLE_WAIT_S = 2
DIFF_CHARS = 60_000
SEVERITY = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
ALERTS = {"run.waiting_approval": "espera tu aprobación",  # cuándo umbra necesita a la persona
          "run.blocked": "se detuvo y necesita tu decisión", "run.failed": "falló"}
DECIDED = {"waived": "no aplica", "deferred": "se hará después en otra tarea"}
RETRY_GUIDANCE = {
    "policy": "Deja los tests existentes y las rutas protegidas exactamente como están en la rama "
              "base (restáuralos si los cambiaste). Puedes añadir tests nuevos, en archivos nuevos "
              "o al final de uno existente, pero no quites ni cambies líneas existentes ni añadas "
              "skip/xfail/only.",
    "no_changes": "Esta vez implementa los cambios que pide la tarea.",
    "tests_failing": "Revisa el error de los tests con calma antes de cambiar código.",
}


@dataclass
class Round:
    stage: str
    ended_at: str
    findings: list[Finding]


class LeaseLost(Exception):
    pass


class EngineError(Exception):
    pass


@dataclass
class Outcome:
    status: str  # "next" | "rework" | "waiting" | "BLOCKED" | "FAILED"
    reason: str = ""
    code: str | None = None  # motivo estable; unified/explain.py lo traduce a lenguaje llano
    details: dict = field(default_factory=dict)


def conflict_feedback(files: list[str], still: bool = False) -> str:
    lead = ("Aún quedan marcadores de conflicto" if still else
            "La rama base cambió mientras trabajabas y la fusión dejó conflictos")
    return (f"{lead} en: {', '.join(files)}. Resuélvelos editando esos archivos: quita las "
            "líneas <<<<<<<, ======= y >>>>>>> y conserva los cambios de AMBOS lados (lo que ya "
            "está en la base y lo de esta tarea), salvo que se contradigan. No toques nada más; "
            "umbra hará el commit de la fusión.")


def uncommitted(wt: Path) -> list[str]:
    """Rutas con cambios sin confirmar en el workspace (nuevas incluidas)."""
    changed = git.run(wt, "diff", "--name-only", "HEAD").splitlines()
    new = git.run(wt, "ls-files", "--others", "--exclude-standard").splitlines()
    return [p.strip() for p in (*changed, *new) if p.strip()]


def agent_failure(result: AgentResult) -> Outcome:
    if result.timed_out:
        return Outcome("BLOCKED", result.error or "", "agent_timeout")
    return Outcome("FAILED", result.error or "el agente falló", "agent_error",
                   {"error": result.error})


class Engine:
    def __init__(self, root: Path, udir: Path, conn: sqlite3.Connection, project: dict,
                 guard: Callable[[], bool] = lambda: True, origin: str = "worker"):
        self.root, self.udir, self.conn, self.project = root, udir, conn, project
        self.guard, self.origin = guard, origin

    # ---------- utilidades ----------
    def run_row(self, run_id: str) -> sqlite3.Row:
        return self.conn.execute(
            "SELECT r.*, t.number, t.title, t.description, t.acceptance, t.scope,"
            " t.spec_dir, t.allowed_paths FROM run r"
            " JOIN task t ON t.id = r.task_id WHERE r.id = ?", (run_id,)).fetchone()

    def base_branch(self, run) -> str:
        """Rama base de esta ejecución: la de la spec si la tarea tiene una; si no, la del
        proyecto."""
        return run["base_branch"] or self.project_base()

    def project_base(self) -> str:
        return self.project.get("project", {}).get("base_branch", "main")

    def set_run(self, run_id: str, **fields) -> None:
        fields["updated_at"] = now()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE run SET {cols} WHERE id = ?", (*fields.values(), run_id))

    def transition(self, run_id: str, to: str, from_: tuple[str, ...] = ("RUNNING",)) -> bool:
        """Cambio de estado solo si nadie lo cambió antes (p. ej. un cancel del humano)."""
        marks = ",".join("?" * len(from_))
        cur = self.conn.execute(
            f"UPDATE run SET status = ?, updated_at = ? WHERE id = ? AND status IN ({marks})",
            (to, now(), run_id, *from_))
        return cur.rowcount == 1

    def event(self, run_id: str, type_: str, **payload) -> None:
        add_event(self.conn, run_id, type_, self.origin, **payload)
        if type_ in ("run.waiting_approval", "run.integrated") and telegram.settings(self.project):
            self.deliver(run_id)
        if type_ not in ALERTS:
            return
        run = self.run_row(run_id)
        if (self.project.get("notify", {}).get("desktop", True)
                and not notify.watch_open(self.conn)):  # un watch abierto ya avisa en pantalla
            reason = f" {payload['reason']}" if payload.get("reason") else ""
            notify.send(f"umbra · tarea {run['number']}",
                        f"{run['title']}: {ALERTS[type_]}.{reason}"[:250])
        if payload.get("code") == "design_review" and (tg := telegram.settings(self.project)):
            wt = Path(run["worktree"] or "")  # las pantallas, antes de la pregunta
            telegram.send_photos(tg, [wt / p for p in payload["details"].get("images", [])],
                                 f"Diseño de la tarea #{run['number']} {run['title']}")
        if mid := telegram.notify_run(self.project, run, type_, payload,
                                      self.root.name):  # al teléfono, siempre
            add_event(self.conn, run_id, "telegram.sent", self.origin, message_id=mid)

    def deliver(self, run_id: str) -> None:
        """Al teléfono: qué se hizo, cómo se comprobó y las capturas del navegador."""
        from umbra.routines import console
        try:
            run = self.run_row(run_id)
            text, photos = console.delivery(self.project, self.root, self.udir, self.conn, run)
            telegram.deliver(self.project, text, photos)
        except Exception as e:  # ponytail: la entrega al teléfono nunca frena la tarea
            add_event(self.conn, run_id, "telegram.error", self.origin, error=str(e))

    def last_event(self, run_id: str, *types: str) -> sqlite3.Row | None:
        marks = ",".join("?" * len(types))
        return self.conn.execute(
            f"SELECT payload, created_at FROM event WHERE run_id = ? AND type IN ({marks})"
            " ORDER BY id DESC LIMIT 1", (run_id, *types)).fetchone()

    def since(self, run_id: str, *types: str) -> str:
        row = self.last_event(run_id, *types)
        return row["created_at"] if row else ""

    def attempts_since(self, run_id: str, stage: str, since: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM attempt WHERE run_id = ? AND stage = ? AND started_at > ?"
            " AND status != 'interrupted'", (run_id, stage, since)).fetchone()[0]

    def ensure_lease(self) -> None:
        if not self.guard():
            raise LeaseLost("se perdió el lease del worker; no se publican cambios")

    def operation(self, key: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM operation WHERE operation_key = ?",
                                 (key,)).fetchone()

    def record_operation(self, key: str, kind: str, status: str, ref: str | None) -> None:
        self.conn.execute(
            "INSERT INTO operation (operation_key, kind, status, external_ref, updated_at)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT(operation_key) DO UPDATE SET"
            " status = excluded.status, external_ref = excluded.external_ref,"
            " updated_at = excluded.updated_at", (key, kind, status, ref, now()))

    def profile(self, name: str) -> Profile:
        """Perfil con acciones efectivas = perfil ∩ política del proyecto."""
        prof = cfg.load_profile(self.udir, name)
        allowed = self.project.get("policy", {}).get("actions")
        if allowed is not None:
            prof.actions = [a for a in prof.actions if a in allowed]
        return prof

    # ---------- ciclo principal ----------
    def process(self, run_id: str) -> str:
        run = self.run_row(run_id)
        if run["status"] in (*TERMINAL, "WAITING_APPROVAL", "PAUSED"):
            return run["status"]
        routine = cfg.load_routine(self.udir, run["routine"])
        if run["status"] != "RUNNING":
            if not self.transition(run_id, "RUNNING", ("QUEUED",)):
                return self.run_row(run_id)["status"]
            self.event(run_id, "run.started", routine=routine.name)
        wt = worktree.ensure(self.root, self.udir, run_id, run["branch"], run["base_sha"])
        if run["worktree"] != wt.as_posix():
            self.set_run(run_id, worktree=wt.as_posix())
        src = self.root / run["spec_dir"] if run["spec_dir"] else None
        if src and src.is_dir() and not src.is_symlink():
            # enlaces simbólicos omitidos (podrían apuntar fuera del repo); se copia lo que
            # falte aunque la carpeta ya exista, sin pisar lo del worktree
            shutil.copytree(src, wt / run["spec_dir"], dirs_exist_ok=True,
                            ignore=lambda d, names: [
                                n for n in names if (Path(d) / n).is_symlink()],
                            copy_function=lambda s, d: None if Path(d).exists()
                            else shutil.copy2(s, d))

        names = [s.name for s in routine.stages]
        i = names.index(run["stage"]) if run["stage"] in names else 0
        while i < len(routine.stages):
            stage = routine.stages[i]
            current = self.run_row(run_id)["status"]
            if current != "RUNNING":
                return self.stopped(run_id, current, stage.name)
            self.set_run(run_id, stage=stage.name)
            self.event(run_id, "stage.started", stage=stage.name)
            outcome = self.run_stage(run_id, stage, wt)
            if outcome.status == "waiting":
                return self.run_row(run_id)["status"]
            if outcome.status in ("BLOCKED", "FAILED"):
                if self.transition(run_id, outcome.status):
                    self.event(run_id, f"run.{outcome.status.lower()}", stage=stage.name,
                               reason=outcome.reason, code=outcome.code,
                               details=outcome.details)
                return self.run_row(run_id)["status"]
            self.event(run_id, "stage.completed", stage=stage.name)
            if outcome.status == "rework" and "build" in names:
                i = names.index("build")
                continue
            i += 1
        raise EngineError(f"la rutina {routine.name} terminó sin etapa ship")

    def stopped(self, run_id: str, status: str, stage: str) -> str:
        self.event(run_id, f"run.{status.lower()}.observed", stage=stage)
        if status == "CANCELLED":
            cleanup(self, run_id, "cancelado")
        return status

    def run_stage(self, run_id: str, stage: Stage, wt: Path) -> Outcome:
        if stage.name == "plan":
            return self.plan(run_id, stage, wt)
        if stage.name == "design":
            return self.design(run_id, stage, wt)
        if stage.name == "build":
            return self.build(run_id, stage, wt)
        if stage.name in ("review", "verify"):
            return self.check_stage(run_id, stage, wt)
        if stage.name == "scan":
            return self.scan(run_id, stage, wt)
        if stage.name == "ship":
            return self.ship(run_id, wt)
        raise EngineError(f"etapa '{stage.name}' no soportada")

    def interrupt_stale(self, run_id: str, stage: str) -> None:
        self.conn.execute("UPDATE attempt SET status = 'interrupted', ended_at = ?"
                          " WHERE run_id = ? AND stage = ? AND status = 'running'",
                          (now(), run_id, stage))

    # ---------- PLAN ----------
    def plan(self, run_id: str, stage: Stage, wt: Path) -> Outcome:
        self.interrupt_stale(run_id, "plan")
        profile = self.profile(stage.profile or "planner")
        attempt_id, result = self.agent_attempt(self.run_row(run_id), "plan", profile, wt)
        if not result.ok:
            return agent_failure(result)
        if result.output.status == "blocked":
            self.finish_attempt(attempt_id, "blocked")
            return Outcome("BLOCKED", "el planificador necesita aclaraciones: "
                           + "; ".join(result.output.questions), "agent_questions",
                           {"stage": "plan", "questions": result.output.questions})
        self.finish_attempt(attempt_id, "done")
        self.event(run_id, "plan.ready", plan=result.output.summary,
                   needs_design=bool(result.output.needs_design))
        return Outcome("next")

    # ---------- DESIGN ----------
    def design(self, run_id: str, stage: Stage, wt: Path) -> Outcome:
        """Si la tarea toca interfaz y hay diseñador (un perfil, p. ej. de un paquete), diseña
        en `design/` y espera el visto bueno de la persona antes de construir."""
        self.interrupt_stale(run_id, "design")
        plan = self.last_event(run_id, "plan.ready")
        if not (plan and json.loads(plan["payload"]).get("needs_design")):
            self.event(run_id, "design.skipped", reason="la tarea no toca la interfaz")
            return Outcome("next")
        try:
            profile = self.profile(stage.profile or "designer")
        except cfg.ConfigError:
            self.event(run_id, "design.skipped",
                       reason=f"no hay diseñador instalado (perfil «{stage.profile or 'designer'}»"
                              ", p. ej. desde un paquete: umbra pack sync)")
            return Outcome("next")
        run = self.run_row(run_id)
        attempt_id, result = self.agent_attempt(run, "design", profile, wt,
                                                self.design_feedback(run_id))
        if not result.ok:
            return agent_failure(result)
        if result.output.status == "blocked":
            self.finish_attempt(attempt_id, "blocked")
            return Outcome("BLOCKED", "el diseñador necesita aclaraciones: "
                           + "; ".join(result.output.questions), "agent_questions",
                           {"stage": "design", "questions": result.output.questions})
        outside = [p for p in uncommitted(wt) if not p.startswith(f"{DESIGN_DIR}/")]
        if outside:
            self.finish_attempt(attempt_id, "policy_violation")
            return Outcome("BLOCKED", f"el diseñador tocó archivos fuera de {DESIGN_DIR}/: "
                           + ", ".join(outside), "design_outside",
                           {"stage": "design", "files": outside})
        if git.has_changes(wt):
            git.commit_all(wt, f"umbra: diseño de {run['title']} (intento {attempt_id[:8]})")
        images = [p for p in result.output.images if (wt / p).is_file()]
        if not images:
            self.finish_attempt(attempt_id, "no_changes")
            return Outcome("BLOCKED", "el diseñador no dejó pantallas exportadas",
                           "design_empty", {"stage": "design"})
        self.finish_attempt(attempt_id, "done")
        for p in images:
            f = wt / p
            self.conn.execute(
                "INSERT INTO artifact (id, run_id, attempt_id, kind, path, checksum, tested_sha,"
                " created_at) VALUES (?, ?, ?, 'design', ?, ?, ?, ?)",
                (new_id(), run_id, attempt_id, f.as_posix(),
                 hashlib.sha256(f.read_bytes()).hexdigest(), git.head(wt), now()))
        self.event(run_id, "design.ready", images=images, summary=result.output.summary)
        if not stage.human_approval:
            self.event(run_id, "design.approved", images=images, auto=True)
            return Outcome("next")
        return Outcome("BLOCKED", "el diseño espera tu visto bueno", "design_review",
                       {"stage": "design", "images": images,
                        "summary": result.output.summary})

    def design_feedback(self, run_id: str) -> list[str]:
        """Lo que la persona pidió cambiar desde el último diseño."""
        since = self.since(run_id, "design.ready")
        asks = [json.loads(r["payload"])["text"] for r in self.conn.execute(
            "SELECT payload FROM event WHERE run_id = ? AND type = 'design.changes'"
            " AND created_at > ? ORDER BY id", (run_id, since))]
        if not asks:
            return []
        return ["La persona revisó tu diseño anterior (sigue en design/) y pide estos cambios; "
                "aplícalos sobre él, no empieces de cero: " + " ".join(asks)]

    def approved_design(self, run_id: str) -> list[str]:
        row = self.last_event(run_id, "design.approved")
        return json.loads(row["payload"]).get("images", []) if row else []

    # ---------- BUILD ----------
    def build(self, run_id: str, stage: Stage, wt: Path) -> Outcome:
        self.interrupt_stale(run_id, "build")
        if "test" not in commands.registered(self.project):
            return Outcome("BLOCKED", "no hay comando 'test' registrado en .umbra/project.toml",
                           "no_test_command")
        done = self.attempts_since(run_id, "build",
                                   self.since(run_id, "run.retried", "stage.rework",
                                              "stage.escalated"))
        rounds = self.finding_rounds(run_id)
        last_build = self.conn.execute(
            "SELECT MAX(ended_at) FROM attempt WHERE run_id = ? AND stage = 'build'",
            (run_id,)).fetchone()[0]
        # la última revisión está pendiente si ningún BUILD la atendió todavía (también tras un
        # retry: antes se perdía el hallazgo que bloqueó y se repetía el de la ronda anterior)
        pending = rounds[-1] if rounds and (last_build is None
                                            or rounds[-1].ended_at > last_build) else None
        feedback = [_describe(f) for f in pending.findings] if pending and done == 0 else []
        if not feedback and done == 0:
            feedback = self.retry_feedback(run_id)
        if done == 0:
            feedback += self.person_feedback(run_id)
        if history := [f for r in rounds if r is not pending for f in r.findings]:
            feedback.append("Hallazgos de revisiones anteriores de esta tarea, ya corregidos: no "
                            "los reintroduzcas.\n"
                            + "\n".join(f"- {_describe(f)}" for f in history))
        feedback = self.sync_with_base(run_id, wt) + feedback
        levels = [stage.profile or "builder", *stage.escalation]
        level = self.escalation_level(run_id)
        profile = self.profile(levels[min(level, len(levels) - 1)])
        test, conflicts = None, []
        attempt = done
        while attempt <= stage.max_fix_cycles:
            attempt += 1
            run = self.run_row(run_id)
            attempt_id, result = self.agent_attempt(run, "build", profile, wt, feedback)
            if not result.ok:
                return agent_failure(result)
            if result.output.status == "blocked":
                self.finish_attempt(attempt_id, "blocked")
                return Outcome("BLOCKED", "el agente necesita aclaraciones: "
                               + "; ".join(result.output.questions), "agent_questions",
                               {"stage": "build", "questions": result.output.questions})
            if conflicts := git.files_with_conflict_markers(wt, git.unmerged_files(wt)):
                self.finish_attempt(attempt_id, "conflicts")
                feedback = [conflict_feedback(conflicts, still=True)]
                continue
            if git.has_changes(wt):
                git.commit_all(wt, f"umbra: {run['title']} (intento {attempt_id[:8]})")
            head = git.head(wt)
            if head == run["base_sha"]:
                self.finish_attempt(attempt_id, "no_changes")
                return Outcome("BLOCKED", "el agente no produjo cambios", "no_changes")
            changes = git.changed_files(wt, run["base_sha"])
            edits = {p: git.edit_summary(wt, run["base_sha"], head, p)
                     for s, p in changes if s[0] == "M" and policy.is_test_file(p)}
            violations = policy.check_diff(
                changes,
                self.project.get("policy", {}).get("protected_paths", policy.DEFAULT_PROTECTED),
                edits, json.loads(run["allowed_paths"] or "[]"))
            if violations:
                self.finish_attempt(attempt_id, "policy_violation")
                return Outcome("BLOCKED", "política: " + "; ".join(v.message for v in violations),
                               "policy", {"violations": [v.as_dict() for v in violations]})
            test = commands.run_registered(self.conn, self.project, "test", wt, self.udir,
                                           run_id, attempt_id, tested_sha=head)
            self.event(run_id, "evidence.tests", attempt=attempt_id, sha=head,
                       exit_code=test["exit_code"], command=test["command"])
            if test["exit_code"] == 0:
                self.finish_attempt(attempt_id, "done")
                self.set_run(run_id, head_sha=head)
                return Outcome("next")
            self.finish_attempt(attempt_id, "tests_failed")
            feedback = [f"El comando `{test['command']}` terminó con exit code "
                        f"{test['exit_code']}:\n{test['output'][-FEEDBACK_CHARS:]}"]
            if attempt > stage.max_fix_cycles and level + 1 < len(levels):
                # se agotaron los ciclos con este perfil: sube al siguiente, más fuerte
                level += 1
                profile = self.profile(levels[level])
                self.event(run_id, "stage.escalated", stage="build", profile=profile.name,
                           reason="tests_failing")
                attempt = 0
        attempts = stage.max_fix_cycles + 1
        if conflicts:
            return Outcome("BLOCKED", f"conflictos con la rama base sin resolver tras {attempts}"
                           " intentos", "base_conflict_unresolved",
                           {"attempts": attempts, "files": conflicts})
        details = {"attempts": attempts}
        if test:
            details |= {"command": test["command"], "exit_code": test["exit_code"],
                        "output": test["output"][-1500:]}
        return Outcome("BLOCKED", f"los tests siguen fallando tras {attempts} intentos",
                       "tests_failing", details)

    def escalation_level(self, run_id: str) -> int:
        """Cuántas veces subió de perfil Construir desde el último reintento."""
        since = self.since(run_id, "run.retried")
        return self.conn.execute(
            "SELECT COUNT(*) FROM event WHERE run_id = ? AND type = 'stage.escalated'"
            " AND created_at > ?", (run_id, since)).fetchone()[0]

    def sync_with_base(self, run_id: str, wt: Path) -> list[str]:
        """Trae a la rama de la tarea lo integrado en la base desde que empezó.

        Devuelve retroalimentación para el agente si hay conflictos que resolver."""
        pending = git.unmerged_files(wt)  # un intento anterior quedó a mitad de resolver
        if pending:
            return [conflict_feedback(pending)]
        run = self.run_row(run_id)
        target = git.remote_base(wt, self.base_branch(run))
        if not target or target == run["base_sha"] or git.is_ancestor(wt, target):
            return []
        conflicts = git.merge(wt, target)
        self.set_run(run_id, base_sha=target)  # políticas y diffs se miden contra la base nueva
        if not conflicts:
            self.event(run_id, "base.synced", sha=target)
            return [f"La rama base avanzó y se fusionó en tu rama sin conflictos (commit "
                    f"{target[:10]}). Comprueba que todo sigue funcionando; no cambies nada que "
                    "no haga falta."]
        self.event(run_id, "base.conflict", sha=target, files=conflicts)
        return [conflict_feedback(conflicts)]

    def finding_rounds(self, run_id: str) -> list["Round"]:
        """Hallazgos bloqueantes de cada revisión de esta ejecución, en orden: su memoria."""
        routine = cfg.load_routine(self.udir, self.run_row(run_id)["routine"])
        block_on = {s.name: s.block_on for s in routine.stages}
        rounds: dict[str, Round] = {}
        # lo que la persona decidió (en esta o en otra tarea del repo) no cuenta, tampoco sus
        # repeticiones de otras rondas
        decided = memory.decided_messages(self.conn)
        for r in self.conn.execute(
                "SELECT a.id, a.stage, a.ended_at, f.severity, f.message, f.file, f.line, f.rule"
                " FROM attempt a JOIN finding f ON f.attempt_id = a.id"
                " WHERE a.run_id = ? AND a.status = 'findings' AND f.status = 'open'"
                " ORDER BY a.started_at, f.rowid",
                (run_id,)):
            if SEVERITY[r["severity"]] < SEVERITY[block_on.get(r["stage"], "high")]:
                continue
            if memory.normalize(r["message"]) in decided:
                continue
            rounds.setdefault(r["id"], Round(r["stage"], r["ended_at"], [])).findings.append(
                Finding(severity=r["severity"], message=r["message"], file=r["file"],
                        line=r["line"], rule=r["rule"]))
        return list(rounds.values())

    def decided_feedback(self, run_id: str) -> list[str]:
        """Lo que la persona decidió no corregir aquí: el revisor no debe volver a pedirlo."""
        rows = self.conn.execute(
            "SELECT f.status, f.message FROM finding f JOIN attempt a ON a.id = f.attempt_id"
            " WHERE a.run_id = ? AND f.status IN ('waived', 'deferred') ORDER BY f.rowid",
            (run_id,)).fetchall()
        if not rows:
            return []
        return ["La persona responsable ya decidió sobre estos hallazgos; no los vuelvas a "
                "reportar:\n" + "\n".join(f"- ({DECIDED[r['status']]}) {r['message']}"
                                          for r in rows)]

    def person_feedback(self, run_id: str) -> list[str]:
        """Lo que la persona decidió desde que se detuvo: respuestas a preguntas y rutas que
        autorizó cambiar (lo que la política bloqueaba)."""
        run = self.run_row(run_id)
        out = []
        if allowed := json.loads(run["allowed_paths"] or "[]"):
            out.append("La persona responsable autorizó cambiar estos archivos en esta tarea, "
                       "aunque la política normalmente los protege: " + ", ".join(allowed)
                       + ". Puedes modificarlos si la tarea lo requiere.")
        stopped = self.last_event(run_id, "run.blocked", "run.failed")
        since = stopped["created_at"] if stopped else ""
        answers = [json.loads(r["payload"])["answer"] for r in self.conn.execute(
            "SELECT payload FROM event WHERE run_id = ? AND type = 'task.answered'"
            " AND created_at > ? ORDER BY id", (run_id, since))]
        if answers:
            out.append("Respuesta de la persona responsable a tus preguntas: "
                       + " ".join(answers) + " Continúa con esa respuesta; no vuelvas a "
                       "preguntar lo mismo.")
        return out

    def retry_feedback(self, run_id: str) -> list[str]:
        """Tras un retry, el agente recibe por qué se detuvo el intento anterior en BUILD."""
        stopped = self.last_event(run_id, "run.blocked")
        retried = self.since(run_id, "run.retried")
        if not stopped or not retried or retried < stopped["created_at"]:
            return []
        payload = json.loads(stopped["payload"])
        if payload.get("stage") != "build":
            return []
        guidance = RETRY_GUIDANCE.get(payload.get("code"), "")
        return [f"Tu intento anterior en esta tarea se detuvo por esto: {payload.get('reason')}."
                f" {guidance}".strip()]

    # ---------- REVIEW / VERIFY ----------
    def check_stage(self, run_id: str, stage: Stage, wt: Path) -> Outcome:
        self.interrupt_stale(run_id, stage.name)
        default = "reviewer-strict" if stage.name == "review" else "verifier"
        profile = self.profile(stage.profile or default)
        run = self.run_row(run_id)
        previous = [f for r in self.finding_rounds(run_id) if r.stage == stage.name
                    for f in r.findings]
        dev = None
        if stage.name == "verify" and "browse" in profile.actions:
            try:  # la app de desarrollo, levantada sobre el workspace, para verla en el navegador
                dev = commands.start_background(self.project, "dev", wt, self.udir)
            except commands.NotReady as e:
                return Outcome("BLOCKED", str(e), "dev_not_ready")
            if dev:
                self.event(run_id, "dev.started", url=dev["url"], command=dev["command"])
        app_url = dev["url"] if dev else None
        try:
            attempt_id, result = self.agent_attempt(run, stage.name, profile, wt,
                                                    feedback=self.decided_feedback(run_id),
                                                    previous=previous, app_url=app_url)
            if not result.ok and not result.timed_out and stage.fallback_profile:
                # el agente falló por algo técnico (modelo saturado, sesión): otro perfil revisa
                self.event(run_id, "stage.fallback", stage=stage.name, failed=profile.name,
                           profile=stage.fallback_profile, error=result.error)
                profile = self.profile(stage.fallback_profile)
                attempt_id, result = self.agent_attempt(run, stage.name, profile, wt,
                                                        feedback=self.decided_feedback(run_id),
                                                        previous=previous, app_url=app_url)
        finally:
            if dev:
                commands.stop_background(dev)
                self.event(run_id, "dev.stopped", url=dev["url"])
        if not result.ok:
            return agent_failure(result)
        if git.has_changes(wt):  # una etapa de solo lectura no puede tocar el workspace
            self.finish_attempt(attempt_id, "policy_violation")
            return Outcome("BLOCKED", f"{stage.name} modificó el workspace", "readonly_modified",
                           {"stage": stage.name, "agent": profile.agent})
        return self.judge(run_id, stage, attempt_id, result.output.findings, wt)

    # ---------- SCAN (determinista, sin agente) ----------
    def scan(self, run_id: str, stage: Stage, wt: Path) -> Outcome:
        self.interrupt_stale(run_id, "scan")
        run = self.run_row(run_id)
        attempt_no = self.conn.execute(
            "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM attempt WHERE run_id = ?"
            " AND stage = 'scan'", (run_id,)).fetchone()[0]
        attempt_id = new_id()
        self.conn.execute(
            "INSERT INTO attempt (id, run_id, stage, attempt_no, profile, agent, status,"
            " started_at) VALUES (?, ?, 'scan', ?, 'scan', 'umbra', 'running', ?)",
            (attempt_id, run_id, attempt_no, now()))
        head = run["head_sha"]
        findings = secrets.scan_diff(git.run(wt, "diff", f"{run['base_sha']}..{head}"))
        found_secrets = list(findings)
        for name in self.project.get("scan", {}).get("commands", []):
            res = commands.run_registered(self.conn, self.project, name, wt, self.udir,
                                          run_id, attempt_id, tested_sha=head)
            self.event(run_id, "evidence.scan", command=res["command"],
                       exit_code=res["exit_code"], sha=head)
            if res["exit_code"] != 0:
                findings.append(Finding(
                    severity="high", rule=f"sast:{name}",
                    message=f"`{res['command']}` terminó con exit {res['exit_code']}:\n"
                            f"{res['output'][-FEEDBACK_CHARS:]}"))
        if found_secrets:  # un secreto confirmado bloquea siempre: sin retrabajo ni excepción
            self.record_findings(attempt_id, findings)
            self.finish_attempt(attempt_id, "secrets")
            return Outcome("BLOCKED", "secretos en el diff: "
                           + "; ".join(_describe(f) for f in found_secrets), "secrets",
                           {"findings": [f.model_dump() for f in found_secrets]})
        return self.judge(run_id, stage, attempt_id, findings, wt)

    def record_findings(self, attempt_id: str, findings: list[Finding]) -> None:
        for f in findings:
            self.conn.execute(
                "INSERT INTO finding (id, attempt_id, severity, rule, file, line, message)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id(), attempt_id, f.severity, f.rule, f.file, f.line, f.message))

    def judge(self, run_id: str, stage: Stage, attempt_id: str,
              findings: list[Finding], wt: Path | None = None) -> Outcome:
        """Hallazgos ≥ block_on devuelven la tarea a BUILD hasta agotar ciclos; después, si hay
        árbitro, decide él; si Construir puede escalar de perfil, otra ronda con uno más fuerte."""
        self.record_findings(attempt_id, findings)
        severe = [f for f in findings if SEVERITY[f.severity] >= SEVERITY[stage.block_on]]
        # lo que la persona ya decidió («no aplica» o «para después») en el repo no frena
        remembered = memory.decided_messages(self.conn)
        blocking = [f for f in severe if memory.normalize(f.message) not in remembered]
        self.finish_attempt(attempt_id, "findings" if blocking else "done")
        self.event(run_id, f"{stage.name}.result", findings=len(findings),
                   blocking=len(blocking), remembered=len(severe) - len(blocking))
        if not blocking:
            return Outcome("next")
        cycles = self.attempts_since(run_id, stage.name, self.since(run_id, "run.retried"))
        if cycles > stage.max_fix_cycles:
            if stage.arbiter and wt is not None and not self.attempts_since(
                    run_id, "arbiter", self.since(run_id, "run.retried")):
                return self.arbitrate(run_id, stage, wt, blocking)
            build = self.build_stage(run_id)
            if build and self.escalation_level(run_id) < len(build.escalation):
                nxt = build.escalation[self.escalation_level(run_id)]
                self.event(run_id, "stage.escalated", stage="build", profile=nxt,
                           reason="findings")
                self.event(run_id, "stage.rework", stage=stage.name,
                           feedback=[_describe(f) for f in blocking])
                return Outcome("rework")
            return Outcome("BLOCKED", f"{len(blocking)} hallazgos bloqueantes en {stage.name} "
                           f"tras {cycles} revisiones", "findings",
                           {"stage": stage.name, "cycles": cycles,
                            "findings": [f.model_dump() for f in blocking]})
        self.event(run_id, "stage.rework", stage=stage.name,
                   feedback=[_describe(f) for f in blocking])
        return Outcome("rework")

    def build_stage(self, run_id: str) -> Stage | None:
        routine = cfg.load_routine(self.udir, self.run_row(run_id)["routine"])
        return routine.stage("build")

    def arbitrate(self, run_id: str, stage: Stage, wt: Path,
                  blocking: list[Finding]) -> Outcome:
        """Un tercer agente, de solo lectura, decide qué hallazgos siguen en pie."""
        run = self.run_row(run_id)
        profile = self.profile(stage.arbiter)
        self.event(run_id, "stage.arbiter", stage=stage.name, profile=profile.name,
                   findings=len(blocking))
        attempt_id, result = self.agent_attempt(
            run, "arbiter", profile, wt, previous=blocking,
            feedback=[f"Constructor y revisor llevan {stage.max_fix_cycles + 1} rondas sin "
                      "acordar estos hallazgos. Decide tú cuáles son reales y bloquean de verdad; "
                      "devuelve solo esos en `findings` (vacío si ninguno lo es)."])
        if not result.ok:
            return agent_failure(result)
        if git.has_changes(wt):
            self.finish_attempt(attempt_id, "policy_violation")
            return Outcome("BLOCKED", "el árbitro modificó el workspace", "readonly_modified",
                           {"stage": "arbiter", "agent": profile.agent})
        kept = [f for f in result.output.findings
                if SEVERITY[f.severity] >= SEVERITY[stage.block_on]]
        self.record_findings(attempt_id, kept)
        self.finish_attempt(attempt_id, "findings" if kept else "done")
        self.event(run_id, "arbiter.result", kept=len(kept), dropped=len(blocking) - len(kept))
        if not kept:
            return Outcome("next")
        self.event(run_id, "stage.rework", stage=stage.name,
                   feedback=[_describe(f) for f in kept])
        return Outcome("rework")

    # ---------- intento de agente ----------
    def agent_attempt(self, run, stage: str, profile: Profile, wt: Path,
                      feedback: list[str] | None = None,
                      previous: list[Finding] | None = None,
                      output_model: type[BaseModel] = StageOutput,
                      diff: str | None = None, app_url: str | None = None
                      ) -> tuple[str, AgentResult]:
        attempt_no = self.conn.execute(
            "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM attempt WHERE run_id = ? AND stage = ?",
            (run["id"], stage)).fetchone()[0]
        attempt_id = new_id()
        self.conn.execute(
            "INSERT INTO attempt (id, run_id, stage, attempt_no, profile, agent, status,"
            " started_at) VALUES (?, ?, ?, ?, ?, ?, 'running', ?)",
            (attempt_id, run["id"], stage, attempt_no, profile.name, profile.agent, now()))
        self.event(run["id"], "attempt.started", stage=stage, attempt=attempt_id,
                   profile=profile.name, agent=profile.agent, n=attempt_no)
        plan = self.last_event(run["id"], "plan.ready")
        if diff is None and stage in ("review", "verify", "arbiter") and run["head_sha"]:
            diff = git.run(wt, "diff", f"{run['base_sha']}..{run['head_sha']}")[:DIFF_CHARS]
        envelope = Envelope(
            run_id=run["id"], stage=stage, attempt_id=attempt_id, input_sha=git.head(wt),
            task=TaskInfo(number=run["number"], title=run["title"],
                          description=run["description"],
                          acceptance=json.loads(run["acceptance"]),
                          scope=json.loads(run["scope"])),
            plan=json.loads(plan["payload"])["plan"] if plan and stage in ("build", "summary")
            else None,
            diff=diff, feedback=feedback or [], findings=previous or [],
            project_notes=memory.project_notes(self.root, self.udir), app_url=app_url,
            design=self.approved_design(run["id"]) if stage in ("build", "verify") else [])
        shots = None
        if app_url:  # las capturas caen fuera del workspace: no ensucian el diff
            shots = self.udir / "artifacts" / f"{attempt_id}-shots"
            shots.mkdir(parents=True, exist_ok=True)
            envelope.screenshots_dir = shots.as_posix()
        allowed = [c["run"] for c in commands.registered(self.project).values()
                   if not c.get("background")]  # los servidores los levanta umbra, no el agente
        req = AgentRun(envelope, profile, wt,
                       self.udir / "artifacts" / f"{attempt_id}-{stage}.jsonl", allowed,
                       output_model=output_model)
        result = get_adapter(profile.agent, self.udir).run(req)
        self.conn.execute(
            "INSERT INTO usage (id, attempt_id, agent, model, input_tokens, output_tokens, cost,"
            " estimated, invocation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id(), attempt_id, profile.agent, result.model, result.input_tokens,
             result.output_tokens, to_cost(result.cost), int(result.estimated), attempt_id))
        self.conn.execute("UPDATE attempt SET session_id = ? WHERE id = ?",
                          (result.session_id, attempt_id))
        if shots:
            self.record_screenshots(run, attempt_id, shots)
        if not result.ok:
            self.finish_attempt(attempt_id, "timeout" if result.timed_out else "error")
        unpriced = (result.input_tokens or 0) + (result.output_tokens or 0) \
            if result.estimated and not result.cost else 0
        self.event(run["id"], "attempt.finished", stage=stage, attempt=attempt_id, ok=result.ok,
                   cost=to_cost(result.cost), unpriced_tokens=unpriced, error=result.error,
                   summary=result.output.summary if result.output else None)
        return attempt_id, result

    def record_screenshots(self, run, attempt_id: str, shots: Path) -> None:
        """Cada captura del navegador es evidencia ligada al SHA verificado."""
        files = sorted(f for f in shots.iterdir() if f.is_file())
        for f in files:
            self.conn.execute(
                "INSERT INTO artifact (id, run_id, attempt_id, kind, path, checksum, tested_sha,"
                " created_at) VALUES (?, ?, ?, 'screenshot', ?, ?, ?, ?)",
                (new_id(), run["id"], attempt_id, f.as_posix(),
                 hashlib.sha256(f.read_bytes()).hexdigest(), run["head_sha"], now()))
        if files:
            self.event(run["id"], "evidence.screenshots", attempt=attempt_id, count=len(files),
                       dir=shots.as_posix())

    def finish_attempt(self, attempt_id: str, status: str) -> None:
        self.conn.execute("UPDATE attempt SET status = ?, ended_at = ? WHERE id = ?",
                          (status, now(), attempt_id))

    # ---------- SHIP ----------
    def ship(self, run_id: str, wt: Path) -> Outcome:
        run = self.run_row(run_id)
        head = git.head(wt)
        if head != run["head_sha"]:
            return Outcome("BLOCKED", "el SHA actual no es el evaluado; reintenta desde build",
                           "stale_sha")
        base = self.base_branch(run)
        self.summarize(run_id, wt)

        push_key = f"{run_id}:push:{head}"
        if not self.operation(push_key):
            self.ensure_lease()
            if git.remote_branch_sha(wt, run["branch"]) != head:
                git.push(wt, run["branch"])
            self.record_operation(push_key, "push", "done", head)
            self.event(run_id, "git.pushed", branch=run["branch"], sha=head)

        pr_key = f"{run_id}:pr"
        if not self.operation(pr_key):
            self.ensure_lease()
            pr = gh.find_pr(wt, run["branch"]) or gh.create_pr(
                wt, run["branch"], base, f"umbra #{run['number']}: {run['title']}",
                self.pr_body(run))
            self.record_operation(pr_key, "pr", "done", json.dumps(pr))
            self.event(run_id, "pr.opened", number=pr["number"], url=pr["url"])
        self.set_run(run_id, stage="ship")
        if base != self.project_base():  # rama de spec: se integra sola (constitution VII)
            return self.integrate_in_spec(run_id, wt, head, base)
        if self.transition(run_id, "WAITING_APPROVAL"):
            self.event(run_id, "run.waiting_approval", sha=head)
        return Outcome("waiting")

    def integrate_in_spec(self, run_id: str, wt: Path, head: str, base: str) -> Outcome:
        """Tareas de una spec: pasadas todas las etapas, el PR se integra en la rama de la spec
        sin aprobación; la persona aprueba la spec completa al final."""
        run = self.run_row(run_id)
        pr = self.pr_info(run_id)
        merge_key = f"{run_id}:merge:{head}"
        if not self.operation(merge_key):
            self.ensure_lease()
            current = gh.view_pr(wt, pr["number"])
            if current["state"] != "MERGED":
                try:
                    gh.merge_pr(wt, pr["number"], head)
                except gh.GhError as e:
                    return Outcome("BLOCKED", f"no se pudo integrar en {base}: {e}",
                                   "base_conflict", {"pr": pr["number"], "url": pr["url"]})
            final = gh.view_pr(wt, pr["number"])
            merge_sha = (final.get("mergeCommit") or {}).get("oid")
            if final["state"] != "MERGED" or not merge_sha:
                return Outcome("FAILED", f"el proveedor no confirma el merge en {base}",
                               "merge_unconfirmed")
            self.record_operation(merge_key, "merge", "done", merge_sha)
        if self.transition(run_id, "SUCCEEDED"):
            self.conn.execute("UPDATE task SET status = 'done', updated_at = ? WHERE id = ?",
                              (now(), run["task_id"]))
            self.event(run_id, "run.integrated", branch=base, pr=pr["number"],
                       merge_sha=self.operation(merge_key)["external_ref"])
            worktree.remove(self.root, wt)
            self.spec_ready(run["spec_dir"], base)
        return Outcome("waiting")

    def spec_ready(self, spec_dir: str, branch: str) -> None:
        """Con todas las tareas de la spec integradas en su rama, abre el PR de la spec a la
        base y avisa una sola vez: la spec espera la aprobación de la persona."""
        left = self.conn.execute("SELECT COUNT(*) FROM task WHERE spec_dir = ? AND status NOT IN"
                                 " ('done', 'dropped')", (spec_dir,)).fetchone()[0]
        key = f"spec:{spec_dir}:pr"
        if left or self.operation(key):
            return
        self.ensure_lease()
        base = self.project_base()
        pr = gh.find_pr(self.root, branch) or gh.create_pr(
            self.root, branch, base, f"umbra spec {Path(spec_dir).name}",
            self.spec_pr_body(spec_dir))
        self.record_operation(key, "pr", "done", json.dumps(pr))
        add_event(self.conn, None, "spec.ready", self.origin, spec_dir=spec_dir, branch=branch,
                  number=pr["number"], url=pr["url"])
        if self.project.get("notify", {}).get("desktop", True) \
                and not notify.watch_open(self.conn):
            notify.send(f"umbra · spec {Path(spec_dir).name}",
                        f"todas sus historias están integradas: espera tu aprobación ({pr['url']})")
        telegram.notify_spec(self.project, spec_dir, pr["url"], self.root.name)

    def spec_pr_body(self, spec_dir: str) -> str:
        lines = [f"Spec `{spec_dir}` construida por umbra-engine. Historias integradas en su "
                 "rama tras tests, revisión, verificación y política:", ""]
        for t in self.conn.execute("SELECT t.number, t.title, r.id AS run_id FROM task t"
                                   " JOIN run r ON r.id = (SELECT id FROM run WHERE task_id = t.id"
                                   " ORDER BY created_at DESC LIMIT 1)"
                                   " WHERE t.spec_dir = ? ORDER BY t.number", (spec_dir,)):
            pr = self.pr_info(t["run_id"]) or {}
            lines.append(f"- #{t['number']} {t['title']}"
                         + (f" (PR #{pr['number']})" if pr else ""))
        lines += ["", "Se integra solo con `umbra approve --spec`."]
        return "\n".join(lines)

    def summarize(self, run_id: str, wt: Path) -> None:
        """Explicación conceptual para quien aprueba (y para el PR). Nunca frena la entrega."""
        run = self.run_row(run_id)
        ready = self.last_event(run_id, "summary.ready")
        if (not self.project.get("report", {}).get("summary", True)
                or ready and json.loads(ready["payload"])["sha"] == run["head_sha"]):
            return
        self.interrupt_stale(run_id, "summary")
        told = []
        for r in self.conn.execute("SELECT payload FROM event WHERE run_id = ?"
                                   " AND type = 'attempt.finished' ORDER BY id", (run_id,)):
            p = json.loads(r["payload"])
            if p.get("ok") and p.get("summary") and p.get("stage") in ("build", "verify"):
                told.append(f"{p['stage']}: {p['summary']}")
        fixed = [f for r in self.finding_rounds(run_id) for f in r.findings]
        try:
            attempt_id, result = self.agent_attempt(
                run, "summary", self.profile("summarizer"), wt, feedback=told, previous=fixed,
                output_model=SummaryOutput,
                diff=git.diff_stat(wt, run["base_sha"], run["head_sha"]))
        except Exception as e:  # ponytail: sin resumen la vista usa los datos exactos
            self.conn.execute("UPDATE attempt SET status = 'error', ended_at = ? WHERE run_id = ?"
                              " AND stage = 'summary' AND status = 'running'", (now(), run_id))
            self.event(run_id, "summary.failed", error=str(e))
            return
        if not result.ok:
            self.event(run_id, "summary.failed", error=result.error)
            return
        self.finish_attempt(attempt_id, "done")
        self.event(run_id, "summary.ready", sha=run["head_sha"], summary=result.output.summary,
                   observations=result.output.observations)

    def pr_body(self, run) -> str:
        acceptance = "\n".join(f"- {a}" for a in json.loads(run["acceptance"])) or "-"
        tests = self.conn.execute(
            "SELECT command, exit_code, tested_sha FROM artifact WHERE run_id = ?"
            " AND kind = 'command:test' ORDER BY created_at DESC LIMIT 1", (run["id"],)).fetchone()
        evidence = "-"
        if tests:
            evidence = (f"`{tests['command']}` → exit {tests['exit_code']}"
                        f" sobre `{tests['tested_sha']}`")
        ready = self.last_event(run["id"], "summary.ready")
        what = f"**Qué se hizo**\n{json.loads(ready['payload'])['summary']}\n\n" if ready else ""
        return (f"{what}**Tarea**\n{run['description']}\n\n"
                f"**Criterios de aceptación**\n{acceptance}\n\n"
                f"**Evidencia**\n{evidence}\n\nGenerado por umbra-engine (run `{run['id']}`). "
                "Se integra solo con `umbra approve`.")

    def pr_info(self, run_id: str) -> dict | None:
        op = self.operation(f"{run_id}:pr")
        return json.loads(op["external_ref"]) if op else None


def _describe(f: Finding) -> str:
    where = f" ({f.file}:{f.line})" if f.file else ""
    return f"[{f.severity}] {f.message}{where}"


# ---------- decisiones humanas ----------
class ApprovalError(Exception):
    pass


def approve(engine: Engine, run_id: str, actor: str) -> dict:
    run = engine.run_row(run_id)
    if run["status"] != "WAITING_APPROVAL":
        raise ApprovalError(f"la ejecución está en {run['status']}, no en WAITING_APPROVAL")
    pr = engine.pr_info(run_id)
    wt = Path(run["worktree"])
    current = gh.view_pr(wt, pr["number"])
    local = git.head(wt) if wt.exists() else run["head_sha"]
    if current["headRefOid"] != run["head_sha"] or local != run["head_sha"]:
        raise ApprovalError("hay commits posteriores al SHA evaluado; vuelve a verificar con "
                            f"`umbra retry {run['number']}`")
    if current["state"] != "MERGED":
        mergeable = current.get("mergeable")
        for _ in range(MERGEABLE_POLLS):  # GitHub lo calcula en diferido tras cada cambio
            if mergeable not in (None, "UNKNOWN"):
                break
            time.sleep(MERGEABLE_WAIT_S)
            mergeable = gh.view_pr(wt, pr["number"]).get("mergeable")
        if mergeable == "CONFLICTING":
            raise base_conflict(engine, run, pr)
    engine.conn.execute(
        "INSERT OR IGNORE INTO approval (id, run_id, head_sha, decision, actor, created_at)"
        " VALUES (?, ?, ?, 'approved', ?, ?)", (new_id(), run_id, run["head_sha"], actor, now()))
    engine.event(run_id, "approval.approved", sha=run["head_sha"], actor=actor)
    merge_key = f"{run_id}:merge:{run['head_sha']}"
    if current["state"] != "MERGED" and not engine.operation(merge_key):
        try:
            gh.merge_pr(wt, pr["number"], run["head_sha"])
        except gh.GhError as e:
            if re.search(r"conflict|not mergeable", str(e), re.IGNORECASE):
                raise base_conflict(engine, run, pr) from e
            raise
        engine.record_operation(merge_key, "merge", "requested", str(pr["number"]))
    final = gh.view_pr(wt, pr["number"])
    merge_sha = (final.get("mergeCommit") or {}).get("oid")
    if final["state"] != "MERGED" or not merge_sha:
        raise ApprovalError(f"el proveedor no confirma el merge (estado {final['state']})")
    engine.record_operation(merge_key, "merge", "done", merge_sha)
    engine.set_run(run_id, status="SUCCEEDED")
    engine.conn.execute("UPDATE task SET status = 'done', updated_at = ? WHERE id = ?",
                        (now(), run["task_id"]))
    engine.event(run_id, "run.succeeded", merge_sha=merge_sha, pr=pr["number"])
    worktree.remove(engine.root, wt)
    return {"run_id": run_id, "merge_sha": merge_sha, "pr": pr["url"]}


def base_conflict(engine: Engine, run, pr: dict) -> "ApprovalError":
    """La base cambió y el PR ya no encaja: se detiene la tarea (sin registrar aprobación)."""
    engine.set_run(run["id"], status="BLOCKED")
    engine.event(run["id"], "run.blocked", stage="ship", code="base_conflict",
                 reason="el PR tiene conflictos con la rama base",
                 details={"pr": pr["number"], "url": pr["url"]})
    return ApprovalError(f"no se integró: la rama base cambió y el PR #{pr['number']} tiene "
                         f"conflictos. Ponla al día con `umbra retry {run['number']} --from "
                         "build` (el agente resuelve el conflicto y se vuelve a verificar).")


def reject(engine: Engine, run_id: str, actor: str, reason: str) -> dict:
    run = engine.run_row(run_id)
    if run["status"] in TERMINAL:
        raise ApprovalError(f"la ejecución ya terminó ({run['status']})")
    if run["head_sha"]:
        engine.conn.execute(
            "INSERT OR IGNORE INTO approval (id, run_id, head_sha, decision, actor, created_at)"
            " VALUES (?, ?, ?, 'rejected', ?, ?)",
            (new_id(), run_id, run["head_sha"], actor, now()))
    engine.set_run(run_id, status="CANCELLED")
    engine.event(run_id, "approval.rejected", actor=actor, reason=reason)
    cleanup(engine, run_id, f"Rechazado en umbra: {reason}")
    return {"run_id": run_id, "status": "CANCELLED"}


def cancel(engine: Engine, run_id: str) -> str:
    """RUNNING: se marca y el worker limpia en el siguiente punto seguro. Resto: limpia ya."""
    run = engine.run_row(run_id)
    if run["status"] in ("SUCCEEDED", "CANCELLED"):
        raise ApprovalError(f"la ejecución ya terminó ({run['status']})")
    was_running = run["status"] == "RUNNING"
    engine.set_run(run_id, status="CANCELLED")
    engine.event(run_id, "run.cancel_requested", stage=run["stage"])
    if not was_running:
        cleanup(engine, run_id, "cancelado")
    return "CANCELLED"


def cleanup(engine: Engine, run_id: str, reason: str) -> None:
    run = engine.run_row(run_id)
    pr = engine.pr_info(run_id)
    if pr:
        try:
            if gh.view_pr(engine.root, pr["number"])["state"] == "OPEN":
                gh.close_pr(engine.root, pr["number"], reason)
        except gh.GhError as e:
            engine.event(run_id, "cleanup.error", error=str(e))
    if run["worktree"]:
        worktree.remove(engine.root, Path(run["worktree"]))
    engine.event(run_id, "run.cleaned")
