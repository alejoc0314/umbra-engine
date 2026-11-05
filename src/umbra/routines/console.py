"""La consola de umbra en el teléfono: lo que hace `umbra watch`, contado en texto para Telegram.

Solo compone texto (Markdown ligero que `telegram.send` convierte) y llama a las operaciones de
`service`; la conversación de spec (`SpecTalk`) reproduce sin pantalla la lógica de
`cli/spec_screen.py`."""

import json
import re
from pathlib import Path

from umbra import service
from umbra.chat import elicit
from umbra.chat.stream import Stream
from umbra.cli import agent_story
from umbra.unified import clock
from umbra.unified import explain as ex
from umbra.unified.events import add_event, events_for
from umbra.unified.store import new_id, now

ORIGIN = "telegram"
TAIL = 25
REVIEWS = ("spec_review", "plan_review")
GROUPS = ("Te necesitan", "En marcha", "Por hacer", "Terminadas")


def _group(exp: ex.Explanation) -> str:
    if exp.state.startswith(("Detenida", "Falló", "Espera tu")):
        return GROUPS[0]
    if exp.kind in ("queued", "running", "paused"):
        return GROUPS[1]
    if exp.kind in ("draft", "ready", "waiting_deps"):
        return GROUPS[2]
    return GROUPS[3]


# ---------- ver ----------
def tasks_text(ctx: service.Ctx) -> str:
    rows = ctx.conn.execute("SELECT * FROM task WHERE status != 'dropped' ORDER BY number"
                            ).fetchall()
    if not rows:
        return "Sin tareas todavía. /tarea título | criterio, o /spec idea."
    groups: dict[str, list[str]] = {g: [] for g in GROUPS}
    for t in rows:
        exp = ex.explain_number(ctx.conn, ctx.udir, t)
        groups[_group(exp)].append(f"#{t['number']} {t['title']} — {ex.short(exp)}")
    return "\n\n".join(f"**{g}**\n" + "\n".join(lines) for g, lines in groups.items() if lines)


def explain_text(ctx: service.Ctx, n: int) -> str:
    exp = ex.explain_number(ctx.conn, ctx.udir, service.task_row(ctx, n))
    out = [f"**#{n} {exp.title}** · {exp.state}", exp.headline]
    if exp.why:
        out.append(exp.why)
    out += [f"- {d}" for d in exp.details]
    if exp.actions:
        out.append("\nPuedes:")
        out += [f"- {a.what}" + (f" (`{a.command}`)" if a.command else "") for a in exp.actions]
    return "\n".join(out)


def log_text(ctx: service.Ctx, n: int, tail: int = TAIL) -> str:
    run = service.latest_run(ctx, n)
    lines = []
    for e in events_for(ctx.conn, run["id"]):
        if (line := ex.narrate(e)) is not None:
            lines.append(f"{clock.hhmm(e['created_at'])} {line.strip()}")
    return f"**Registro de #{n}** (últimas {tail})\n" + "\n".join(lines[-tail:])


def _mark(ok: bool | None) -> str:
    return "✓" if ok else "·" if ok is None else "✗"


