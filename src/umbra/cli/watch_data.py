"""Lo que `umbra watch` muestra, calculado fuera del hilo de la pantalla.

`Loader` tiene su propia conexión y se usa desde un solo worker a la vez. Antes de consultar nada
mira `PRAGMA data_version`: si nadie escribió desde la última vez y la persona no cambió de tarea ni
de pestaña, no hay nada que recalcular (salvo el registro del agente en curso, que se sigue por
tamaño de archivo). Cuando sí hay cambios, lee cada tabla una sola vez (nunca una consulta por
tarea) y devuelve una instantánea que la pantalla aplica de forma incremental.
"""

import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from rich.console import Console

from umbra import service
from umbra.actions import git
from umbra.blocks.lease import _ts
from umbra.cli import agent_story, theme
from umbra.management import memory
from umbra.unified import clock
from umbra.unified import explain as ex
from umbra.unified.store import _unpriced, data_version, open_store

ATTENTION = {"BLOCKED", "FAILED", "WAITING_APPROVAL"}
WORKING = {"RUNNING", "QUEUED", "PAUSED"}
GROUPS = ("Te necesitan", "En marcha", "Por hacer", "Terminadas")
PATCH_CHARS = 60_000
AGENT_TAIL = 400
TEST_TAIL = 60
EVIDENCE_WIDTH = 96


def group_of(run_status: str | None, task_status: str) -> int:
    if run_status in ATTENTION:
        return 0
    if run_status in WORKING:
        return 1
    if task_status in ("done", "dropped") or run_status in ("SUCCEEDED", "CANCELLED"):
        return 3
    return 2


@dataclass
class TaskRow:
    number: int
    title: str
    situation: str
    cost: str
    state: str  # clave de color: theme.STATE_KEYS
    run_status: str | None
    group: int
    progress: list[tuple[str, str]]  # (marca, clave de color)
    elapsed: str


@dataclass
class AttemptRow:
    cells: tuple[str, str, str, str, str, str]
    started_at: str | None
    running: bool


@dataclass
class HeaderInfo:
    worker_alive: bool
    queued: int
    spend: str
    attention: int
    tasks: int


@dataclass
class Snapshot:
    selected: int | None
    run_id: str | None
    header: HeaderInfo | None = None
    tasks: list[TaskRow] = field(default_factory=list)
    explanation: ex.Explanation | None = None
    explanation_key: tuple | None = None
    specs: list[str] = field(default_factory=list)
    attempts: list[AttemptRow] = field(default_factory=list)
    log: list[tuple[str, str]] = field(default_factory=list)  # (marca UTC, texto)
    log_reset: bool = False
    last_seq: int = 0
    evidence: tuple[str, str] | None = None  # (informe ANSI, salida de pruebas)
    changes: tuple[list[tuple[str, str, str]], str, bool] | None = None  # archivos, parche
    agent: list[str] | None = None  # líneas nuevas del relato del agente
    agent_reset: bool = False
    agent_empty: str | None = None  # por qué no hay relato
    decision: dict = field(default_factory=dict)  # qué puede decidir la persona ahora
    memory: str | None = None  # aprendido.md, solo cuando ese panel está a la vista


MARKS = {"hecho": ("●", "done"), "en curso": ("▶", "running"), "detenida": ("■", "blocked"),
         "falló": ("✗", "failed"), "cancelada": ("○", "cancelled"), "en pausa": ("‖", "paused"),
         "pendiente": ("○", "queued")}


def _log_line(event, raw: bool) -> str | None:
    payload = json.loads(event["payload"])
    if raw:
        extra = " ".join(f"{k}={v}" for k, v in payload.items()
                         if k not in ("trace", "summary", "details", "plan") and v is not None)
        return f"{clock.hhmmss(event['created_at'])} {event['type']} {extra}"
    if (line := ex.narrate({"type": event["type"], "payload": payload})) is None:
        return None
    return f"{clock.hhmm(event['created_at'])} {line}"


def report_ansi(data: dict, width: int = EVIDENCE_WIDTH, raw: bool = False) -> str:
    """El informe de evidencia con sus colores (ANSI), para pintarlo tal cual en la pantalla."""
    from umbra.cli.routines import render_evidence, render_report
    console = Console(file=io.StringIO(), width=width, force_terminal=True,
                      color_system="truecolor", record=True)
    (render_evidence if raw else render_report)(console, data)
    return console.export_text(styles=True)