def report_text(rep: dict) -> str:
    """El informe de aprobación (`umbra evidence`) en texto: qué se hizo y cómo se comprobó."""
    out = [f"**Tarea {rep['number']} · {rep['title']}** · {rep['state']}", "",
           "**Qué se hizo**", rep["what"] or "Todavía no hay trabajo terminado."]
    if rep.get("what_by"):
        out.append(f"(lo cuenta {rep['what_by']})")
    out += ["", "**Cómo se comprobó**"]
    t = rep["tests"]
    if not t:
        out.append("· Pruebas: todavía no se ejecutaron")
    elif t["ok"]:
        n = t["counts"].get("passed")
        where = "sobre la versión final" if t["current"] else "sobre una versión anterior"
        out.append(f"{_mark(t['current'])} Pruebas: {f'{n} pasan' if n else 'pasan'} {where}")
    else:
        out.append("✗ Pruebas: fallan")
    crit = rep["criteria"]
    total = len(crit["items"])
    if not crit["checked"]:
        out.append(f"· Criterios de aceptación ({total}): todavía sin verificar")
    elif crit["unmet"]:
        out.append(f"✗ Criterios de aceptación: {len(crit['unmet'])} de {total} sin cumplir")
        out += [f"   ✗ {u}" for u in crit["unmet"]]
    else:
        out.append(f"✓ Criterios de aceptación: {total} de {total} cumplidos")
    if rep["review_rounds"]:
        pending = [o for o in rep["observations"] if not o["resolved"]]
        state = ("sin observaciones importantes" if not rep["observations"] else
                 f"{len(pending)} sin resolver" if pending else "todas corregidas")
        out.append(f"{_mark(not pending)} Revisión independiente: {rep['review_rounds']} "
                   f"{'ronda' if rep['review_rounds'] == 1 else 'rondas'} · {state}")
    if rep["scan"]:
        ok = rep["scan"] == "done"
        out.append(f"{_mark(ok)} Seguridad: " + ("sin secretos ni problemas" if ok
                                                 else "hay problemas"))
    if rep.get("design"):
        out.append(f"✓ Maquetado sobre el diseño que aprobaste ({rep['design']} pantalla"
                   f"{'s' if rep['design'] > 1 else ''})")
    if rep.get("screenshots"):
        out.append(f"✓ Visto en el navegador: {rep['screenshots']} captura"
                   f"{'s' if rep['screenshots'] > 1 else ''} (van adjuntas)")
    ch = rep["changes"]
    out += ["", "**Cambios** " + " · ".join(f"{k} {v[0]}" for k, v in ch.items())
            + f" (+{sum(v[1] for v in ch.values())} −{sum(v[2] for v in ch.values())} líneas)",
            f"**Costo** {ex.spend_text(rep['cost'], rep['unpriced_tokens'])} · "
            f"{rep['minutes']} min · {rep['attempts']} intentos"]
    if rep.get("pr"):
        out.append(f"PR: {rep['pr']}")
    return "\n".join(out)


def evidence_text(ctx: service.Ctx, n: int) -> str:
    return report_text(service.evidence(ctx, n)["report"])


def changes_text(ctx: service.Ctx, n: int) -> str:
    data = service.evidence(ctx, n)
    stat = data["diff_stat"] or "(sin cambios evaluados todavía)"
    pr = data.get("pr") or {}
    return f"**Cambios de #{n}**\n```\n{stat}\n```" + (f"\n{pr['url']}" if pr else "")


def agent_text(ctx: service.Ctx, n: int, tail: int = TAIL) -> str:
    row = ctx.conn.execute(
        "SELECT a.id, a.stage, a.status FROM attempt a JOIN run r ON r.id = a.run_id"
        " JOIN task t ON t.id = r.task_id WHERE t.number = ? AND a.agent != 'umbra'"
        " ORDER BY (a.status = 'running') DESC, a.started_at DESC LIMIT 1", (n,)).fetchone()
    if not row:
        return f"La tarea {n} no tiene actividad de agente todavía."
    path = ctx.udir / "artifacts" / f"{row['id']}-{row['stage']}.jsonl"
    if not path.exists():
        return "El agente aún no ha escrito nada."
    lines = agent_story.lines(path.read_text(encoding="utf-8", errors="replace"))
    stage = ex.STAGES.get(row["stage"], row["stage"])
    return f"**Agente de #{n}** ({stage}, {ex.ATTEMPTS.get(row['status'], row['status'])})\n" \
        + "\n".join(lines[-tail:])


def findings_text(ctx: service.Ctx, n: int) -> str:
    items = service.pending_findings(ctx, n) or service.open_findings(ctx, n)
    if not items:
        return f"La tarea {n} no tiene hallazgos abiertos."
    out = [f"**Hallazgos de #{n}** (/noaplica {n} o /despues {n} deciden todos)"]
    out += [f"{i}. [{f['severity']}] {f['message']}" + (f" ({f['file']}:{f['line']})"
                                                       if f.get("file") else "")
            for i, f in enumerate(items, 1)]
    return "\n".join(out)