class Loader:
    def __init__(self, udir: Path):
        self.udir, self.root = udir, udir.parent
        self.conn = open_store(udir, same_thread=False)  # solo la usa el worker exclusivo
        self.version: int | None = None
        self.explained: dict[int, tuple[tuple, ex.Explanation]] = {}
        self.seen: tuple | None = None  # (selected, raw, pestaña)
        self.extras: dict[tuple, object] = {}  # (tipo, run_id, head) → calculado
        self.agent_path: Path | None = None
        self.agent_offset = 0
        self.width = EVIDENCE_WIDTH  # ancho al que se envuelve el informe (lo fija la pantalla)

    def close(self) -> None:
        self.conn.close()

    def load(self, selected: int | None, raw: bool, shown_run: str | None, last_seq: int,
             force: bool = False, want: str = "situation") -> Snapshot | None:
        """None = nada cambió desde la última instantánea."""
        conn = self.conn
        version = data_version(conn)
        if selected is None:
            selected = self._default_selection()
        unchanged = version == self.version and self.seen == (selected, raw, want)
        self.version, self.seen = version, (selected, raw, want)
        if unchanged and not force:
            return self._agent_only(selected) if want == "agent" else None
        run = self._run(selected) if selected is not None else None
        run_id = run["id"] if run else None
        snap = Snapshot(selected, run_id)
        snap.tasks = self._tasks()
        snap.header = self._header(snap.tasks)
        if selected is not None:
            task = conn.execute("SELECT * FROM task WHERE number = ?", (selected,)).fetchone()
            if task:
                snap.explanation_key, snap.explanation = self._explain(task)
                snap.decision = self._spec_decision(task)
        snap.specs = [ex.spec_line(p) for p in
                      service.spec_progress(service.Ctx(self.root, self.udir, conn, {}))]
        if run:
            snap.decision = {**snap.decision, **self._decision(run)}
            snap.attempts = self._attempts(run_id)
            snap.log_reset = run_id != shown_run
            since = 0 if snap.log_reset else last_seq
            snap.last_seq = since
            for e in conn.execute("SELECT seq, type, payload, created_at FROM event"
                                  " WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, since)):
                if (text := _log_line(e, raw)) is not None:
                    snap.log.append((e["created_at"], text))
                snap.last_seq = e["seq"]
        else:
            snap.log_reset = shown_run is not None
        if want == "evidence":
            snap.evidence = self._evidence(selected, run)
        elif want == "changes":
            snap.changes = self._changes(run)
        elif want == "agent":
            self._agent(selected, snap, reset=True)
        elif want == "memory":
            snap.memory = memory.load(self.udir, limit=10 ** 9)
        return snap

    # ---------- consultas ----------
    def _default_selection(self) -> int | None:
        marks = ",".join("?" * len(ATTENTION))
        row = self.conn.execute(
            f"SELECT t.number FROM run r JOIN task t ON t.id = r.task_id WHERE r.status IN"
            f" ({marks}) ORDER BY t.number LIMIT 1", tuple(ATTENTION)).fetchone()
        row = row or self.conn.execute("SELECT t.number FROM run r JOIN task t ON t.id = r.task_id"
                                       " ORDER BY r.updated_at DESC LIMIT 1").fetchone()
        row = row or self.conn.execute("SELECT number FROM task ORDER BY number LIMIT 1").fetchone()
        return row[0] if row else None

    def _run(self, number: int):
        return self.conn.execute("SELECT r.* FROM run r JOIN task t ON t.id = r.task_id"
                                 " WHERE t.number = ? ORDER BY r.created_at DESC LIMIT 1",
                                 (number,)).fetchone()

    def _header(self, tasks: list[TaskRow]) -> HeaderInfo:
        conn = self.conn
        alive = conn.execute("SELECT 1 FROM lease WHERE name = 'worker' AND expires_at > ?",
                             (_ts(),)).fetchone() is not None
        queued = conn.execute("SELECT COUNT(*) FROM run WHERE status = 'QUEUED'").fetchone()[0]
        total, tokens = Decimal(0), 0
        for u in conn.execute("SELECT cost, estimated, input_tokens, output_tokens FROM usage"):
            total += Decimal(u["cost"] or 0)
            tokens += _unpriced(u)
        return HeaderInfo(alive, queued, ex.spend_text(total, tokens),
                          sum(t.group == 0 for t in tasks), len(tasks))

    def _tasks(self) -> list[TaskRow]:
        conn = self.conn
        spend: dict[str, tuple] = {}
        for u in conn.execute("SELECT a.run_id, u.cost, u.estimated, u.input_tokens,"
                              " u.output_tokens FROM usage u JOIN attempt a"
                              " ON a.id = u.attempt_id"):
            cost, tokens = spend.get(u["run_id"], (Decimal(0), 0))
            spend[u["run_id"]] = (cost + Decimal(u["cost"] or 0), tokens + _unpriced(u))
        last_event = dict(conn.execute("SELECT run_id, MAX(created_at) FROM event"
                                       " WHERE run_id IS NOT NULL GROUP BY run_id").fetchall())
        rows = []
        for t in conn.execute(
                "SELECT t.*, r.id AS run_id, r.status AS run_status, r.created_at AS run_at"
                " FROM task t LEFT JOIN run r ON r.id = (SELECT id FROM run WHERE task_id = t.id"
                " ORDER BY created_at DESC LIMIT 1) ORDER BY t.number"):
            cost, tokens = spend.get(t["run_id"], (Decimal(0), 0))
            _, exp = self._explain(t)
            if t["run_id"]:
                end = None if t["run_status"] in WORKING else last_event.get(t["run_id"])
                elapsed = clock.duration(t["run_at"], end)
            else:
                elapsed = "-"
            rows.append(TaskRow(
                t["number"], ex.task_title(t), ex.short(exp),
                ex.spend_text(cost, tokens) if t["run_id"] else "$0.00",
                theme.state_key(t["run_status"] or t["status"]), t["run_status"],
                group_of(t["run_status"], t["status"]),
                [MARKS.get(mark, ("○", "queued")) for _, mark in exp.progress], elapsed))
        rows.sort(key=lambda r: (r.group, r.number))
        return rows

    def _explain(self, task) -> tuple[tuple, ex.Explanation]:
        """La explicación se recalcula solo si la tarea o su última ejecución cambiaron."""
        key = tuple(self.conn.execute(
            "SELECT t.status, t.revision, r.id, r.status, r.stage, r.updated_at,"
            " (SELECT MAX(id) FROM event e WHERE e.run_id = r.id) FROM task t"
            " LEFT JOIN run r ON r.id = (SELECT id FROM run WHERE task_id = t.id"
            "  ORDER BY created_at DESC LIMIT 1) WHERE t.id = ?", (task["id"],)).fetchone())
        cached = self.explained.get(task["number"])
        if cached and cached[0] == key:
            return cached
        exp = ex.explain_number(self.conn, self.udir, task)
        self.explained[task["number"]] = (key, exp)
        return key, exp

    def _attempts(self, run_id: str) -> list[AttemptRow]:
        out = []
        for a in self.conn.execute("SELECT a.*, u.cost, u.estimated, u.input_tokens,"
                                   " u.output_tokens FROM attempt a LEFT JOIN usage u"
                                   " ON u.attempt_id = a.id WHERE a.run_id = ?"
                                   " ORDER BY a.started_at", (run_id,)):
            running = a["status"] == "running"
            out.append(AttemptRow((
                ex.STAGES.get(a["stage"], a["stage"]), str(a["attempt_no"]),
                ex.AGENTS.get(a["agent"], a["agent"] or "-"),
                ex.ATTEMPTS.get(a["status"], a["status"]),
                clock.duration(a["started_at"], a["ended_at"]),
                ex.spend_text(a["cost"], _unpriced(a)) if a["cost"] else "-"),
                a["started_at"], running))
        return out

    def _spec_decision(self, task) -> dict:
        """La spec de la tarea y si espera la aprobación de la persona (tecla I)."""
        if not task["spec_dir"]:
            return {}
        pr = service.spec_pr(service.Ctx(self.root, self.udir, self.conn, {}), task["spec_dir"])
        return {"spec": task["spec_dir"], "spec_pr": pr,
                "spec_waiting": bool(pr and pr["state"] == "waiting")}

    def _decision(self, run) -> dict:
        """Lo que la persona puede decidir sobre esta ejecución: código del bloqueo, rutas que la
        política frenó, preguntas del agente, cuántas esperan integrarse, hallazgos abiertos."""
        conn = self.conn
        out = {"code": None, "paths": [], "questions": [], "waiting": 0, "open_findings": 0,
               "takeover": False}
        if run["status"] in ("BLOCKED", "FAILED", "WAITING_APPROVAL"):
            # lo abrió en su editor desde el último reintento: la tecla o pasa a «retomar»
            last = conn.execute("SELECT type FROM event WHERE run_id = ? AND type IN"
                                " ('takeover.opened', 'run.retried') ORDER BY id DESC LIMIT 1",
                                (run["id"],)).fetchone()
            out["takeover"] = bool(last) and last[0] == "takeover.opened"
        if run["status"] in ("BLOCKED", "FAILED"):
            last = conn.execute("SELECT payload FROM event WHERE run_id = ? AND type IN"
                                " ('run.blocked', 'run.failed') ORDER BY id DESC LIMIT 1",
                                (run["id"],)).fetchone()
            payload = json.loads(last[0]) if last else {}
            out["code"] = payload.get("code")
            out["questions"] = payload.get("details", {}).get("questions", [])
            for r in conn.execute("SELECT payload FROM event WHERE run_id = ? AND"
                                  " type = 'run.blocked' ORDER BY id", (run["id"],)):
                p = json.loads(r[0])
                if p.get("code") == "policy":
                    out["paths"] += [v["path"] for v in p.get("details", {}).get("violations", [])
                                     if v.get("path") and v["path"] not in out["paths"]]
        if run["status"] == "WAITING_APPROVAL":
            out["waiting"] = conn.execute(
                "SELECT COUNT(*) FROM task t JOIN run r ON r.id = (SELECT id FROM run WHERE"
                " task_id = t.id ORDER BY created_at DESC LIMIT 1)"
                " WHERE r.status = 'WAITING_APPROVAL'").fetchone()[0]
        out["open_findings"] = conn.execute(
            "SELECT COUNT(*) FROM finding f JOIN attempt a ON a.id = f.attempt_id"
            " WHERE a.run_id = ? AND f.status = 'open'", (run["id"],)).fetchone()[0]
        return out

    # ---------- bajo demanda ----------
    def _evidence(self, number: int | None, run) -> tuple[str, str] | None:
        if not run:
            return None
        key = ("evidence", run["id"], run["head_sha"], run["status"], self.version, self.width)
        if key in self.extras:
            return self.extras[key]
        ctx = service.Ctx(self.root, self.udir, self.conn, service.load(self.root).config)
        try:
            data = service.evidence(ctx, number)
        except service.OpError as e:
            return (str(e), "")
        ansi = report_ansi(data, width=self.width)
        tests = self.conn.execute(
            "SELECT path FROM artifact WHERE run_id = ? AND kind = 'command:test'"
            " ORDER BY created_at DESC LIMIT 1", (run["id"],)).fetchone()
        tail = ""
        if tests:
            try:
                lines = Path(tests["path"]).read_text(encoding="utf-8",
                                                      errors="replace").splitlines()
                tail = "\n".join(lines[-TEST_TAIL:])
            except OSError:
                tail = ""
        self.extras = {k: v for k, v in self.extras.items() if k[1] == run["id"]} | {
            key: (ansi, tail)}
        return ansi, tail

    def _changes(self, run) -> tuple[list[tuple[str, str, str]], str, bool] | None:
        if not run or not run["head_sha"]:
            return None
        key = ("changes", run["id"], run["head_sha"])
        if key in self.extras:
            return self.extras[key]
        try:
            ctx = service.Ctx(self.root, self.udir, self.conn, service.load(self.root).config)
            numstat, patch = service.run_diff(ctx, run)
        except (git.GitError, service.OpError) as e:
            return ([], f"No se pudo calcular el diff: {e}", False)
        files = []
        for line in numstat.splitlines():
            parts = line.split("\t", 2)
            if len(parts) == 3:
                files.append((parts[2], parts[0], parts[1]))
        truncated = len(patch) > PATCH_CHARS
        result = (files, patch[:PATCH_CHARS], truncated)
        self.extras[key] = result
        return result

    # ---------- relato del agente ----------
    def _agent_file(self, number: int | None) -> tuple[Path | None, str | None]:
        """Registro del intento en curso o, si no, del último con agente."""
        if number is None:
            return None, "No hay tarea seleccionada."
        row = self.conn.execute(
            "SELECT a.id, a.stage, a.status FROM attempt a JOIN run r ON r.id = a.run_id"
            " JOIN task t ON t.id = r.task_id WHERE t.number = ? AND a.agent != 'umbra'"
            " ORDER BY (a.status = 'running') DESC, a.started_at DESC LIMIT 1",
            (number,)).fetchone()
        if not row:
            return None, "Esta tarea no tiene actividad de agente todavía."
        path = self.udir / "artifacts" / f"{row['id']}-{row['stage']}.jsonl"
        if not path.exists():
            return None, "El agente aún no ha escrito nada."
        return path, None

    def _agent(self, number: int | None, snap: Snapshot, reset: bool) -> None:
        path, why = self._agent_file(number)
        if path != self.agent_path or reset:
            self.agent_path, self.agent_offset = path, 0
            snap.agent_reset = True
        if path is None:
            snap.agent, snap.agent_empty = [], why
            return
        try:
            with path.open("rb") as f:
                f.seek(self.agent_offset)
                raw = f.read()
        except OSError:
            snap.agent, snap.agent_empty = [], "No se pudo leer el registro del agente."
            return
        self.agent_offset += len(raw)
        text = raw.decode("utf-8", errors="replace")
        snap.agent = agent_story.lines(text)
        if snap.agent_reset:
            snap.agent = snap.agent[-AGENT_TAIL:]

    def _agent_only(self, number: int | None) -> Snapshot | None:
        """Sin cambios en la base: solo mira si el registro del agente creció."""
        path, _ = self._agent_file(number)
        if path is None or path != self.agent_path:
            return None
        try:
            size = path.stat().st_size
        except OSError:
            return None
        if size <= self.agent_offset:
            return None
        snap = Snapshot(number, None)
        self._agent(number, snap, reset=False)
        return snap


def now_utc() -> datetime:
    return datetime.now(UTC)