def delivery(project: dict, root: Path, udir: Path, conn, run) -> tuple[str, list[str]]:
    """Qué se manda al teléfono cuando una tarea queda lista: informe y capturas del navegador."""
    ctx = service.Ctx(root, udir, conn, project)
    data = service.evidence(ctx, run["number"])
    head = f"umbra · {root.name} · tarea #{run['number']} lista\n\n"
    photos = [a["path"] for a in data["artifacts"]
              if a["kind"] == "screenshot" and a["tested_sha"] == run["head_sha"]]
    return head + report_text(data["report"]), photos


# ---------- hacer ----------
def add_task(ctx: service.Ctx, title: str, acceptance: list[str], draft: bool = False,
             origin: str = ORIGIN) -> int:
    number = ctx.conn.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM task").fetchone()[0]
    ctx.conn.execute(
        "INSERT INTO task (id, number, title, acceptance, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id(), number, title, json.dumps(acceptance, ensure_ascii=False),
         "draft" if draft else "accepted", now(), now()))
    add_event(ctx.conn, None, "task.added", origin, number=number, title=title)
    return number


def parse_task(text: str) -> tuple[str, list[str]]:
    """«título | criterio 1 | criterio 2» → (título, criterios)."""
    parts = [p.strip() for p in text.split("|")]
    return parts[0], [p for p in parts[1:] if p]


def plan_from_spec(ctx: service.Ctx, spec_path: Path) -> str:
    """`umbra plan`: guarda la spec y el proponente deja tareas en borrador."""
    import getpass

    from umbra.management import planning
    body = spec_path.read_text(encoding="utf-8")
    spec_id, version, _ = planning.save_spec(ctx.conn, body, getpass.getuser())
    try:
        proposal = planning.propose(ctx.root, ctx.udir, ctx.conn, body, version, "proposer")
    except planning.PlanningError as e:
        return f"No se pudo planificar: {e}"
    if proposal.questions:
        return "El proponente necesita aclaraciones:\n" + "\n".join(
            f"- {q}" for q in proposal.questions)
    numbers = planning.insert_proposals(ctx.conn, spec_id, proposal)
    return (f"Tareas en borrador: {numbers}. /tareas las muestra; /aceptar N las acepta "
            "(o /noche para aceptar y encolar todas).")


# ---------- la conversación de spec, sin pantalla ----------
class SpecTalk:
    """Una conversación de requisitos (`umbra spec new/resume`) llevada por mensajes.

    `say(text, buttons)` es cómo habla con la persona; los botones llevan `sq:<i>` (opción),
    `sq:otra` y `sr:approve|changes|discard`. `pending` dice qué espera: una respuesta a una
    pregunta («question»/«other»), la revisión de un punto de control («review») o el texto de
    los cambios («changes»)."""

    def __init__(self, root: Path, conv_id: str, idea: str, exe: str = "claude"):
        self.root, self.conv_id, self.idea, self.exe = root, conv_id, idea, exe
        self.stream: Stream | None = None
        self.stream_phase: str | None = None
        self.pending: tuple | None = None
        self.question: elicit.Question | None = None
        self.busy = False
        self.lock: tuple[str, int] | None = None
        self.done = False

    # --- arranque / cierre ---
    @classmethod
    def start(cls, ctx: service.Ctx, idea: str, say, exe: str = "claude") -> "SpecTalk":
        conv_id = service.spec_new(ctx, idea, ORIGIN)
        talk = cls(ctx.root, conv_id, idea, exe)
        talk.lock = service.spec_lock(ctx, conv_id)
        say(f"Spec nueva sobre «{idea}». Voy con la primera fase; te escribo en cuanto tenga "
            "algo o una pregunta.")
        talk.turn(elicit.phase_message("specify", idea, root=ctx.root), say)
        return talk

    @classmethod
    def resume(cls, ctx: service.Ctx, ref: str | None, say, exe: str = "claude") -> "SpecTalk":
        row = service.spec_resume_target(ctx, ref)
        talk = cls(ctx.root, row["id"], row["idea"], exe)
        talk.lock = service.spec_lock(ctx, row["id"])
        phase = elicit.phase_of(ctx.conn, row["id"])
        say(f"Retomo la spec «{row['idea']}» en la fase {phase}.")
        if phase in REVIEWS:
            talk.review(say)
        else:
            talk.pending = ("text",)
            say("Escríbeme lo que quieras decirle al asistente para seguir.")
        return talk

    def close(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None
        if self.lock:
            ctx = service.load(self.root)
            try:
                service.spec_unlock(ctx, self.lock)
            finally:
                ctx.conn.close()
            self.lock = None
        self.done = True

    # --- turnos ---
    def _stream_for(self, ctx: service.Ctx, phase: str) -> Stream:
        if self.stream and self.stream_phase == phase:
            return self.stream
        if self.stream:
            self.stream.close()
        path = ctx.udir / "artifacts" / "spec" / f"settings-{phase}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(elicit.phase_settings(phase, service.spec_script())),
                        encoding="utf-8")
        sid = ctx.conn.execute("SELECT session_id FROM conversation WHERE id = ?",
                               (self.conv_id,)).fetchone()["session_id"]
        self.stream, self.stream_phase = Stream(ctx.root, path, resume=sid, exe=self.exe), phase
        return self.stream

    def do(self, fn) -> None:
        """Un paso de la persona (respuesta, opción, decisión) y todo lo que desencadena, con
        la conversación marcada como ocupada hasta el final."""
        self.busy = True
        try:
            fn()
        finally:
            self.busy = False

    def turn(self, message: str, say) -> None:
        self.pending = None

        def run():
            ctx = service.load(self.root)
            try:
                phase = elicit.phase_of(ctx.conn, self.conv_id)
                res = elicit.run_turn(ctx.conn, ctx.root, self.conv_id,
                                      self._stream_for(ctx, phase), message,
                                      elicit.max_cost_usd(ctx.config))
            except Exception as e:  # ponytail: un turno roto no tumba el puente
                res = elicit.TurnResult(error=True, text=f"No se pudo hablar con claude: {e}")
            finally:
                ctx.conn.close()
            if res.error and self.stream:
                self.stream.close()
                self.stream = None
            self.after(res, say)

        self.do(run)

    def after(self, res: elicit.TurnResult, say) -> None:
        if res.text:
            say(res.text)
        for w in res.warnings:
            say(f"Aviso: {w}")
        ctx = service.load(self.root)
        try:
            phase = elicit.phase_of(ctx.conn, self.conv_id)
        finally:
            ctx.conn.close()
        if res.error:
            self.pending = ("text",)
            say("Error del asistente. Escribe de nuevo para reintentar.")
        elif res.paused:
            self.pending = ("text",)
        elif res.question:
            self.ask(res.question, say)
        elif phase == "specify":
            self.go("next" if "[NEEDS CLARIFICATION]" in res.text else "skip_clarify", say)
        elif phase in ("clarify", "plan"):
            self.go("next", say)
        elif phase == "tasks":
            self.make_tasks(say)
        else:
            self.pending = ("text",)

    def go(self, event: str, say) -> None:
        ctx = service.load(self.root)
        try:
            phase = elicit.advance(ctx.conn, self.conv_id, event)
        finally:
            ctx.conn.close()
        if phase in REVIEWS:
            self.review(say)
        elif phase == "done":
            say("Conversación terminada.")
            self.close()
        else:
            self.turn(elicit.phase_message(phase, self.idea, root=self.root), say)

    def ask(self, q: elicit.Question, say) -> None:
        self.question, self.pending = q, ("question",)
        order = sorted(range(len(q.options)), key=lambda i: i != q.recommended)
        buttons = [[(q.options[i] + (" (recomendada)" if i == q.recommended else ""),
                     f"sq:{i}")] for i in order]
        buttons.append([("Otra respuesta…", "sq:otra")])
        say(q.question, buttons)

    def review(self, say) -> None:
        self.pending = ("review",)
        ctx = service.load(self.root)
        try:
            phase = elicit.phase_of(ctx.conn, self.conv_id)
        finally:
            ctx.conn.close()
        what = "la spec" if phase == "spec_review" else "el plan"
        folder = elicit.spec_dir_from_feature(self.root)
        say(f"Revisa {what}" + (f" en {folder.as_posix()}" if folder else "")
            + ". /spec_ver te manda el archivo. ¿Qué decides?",
            [[("✅ Aprobar", "sr:approve"), ("✏️ Pedir cambios", "sr:changes")],
             [("🗑 Descartar", "sr:discard")]])

    # --- lo que dice la persona ---
    def option(self, which: str, say) -> None:
        q = self.question
        if not q or self.pending != ("question",):
            return say("No hay una pregunta pendiente.")
        if which == "otra":
            self.pending = ("other",)
            return say("Escribe tu respuesta.")
        try:
            answer = q.options[int(which)]
        except (ValueError, IndexError):
            return say("Esa opción no existe.")
        say(f"Tú: {answer}")
        self.turn(answer, say)

    def decide(self, choice: str, say) -> None:
        if self.pending != ("review",):
            return say("No hay un punto de control pendiente.")
        ctx = service.load(self.root)
        try:
            phase = elicit.phase_of(ctx.conn, self.conv_id)
            if choice == "approve":
                if phase == "plan_review":
                    folder = elicit.spec_dir_from_feature(ctx.root)
                    if folder is None:
                        return say("Falta .specify/feature.json; pide cambios para que el "
                                   "asistente lo cree.")
                    elicit.set_spec_dir(ctx.conn, self.conv_id, folder)
                    if self.lock:
                        service.spec_unlock(ctx, self.lock)
                        self.lock = service.spec_lock(ctx, self.conv_id)
                service.spec_event(ctx, "approved", self.conv_id, ORIGIN, phase=phase)
            elif choice == "changes":
                self.pending = ("changes",)
                return say("¿Qué cambios pides? Escríbelos en un mensaje.")
            elif choice == "discard":
                elicit.advance(ctx.conn, self.conv_id, "discard")
                service.spec_event(ctx, "discarded", self.conv_id, ORIGIN)
                self.close()
                return say("Conversación descartada: no se crearán tareas.")
            else:
                return say("No entiendo esa decisión.")
        finally:
            ctx.conn.close()
        say("Aprobado.")
        self.go("approve", say)

    def text(self, text: str, say) -> None:
        kind = (self.pending or ("text",))[0]
        if kind == "review":
            kind = "changes"
        if kind == "changes":
            ctx = service.load(self.root)
            try:
                phase = elicit.phase_of(ctx.conn, self.conv_id)
                service.spec_event(ctx, "changes", self.conv_id, ORIGIN, phase=phase,
                                   comment=text)
                prev = elicit.advance(ctx.conn, self.conv_id, "changes")
            finally:
                ctx.conn.close()
            say(f"Tú: cambios pedidos → vuelvo a la fase {prev}.")
            return self.turn(elicit.phase_message(prev, comment=text), say)
        say(f"Tú: {text}")
        self.turn(text, say)

    def make_tasks(self, say) -> None:
        ctx = service.load(self.root)
        try:
            row = ctx.conn.execute("SELECT spec_dir FROM conversation WHERE id = ?",
                                   (self.conv_id,)).fetchone()
            try:
                result = service.spec_tasks(ctx, Path(row["spec_dir"]), origin=ORIGIN)
            except service.OpError as e:
                self.pending = ("text",)
                return say(f"No se pudieron crear las tareas: {e}")
        finally:
            ctx.conn.close()
        made = result["created"] or result["existing"]
        say(f"Tareas en borrador: {made}. /tareas las muestra; /aceptar N las acepta, o "
            "/noche para aceptar y encolar todas.")
        self.go("next", say)

    def spec_file(self) -> Path | None:
        folder = elicit.spec_dir_from_feature(self.root)
        if not folder:
            return None
        ctx = service.load(self.root)
        try:
            phase = elicit.phase_of(ctx.conn, self.conv_id)
        finally:
            ctx.conn.close()
        name = "plan.md" if phase in ("plan", "plan_review", "tasks", "done") else "spec.md"
        path = self.root / folder / name
        return path if path.exists() else None


def spec_ref_dir(text: str) -> str | None:
    """«/spec_seguir 3» o «/spec_seguir specs/003-x» → referencia para spec_resume_target."""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else None


NUMBER = re.compile(r"^/\w+\s+#?(\d+)(?:\s+(.*))?$", re.S)
