"""`umbra watch`: la consola de umbra. Lista por atención, detalle en pestañas y acciones.

Cada acción llama a umbra.service, el mismo código que la CLI, y avisa con el comando
equivalente. Lo irreversible (aprobar, rechazar, cancelar...) siempre pide confirmación.

Nada lento corre en el hilo de la pantalla: un worker exclusivo lee la base (watch_data.Loader) y
la vista aplica la instantánea de forma incremental; evidencia, cambios y el relato del agente se
calculan solo cuando su pestaña está a la vista.
"""

import io
import json
import os
import socket
from collections.abc import Callable
from pathlib import Path

from rich.console import Console, Group
from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.coordinate import Coordinate
from textual.widgets import ContentSwitcher, DataTable, Footer, Header, RichLog, Static

from umbra import service
from umbra.blocks import lease
from umbra.cli import theme
from umbra.cli.explain import renderable
from umbra.cli.modals import AskText, Confirm, PickOne, PickStage, TextView
from umbra.cli.watch_data import Loader, Snapshot
from umbra.unified import clock, project, version
from umbra.unified import explain as ex
from umbra.unified.store import open_store

__all__ = ["AskText", "Confirm", "PickOne", "PickStage", "TextView", "WatchApp"]

ORIGIN = "watch"
WATCH_ALERTS = {"WAITING_APPROVAL": "espera tu aprobación",
                "BLOCKED": "se detuvo y necesita tu decisión", "FAILED": "falló"}
WITH_RUN = {"queued", "running", "paused", "blocked", "failed", "waiting_approval",
            "succeeded", "cancelled"}
# acción → situaciones de la tarea en las que tiene sentido
AVAILABLE = {
    "accept": {"draft", "blocked", "failed"},  # aceptar un borrador o autorizar un cambio
    "drop": {"draft", "ready", "waiting_deps"},
    "run": {"ready", "blocked", "failed"},
    "new": {"blocked", "failed"},
    "pause": {"queued", "running", "paused"},
    "cancel": {"queued", "running", "paused", "blocked", "failed", "waiting_approval"},
    "evidence": WITH_RUN,
    "findings": WITH_RUN,
    "approve": {"waiting_approval"},
    "approve_all": {"waiting_approval"},
    "reject": {"waiting_approval"},
    "open": {"blocked", "failed", "waiting_approval"},
    "approve_spec": WITH_RUN | {"draft", "ready", "waiting_deps", "dropped"},
    "night": WITH_RUN | {"draft", "ready", "waiting_deps", "dropped"},
}
LABELS = {"accept": "Aceptar / autorizar", "drop": "Descartar",
          "run": "Ejecutar, reintentar o responder", "new": "Empezar de cero",
          "pause": "Pausar o retomar", "cancel": "Cancelar", "evidence": "Ver evidencia",
          "findings": "Decidir sobre hallazgos", "approve": "Aprobar e integrar",
          "approve_all": "Integrar todas las que esperan", "reject": "Rechazar",
          "open": "Abrir en tu editor / retomar con tu arreglo",
          "approve_spec": "Integrar la spec completa", "night": "Modo noche: aceptar y encolar"}
# panel derecho: qué muestra y con qué tecla se pide (la misma tecla vuelve a «Qué ha pasado»)
PANELS = {"timeline": ("Qué ha pasado", "log"), "evidence": ("Evidencia", "evidence"),
          "changes": ("Cambios", "changes"), "agent": ("Agente", "agent"),
          "memory": ("Aprendido en este repo", "memory")}
PANEL_KEYS = {"e": "evidence", "d": "changes", "g": "agent", "m": "memory"}
PANEL_KEYS_INV = {p: k for k, p in PANEL_KEYS.items()}
MAIN_ACTIONS = (*AVAILABLE, "spec", "toggle_raw", "quit", "panel", "projects")
LEASE_TTL_S, LEASE_RENEW_S = 60, 20
APPROVE_WIDTH = 92  # ancho útil del cuerpo de la confirmación (caja de 100 con borde y padding)
GROUP_GLYPHS = ("⚠", "▶", "·", "✓")  # etiqueta de fila por grupo: GROUPS de watch_data
TITLE_W, STATE_W = 30, 24  # columnas de la lista: el texto largo se recorta con «…»


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def json_key(d: dict) -> str:
    return json.dumps(d, sort_keys=True, default=str)


def _evidence_text(data: dict, heading: str = "", raw: bool = False) -> str:
    from umbra.cli.routines import render_evidence, render_report
    console = Console(file=io.StringIO(), width=100, color_system=None, record=True)
    if heading:
        console.print(heading)
    (render_evidence if raw else render_report)(console, data)
    return console.export_text()


# ---------- aplicación ----------
class WatchApp(App):
    TITLE = "umbra watch"
    CSS_PATH = "watch.tcss"
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (100, "-normal"), (160, "-wide")]
    BINDINGS = [
        Binding("a", "accept", "Aceptar/Autorizar"),
        Binding("r", "run", "Ejecutar/Responder"),
        Binding("n", "new", "De cero"),
        Binding("p", "pause", "Pausar/Retomar"),
        Binding("A", "approve", "Aprobar"),
        Binding("T", "approve_all", "Integrar todas"),
        Binding("R", "reject", "Rechazar"),
        Binding("o", "open", "Abrir/Retomar"),
        Binding("I", "approve_spec", "Integrar spec"),
        Binding("N", "night", "Noche"),
        Binding("e", "evidence", "Evidencia"),
        Binding("d", "panel('changes')", "Cambios"),
        Binding("g", "panel('agent')", "Agente"),
        Binding("m", "panel('memory')", "Aprendido"),
        Binding("h", "findings", "Hallazgos"),
        Binding("c", "cancel", "Cancelar"),
        Binding("x", "drop", "Descartar"),
        Binding("s", "spec", "Spec nueva"),
        Binding("t", "toggle_raw", "Técnico/narrado"),
        Binding("P", "projects", "Proyectos"),
        Binding("question_mark", "show_help_panel", "Ayuda"),
        Binding("q", "quit", "Salir"),
    ]

    def __init__(self, udir: Path, interval: float = 1.0, all_projects: bool = False):
        super().__init__()
        self.udir, self.root, self.interval = udir, udir.parent, interval
        self.all_projects = all_projects  # abierto desde `watch --all`: P vuelve a la lista
        self.selected: int | None = None
        self.shown_run: str | None = None
        self.last_seq = 0
        self.raw = False
        self.busy = False
        self._loader: Loader | None = None
        self._conn = None  # conexión del hilo de la pantalla: solo para el lease
        self._lease: tuple[str, int] | None = None
        self._task_rows: dict[int, tuple] = {}  # número → celdas pintadas
        self._row_order: list[str] = []  # claves en el orden de la tabla
        self._panel = "timeline"
        self._attempt_rows: list[tuple] | None = None
        self._attempt_started: list[str | None] = []  # para la duración en vivo
        self._attempt_run: str | None = None
        self._spec_lines: list | None = None
        self._header_text: str | None = None
        self._statuses: dict[int, str | None] | None = None  # para avisar solo de cambios
        self._shown_situation: tuple | None = None
        self._shown_extra: dict[str, tuple] = {}
        self._decision: dict = {}  # qué puede decidir la persona sobre la tarea seleccionada
        self._kind: str | None = None
        self._last_day: str | None = None
        self._force = True  # la primera instantánea siempre se calcula entera
        self._alive = True  # los hilos pueden volver cuando la pantalla ya se cerró
        self.bell_on = True

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="status")
        yield DataTable(id="tasks", cursor_type="row", zebra_stripes=True, show_row_labels=True)
        yield DataTable(id="attempts")
        yield Static(id="specs")
        with Horizontal(id="middle"):
            with VerticalScroll(id="situation"):
                yield Static(id="situation-body")
            with ContentSwitcher(id="right", initial="log"):
                yield RichLog(id="log", wrap=True, markup=False)
                with VerticalScroll(id="evidence"):
                    yield Static(id="evidence-body")
                with VerticalScroll(id="changes"):
                    yield Static(id="changes-files")
                    yield Static(id="changes-patch")
                yield RichLog(id="agent", wrap=True, markup=False)
                with VerticalScroll(id="memory"):
                    yield Static(id="memory-body")
        yield Footer()

    def on_mount(self) -> None:
        tasks = self.query_one("#tasks", DataTable)
        for label, key, width in (("#", "n", 3), ("tarea", "title", TITLE_W),
                                  ("etapas", "stages", 7), ("situación", "state", STATE_W),
                                  ("costo", "cost", 11), ("tiempo", "time", 7)):
            tasks.add_column(label, key=key, width=width)
        tasks.border_title = "Tareas"
        attempts = self.query_one("#attempts", DataTable)
        attempts.add_columns("etapa", "intento", "agente", "resultado", "duración", "costo")
        attempts.border_title = "Intentos"
        self.query_one("#situation").border_title = "Situación"
        self.sub_title = version.label()
        try:
            self.bell_on = project.load_project(self.root).get("notify", {}).get("bell", True)
        except project.NotInitialized:
            pass
        if warning := theme.apply_saved_theme(self):
            self.notify(warning, severity="warning")
        self._prefs_ready = True  # antes, el tema por defecto pisaría el guardado
        self._log_title()
        self._loader = Loader(self.udir)
        self._conn = open_store(self.udir)
        self._lease = (f"watch:{os.getpid()}@{socket.gethostname()}", 0)
        self._renew_lease()
        self.set_interval(LEASE_RENEW_S, self._renew_lease)
        self.refresh_data()
        self.set_interval(self.interval, self.refresh_data)

    def on_unmount(self) -> None:
        self._alive = False
        if self._lease and self._conn:
            lease.release(self._conn, *self._lease)
        if self._conn:
            self._conn.close()
        if self._loader:
            self._loader.close()

    def _renew_lease(self) -> None:
        """Mientras watch está abierto, el motor no manda avisos del sistema (ya avisa aquí)."""
        name, token = self._lease
        if not token or not lease.renew(self._conn, name, token, LEASE_TTL_S):
            token = lease.acquire(self._conn, name, name, LEASE_TTL_S) or 0
            self._lease = (name, token)

    def watch_theme(self, theme_name: str) -> None:
        """El tema elegido se recuerda entre sesiones (Textual no lo guarda)."""
        if getattr(self, "_prefs_ready", False):
            theme.save_prefs(theme=theme_name)
            self._task_rows, self._shown_situation = {}, None  # repintar con los colores nuevos
            self._header_text, self._shown_extra = None, {}
            self.query_one("#tasks", DataTable).clear()
            self._row_order = []
            self._force = True
            self.refresh_data()

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return theme.VARIABLES

    def _color(self, key: str) -> str:
        return self.theme_variables.get(f"state-{key}", "")

    # ---------- panel derecho ----------
    @property
    def tab(self) -> str:
        """Qué muestra el panel derecho: timeline, evidence, changes o agent."""
        return self._panel

    def action_panel(self, which: str) -> None:
        """Muestra ese panel; la misma tecla otra vez vuelve a «Qué ha pasado»."""
        which = "timeline" if which == self._panel else which
        self._panel = which
        self.query_one("#right", ContentSwitcher).current = PANELS[which][1]
        self._log_title()
        self._force = True
        self.refresh_data(tasks=False)

    # ---------- disponibilidad de acciones ----------
    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action in MAIN_ACTIONS and len(self.screen_stack) > 1:
            return False  # con una pantalla o ventana encima, las teclas de la vista no actúan
        if action == "projects":
            return self.all_projects
        if action in AVAILABLE:
            if self._kind not in AVAILABLE[action] or self.busy:
                return False
            d = self._decision
            if action == "accept" and self._kind != "draft":
                return bool(d.get("paths"))  # autorizar: solo si la política frenó algo
            if action == "findings":
                return d.get("open_findings", 0) > 0
            if action == "approve_all":
                return d.get("waiting", 0) >= 2
            if action == "approve_spec":
                return bool(d.get("spec_waiting"))
            return True
        return True

    def get_system_commands(self, screen):
        yield from super().get_system_commands(screen)
        for name, (title, _) in PANELS.items():
            yield SystemCommand(f"Panel: {title}", "Qué muestra el panel derecho",
                                lambda p=name: self.action_panel(p))
        if self.selected is None or self.busy:
            return
        for action, kinds in AVAILABLE.items():
            if self._kind in kinds:
                yield SystemCommand(f"Tarea {self.selected}: {LABELS[action]}",
                                    "Igual que el comando de umbra para esta tarea",
                                    getattr(self, f"action_{action}"))

    def _set_kind(self, kind: str | None) -> None:
        if kind != self._kind:
            self._kind = kind
            self.refresh_bindings()

    # ---------- acciones ----------
    def action_accept(self) -> None:
        n = self.selected
        if self._kind != "draft":
            return self._allow()
        self._do(f"umbra task accept {n}", lambda ctx: service.accept(ctx, [n], ORIGIN),
                 "Aceptada: ya se puede ejecutar.")

    def _allow(self) -> None:
        """La persona autoriza, solo en esta tarea, las rutas que la política frenó."""
        n, paths = self.selected, list(self._decision.get("paths") or [])
        if not service.interactive():
            self.notify("Autorizar lo decide una persona: requiere una terminal interactiva.",
                        severity="error")
            return
        if not paths:
            self.notify("La política no frenó ninguna ruta en esta ejecución.")
            return
        self._confirm(f"¿Autorizar que la tarea {n} cambie {', '.join(paths)}?",
                      "Autorizar y continuar",
                      lambda: self._do(f"umbra task allow {n} {' '.join(paths)}",
                                       lambda ctx: service.allow_paths(ctx, n, paths, ORIGIN),
                                       "Autorizado: el agente sigue desde Construir con ese "
                                       "permiso."),
                      body="Solo vale para esta tarea y queda registrado quién lo autorizó. "
                           "La política sigue protegiendo el resto de tests y rutas.")

    def _answer(self) -> None:
        """La persona responde las preguntas del agente y la tarea sigue donde quedó."""
        n = self.selected
        questions = "\n".join(f"• {q}" for q in self._decision.get("questions") or [])

        def with_text(text: str | None) -> None:
            if text:
                self._do(f'umbra task answer {n} "{text}"',
                         lambda ctx: service.answer(ctx, n, text, ORIGIN),
                         "Respuesta enviada: el agente sigue desde donde quedó.")

        self.push_screen(AskText(f"El agente pregunta:\n{questions}\n\nTu respuesta:"),
                         with_text)

    def action_drop(self) -> None:
        n = self.selected
        self._confirm(f"¿Descartar la tarea {n}? Queda en el historial, pero no se ejecutará.",
                      "Descartar", lambda: self._do(f"umbra task drop {n}",
                                                    lambda ctx: service.drop(ctx, [n], ORIGIN),
                                                    "Descartada."))

    def action_run(self) -> None:
        n = self.selected
        if self._kind == "ready":
            self._do(f"umbra run {n}", lambda ctx: service.run(ctx, [n], origin=ORIGIN),
                     "En cola: empieza en cuanto el worker la tome.")
            return
        if self._decision.get("code") == "agent_questions":
            return self._answer()
        ctx = service.load(self.root)
        try:
            stages, suggested = service.retry_stages(ctx, n)
        except service.OpError as e:
            self.notify(str(e), severity="error", markup=False)
            return
        finally:
            ctx.conn.close()

        def chosen(stage: str | None) -> None:
            if stage:
                self._do(f"umbra retry {n} --from {stage}",
                         lambda c: service.retry(c, n, stage, origin=ORIGIN),
                         f"Reintento en cola desde «{ex.STAGES.get(stage, stage)}».")

        self.push_screen(PickStage(stages, suggested), chosen)

    def action_new(self) -> None:
        n = self.selected
        self._confirm(f"¿Empezar la tarea {n} de cero?",
                      "Empezar de cero",
                      lambda: self._do(f"umbra run {n} --new",
                                       lambda ctx: service.run(ctx, [n], new=True,
                                                               origin=ORIGIN),
                                       "En cola desde cero."),
                      body="Se cancela la ejecución detenida (se cierra su PR si lo tenía y se "
                           "borra su carpeta de trabajo) y empieza una nueva desde la rama base.")

    def action_pause(self) -> None:
        n = self.selected
        if self._kind == "paused":
            self._do(f"umbra resume {n}", lambda ctx: service.resume(ctx, n, origin=ORIGIN),
                     "Retomada.")
        else:
            self._do(f"umbra pause {n}", lambda ctx: service.pause(ctx, n, ORIGIN),
                     "Pausa solicitada: se detiene al terminar la etapa en curso.")

    def action_cancel(self) -> None:
        n = self.selected
        self._confirm(f"¿Cancelar la tarea {n}?", "Cancelar tarea",
                      lambda: self._do(f"umbra cancel {n}",
                                       lambda ctx: service.cancel(ctx, n, ORIGIN),
                                       "Cancelada."),
                      body="Si está trabajando, se detiene al terminar la etapa en curso. Se "
                           "cierra su PR si lo tenía y se borra su carpeta de trabajo.")

    def action_evidence(self) -> None:
        self.action_panel("evidence")

    def action_findings(self) -> None:
        n = self.selected
        if not service.interactive():
            self.notify("Decidir sobre hallazgos requiere una terminal interactiva.",
                        severity="error")
            return
        ctx = service.load(self.root)
        try:
            pending = service.pending_findings(ctx, n) or service.open_findings(ctx, n)
        finally:
            ctx.conn.close()
        if not pending:
            self.notify("Esta tarea no tiene hallazgos pendientes de decidir.")
            return
        options = [f"[{f['severity']}] {f['message'][:160]}" for f in pending]
        options += ["Todos"] if len(pending) > 1 else []

        def with_decision(which: list[int], decision: str, reason: str | None) -> None:
            if reason is None:
                return
            verb = "waive" if decision == "waived" else "defer"
            nums = " ".join(map(str, which))
            self._do(f'umbra finding {verb} {n} {nums} -m "{reason}"'.replace("  ", " "),
                     lambda c: service.decide_findings(c, n, which, decision, reason, ORIGIN),
                     "Decidido. Pulsa r para seguir: umbra propondrá la etapa adecuada.")

        def with_kind(which: list[int], kind: int | None) -> None:
            if kind is None:
                return
            decision = ("waived", "deferred")[kind]
            default = "no aplica" if decision == "waived" else "se hará después"
            self.push_screen(AskText("Motivo (queda registrado):", default),
                             lambda r: with_decision(which, decision, r))

        def with_finding(i: int | None) -> None:
            if i is None:
                return
            which = [] if i == len(pending) else [i + 1]
            self.push_screen(PickOne("¿Qué decides?", [
                "No aplica: no hay que corregirlo",
                "Se hará después: crea una tarea en borrador con lo pendiente"]),
                lambda k: with_kind(which, k))

        self.push_screen(PickOne(f"Hallazgos que frenaron la tarea {n}", options), with_finding)

    def action_approve(self) -> None:
        n = self.selected
        if not service.interactive():
            self.notify("Aprobar requiere una terminal interactiva.", severity="error")
            return

        def ask(data: dict) -> None:
            from umbra.cli.watch_data import report_ansi
            head = (data["run"]["head_sha"] or "")[:10]
            body = Text.assemble((f"Revisa antes de aprobar (detalle técnico: umbra evidence {n}"
                                  " --raw):\n\n", "bold"),
                                 Text.from_ansi(report_ansi(data, width=APPROVE_WIDTH)))
            self._confirm(f"¿Aprobar e integrar la tarea {n} (commit {head}) en la rama base?",
                          "Aprobar e integrar",
                          lambda: self._do(f"umbra approve {n}",
                                           lambda c: service.approve(c, n, ORIGIN),
                                           lambda r: "Integrada en la rama base." + (
                                               f" Piloto automático: la tarea {r['next']} "
                                               "arrancó sola." if r.get("next") else "")),
                          body=body)

        self._with_evidence(n, ask)

    def action_approve_all(self) -> None:
        if not service.interactive():
            self.notify("Aprobar requiere una terminal interactiva.", severity="error")
            return
        ctx = service.load(self.root)
        try:
            waiting = service.waiting_tasks(ctx)
        finally:
            ctx.conn.close()
        nums = ", ".join(map(str, waiting))

        def done(r) -> str:
            text = f"Integradas: {', '.join(map(str, r['approved'])) or 'ninguna'}."
            if r["failed"]:
                text += f" La tarea {r['failed'][0]} no se integró: {r['failed'][1]}"
            return text

        self._confirm(f"¿Integrar las {len(waiting)} tareas que esperan ({nums})?",
                      "Integrar todas",
                      lambda: self._do("umbra approve --all",
                                       lambda c: service.approve_all(c, ORIGIN), done),
                      body="Cada una se integra con su propia aprobación, en orden; si una no se "
                           "puede, se detiene ahí. Revisa antes la evidencia (e) de cada una.")

    def action_reject(self) -> None:
        n = self.selected
        if not service.interactive():
            self.notify("Rechazar requiere una terminal interactiva.", severity="error")
            return

        def with_reason(reason: str | None) -> None:
            if reason:
                self._do(f'umbra reject {n} -m "{reason}"',
                         lambda ctx: service.reject(ctx, n, reason, ORIGIN),
                         "Rechazada: se cerró el PR.")

        self.push_screen(AskText(f"¿Por qué rechazas la tarea {n}? Se cerrará su PR.",
                                 "rechazado"), with_reason)

    def action_open(self) -> None:
        """Abre la tarea en tu editor; la segunda vez, confirma tu arreglo y umbra retoma."""
        n = self.selected
        if not self._decision.get("takeover"):
            self._do(f"umbra open {n}", lambda ctx: service.open_workspace(ctx, n, ORIGIN),
                     lambda r: f"Abierto con {r['editor']}. Cuando termines, pulsa o de nuevo.")
            return

        def with_text(text: str | None) -> None:
            if text:
                self._do(f'umbra done {n} -m "{text}"',
                         lambda ctx: service.resume_human(ctx, n, text, ORIGIN),
                         lambda r: "Tu arreglo pasa los tests: umbra sigue desde "
                                   f"«{ex.STAGES.get(r['resumed_from'], r['resumed_from'])}».")

        self.push_screen(AskText("Umbra confirmará tus cambios, correrá los tests y seguirá "
                                 "desde Revisar.\n\nQué arreglaste (una línea):"), with_text)

    def action_approve_spec(self) -> None:
        """Una sola aprobación por spec: su PR (rama de spec → base) se integra."""
        d = self._decision
        spec, pr = d.get("spec"), d.get("spec_pr") or {}
        if not service.interactive():
            self.notify("Aprobar lo decide una persona: requiere una terminal interactiva.",
                        severity="error")
            return
        name = Path(spec).name
        self._confirm(f"¿Integrar la spec {name} completa en la rama base?",
                      "Integrar la spec",
                      lambda: self._do(f"umbra approve --spec {name}",
                                       lambda ctx: service.approve_spec(ctx, spec, ORIGIN),
                                       lambda r: f"Spec integrada: merge {r['merge_sha'][:10]}"),
                      body=f"Todas sus historias ya pasaron tests, revisión y política y están "
                           f"integradas en spec/{name}. PR #{pr.get('number')}: {pr.get('url')}")

    def action_night(self) -> None:
        """Deja todo encolado: acepta los borradores y arranca lo que quepa."""
        self._confirm("¿Aceptar todos los borradores y dejar que umbra los encadene sola?",
                      "Modo noche",
                      lambda: self._do("umbra night", lambda ctx: service.night(ctx, None, ORIGIN),
                                       lambda r: f"Aceptadas {len(r['accepted'])}; en marcha "
                                                 f"{len(r['started'])} (hasta {r['parallel']} a "
                                                 f"la vez); esperan {len(r['waiting'])}."),
                      body="Las tareas de una spec se integran solas en su rama; mañana solo "
                           "aprobarás specs completas o atenderás lo que se detuvo.")

    def action_projects(self) -> None:
        """Vuelve a la lista de repos (`umbra watch --all`)."""
        self.exit("projects")

    def action_toggle_raw(self) -> None:
        self.raw = not self.raw
        self.shown_run = None  # fuerza a redibujar el registro desde el principio
        self._log_title()
        if self.tab == "evidence":
            self._shown_extra.pop("evidence", None)
        self._force = True
        self.refresh_data(tasks=False)

    def _confirm(self, question: str, yes: str, then: Callable[[], None], body="") -> None:
        self.push_screen(Confirm(question, body, yes), lambda ok: then() if ok else None)

    def _do(self, command: str, operation: Callable, done: str | Callable) -> None:
        """Ejecuta la operación en segundo plano: la pantalla nunca se congela."""
        self.busy = True
        self.refresh_bindings()
        self.notify(f"Trabajando… ({command})", timeout=2, markup=False)
        self._run_operation(command, operation, done)

    @work(thread=True, exclusive=True, group="operations")
    def _run_operation(self, command: str, operation: Callable, done: str | Callable) -> None:
        try:
            ctx = service.load(self.root)  # conexión propia: SQLite no se comparte entre hilos
            try:
                result = operation(ctx)
            finally:
                ctx.conn.close()
            done = done(result) if callable(done) else done
            self.call_from_thread(self.notify, f"{done}\nEquivale a: {command}",
                                  title="Hecho", markup=False)
        except service.OpError as e:
            self.call_from_thread(self.notify, str(e), title="No se pudo", severity="error",
                                  markup=False)
        except Exception as e:  # nunca tumbar la pantalla por un error inesperado
            self.call_from_thread(self.notify, f"Error inesperado: {e}", title="No se pudo",
                                  severity="error", markup=False)
        finally:
            self.call_from_thread(self._operation_finished)

    def _operation_finished(self) -> None:
        # busy se suelta cuando la vista ya refleja el resultado (la instantánea llega de un hilo)
        self._release_busy = True
        self._force = True
        self._shown_extra = {}
        self.refresh_data()

    def _release(self) -> None:
        if getattr(self, "_release_busy", False):
            self._release_busy = False
            self.busy = False
            self.refresh_bindings()

    def _with_evidence(self, n: int, then: Callable[[dict], None]) -> None:
        """La evidencia tira de git: se prepara en un hilo y la pantalla sigue viva."""
        self.notify("Preparando la evidencia…", timeout=2)
        self._load_evidence(n, then)

    @work(thread=True, exclusive=True, group="evidence")
    def _load_evidence(self, n: int, then: Callable[[dict], None]) -> None:
        ctx = service.load(self.root)
        try:
            data = service.evidence(ctx, n)
        except service.OpError as e:
            self.call_from_thread(self.notify, str(e), severity="error", markup=False)
            return
        finally:
            ctx.conn.close()
        if self._alive:
            self.call_from_thread(then, data)

    # ---------- refresco ----------
    def _log_title(self) -> None:
        """El título del panel derecho dice qué muestra y con qué teclas cambia."""
        title = PANELS[self._panel][0]
        if self._panel == "timeline":
            title = "Registro técnico (t: narrado)" if self.raw else "Qué ha pasado (t: técnico)"
            keys = " ".join(f"{k}·{PANELS[p][0].lower()}" for k, p in PANEL_KEYS.items())
        else:
            keys = f"{PANEL_KEYS_INV[self._panel]}·volver"
        right = self.query_one("#right")
        right.border_title, right.border_subtitle = title, keys

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "tasks" or not event.row_key.value:
            return
        number = int(event.row_key.value)
        if number != self.selected:  # solo una selección nueva del usuario refresca
            self.selected = number
            self._shown_extra = {}
            self.refresh_data(tasks=False)

    def refresh_data(self, tasks: bool = True) -> None:
        """Pide una instantánea nueva (en un hilo) y la aplica al llegar."""
        if self._loader is not None:
            right = self.query("#right")  # el informe se envuelve al ancho real del panel
            if right:
                self._loader.width = max(40, right.first().content_region.width - 2)
            self._load_snapshot(self.tab)

    @work(thread=True, exclusive=True, group="refresh")
    def _load_snapshot(self, want: str) -> None:
        force, self._force = self._force, False
        try:
            snap = self._loader.load(self.selected, self.raw, self.shown_run, self.last_seq,
                                     force, want)
        except Exception as e:  # la pantalla sigue viva; se reintenta en el próximo tick
            if self._alive:
                self.call_from_thread(self.notify, f"No se pudo leer el estado: {e}",
                                      severity="error", markup=False)
                self.call_from_thread(self._release)
            return
        if self._alive:
            self.call_from_thread(self._apply, snap)

    def _apply(self, snap: Snapshot | None) -> None:
        if not self._alive:
            return
        if not self.query("#agent"):  # los paneles aún se están montando: en el próximo tick
            self._force = True
            return
        if snap is None:  # nada cambió: solo avanza la duración del intento en curso
            self._tick_durations()
        elif snap.header is None:  # solo creció el registro del agente
            self._agent(snap)
        else:
            self.selected = snap.selected
            self._status(snap)
            self._tasks(snap)
            self._situation(snap)
            self._specs(snap)
            self._attempts(snap)
            self._log(snap)
            self._evidence(snap)
            self._changes(snap)
            self._agent(snap)
            self._memory(snap)
        self._release()

    def _status(self, snap: Snapshot) -> None:
        h = snap.header
        if h is None:
            return
        ok, warn = self._color("done"), self._color("blocked")
        text = Text.assemble(
            ("● worker vivo", ok) if h.worker_alive else ("○ worker parado", "dim"),
            "  ·  ", f"cola {h.queued}", "  ·  ", f"gasto {h.spend}", "  ·  ",
            f"{h.tasks} tareas", "  ·  ",
            (f"⚠ {h.attention} te necesita{'n' if h.attention != 1 else ''}", f"bold {warn}")
            if h.attention else ("nada pendiente de ti", "dim"))
        if text.plain != self._header_text:
            self._header_text = text.plain
            self.query_one("#status", Static).update(text)

    def _tasks(self, snap: Snapshot) -> None:
        table = self.query_one("#tasks", DataTable)
        painted = {}
        first = self._statuses is None  # en la primera instantánea no se avisa de nada
        self._statuses = self._statuses or {}
        with self.prevent(DataTable.RowHighlighted):  # mover filas no es elegir una tarea
            for t in snap.tasks:
                self._alert(t.number, t.title, t.run_status, first)
                color = self._color(t.state)
                stages = Text()
                for glyph, state in t.progress:
                    stages.append(glyph, style=self._color(state))
                cells = (str(t.number), _clip(t.title, TITLE_W), stages,
                         Text(_clip(t.situation, STATE_W), style=color), t.cost, t.elapsed)
                key = (t.title, t.situation, t.cost, t.elapsed, color, tuple(t.progress),
                       t.group)
                painted[t.number] = key
                if self._task_rows.get(t.number) == key:
                    continue
                if str(t.number) in table.rows:
                    for col, value in zip(("title", "stages", "state", "cost", "time"),
                                          cells[1:], strict=True):
                        table.update_cell(str(t.number), col, value)
                else:
                    table.add_row(*cells, key=str(t.number),
                                  label=Text(GROUP_GLYPHS[t.group], style=color))
            for number in [n for n in self._task_rows if n not in painted]:
                table.remove_row(str(number))
                self._row_order.remove(str(number))
            self._row_order += [str(t.number) for t in snap.tasks
                                if str(t.number) not in self._row_order]
            self._task_rows = painted
            # una tarea que cambia de grupo cambia de sitio: si el orden ya no coincide, se rehace
            wanted = [str(t.number) for t in snap.tasks]
            if self._row_order != wanted:
                table.clear()
                self._task_rows, self._row_order = {}, []
                return self._tasks(snap)
            if self.selected is not None and str(self.selected) in table.rows:
                row = table.get_row_index(str(self.selected))
                if table.cursor_row != row:
                    table.move_cursor(row=row)

    def _alert(self, number: int, title: str, status: str | None, first: bool) -> None:
        """Aviso dentro de la pantalla (y campana) cuando una tarea pasa a necesitarte."""
        before = self._statuses.get(number)
        self._statuses[number] = status
        if first or status == before or status not in WATCH_ALERTS:
            return
        self.notify(f"{title}: {WATCH_ALERTS[status]}", title=f"Tarea {number}",
                    severity="warning" if status == "WAITING_APPROVAL" else "error",
                    timeout=15, markup=False)
        if self.bell_on:
            self.bell()

    def _situation(self, snap: Snapshot) -> None:
        body = self.query_one("#situation-body", Static)
        if snap.explanation is None:
            self._set_kind(None)
            self._shown_situation = None
            body.update("No hay tareas todavía. Crea una con `umbra task add` o `umbra plan`, "
                        "o pulsa s para empezar una spec.")
            return
        if snap.decision != self._decision:
            self._decision = snap.decision
            self.refresh_bindings()
        self._set_kind(snap.explanation.kind)
        shown = (snap.selected, snap.explanation_key, self.raw, self.theme,
                 json_key(snap.decision))
        if shown != self._shown_situation:  # solo se redibuja si la explicación cambió
            self._shown_situation = shown
            colors = {k: self._color(k) for k in theme.STATE_KEYS}
            panel = self.query_one("#situation")
            keys = self._decision_keys(snap)
            if keys:
                panel.border_title = f"Decisión · tarea {snap.selected}"
                panel.styles.border = ("round", self._color("blocked"))
                body.update(Group(keys, Text(""), renderable(
                    snap.explanation, compact=True, technical=self.raw, colors=colors)))
            else:
                panel.border_title = "Situación"
                panel.styles.border = ("round", self.theme_variables.get("accent", ""))
                body.update(renderable(snap.explanation, compact=True, technical=self.raw,
                                       colors=colors))

    def _decision_keys(self, snap: Snapshot) -> Text | None:
        """Las teclas con las que se resuelve lo que la tarea pide, en una línea destacada."""
        d, kind = snap.decision, snap.explanation.kind
        hint = Text()
        key = self._color("blocked")

        def add(k: str, label: str) -> None:
            hint.append(f"[{k}] ", style=f"bold {key}")
            hint.append(f"{label}   ")

        if kind == "waiting_approval":
            add("A", "Integrar")
            if d.get("waiting", 0) >= 2:
                add("T", f"Integrar las {d['waiting']} que esperan")
            add("R", "Rechazar")
            add("e", "Evidencia")
            add("d", "Cambios")
        elif kind in ("blocked", "failed"):
            if d.get("takeover"):
                add("o", "Retomar con tu arreglo")
            if d.get("paths"):
                add("a", "Autorizar cambiar " + ", ".join(d["paths"]))
            if d.get("code") == "agent_questions":
                add("r", "Responder al agente")
            elif d.get("code") == "findings" or d.get("open_findings"):
                add("h", "Decidir hallazgos")
                add("r", "Reintentar")
            else:
                add("r", "Reintentar")
            if not d.get("takeover"):
                add("o", "Arreglarlo tú")
            add("n", "De cero")
        if d.get("spec_waiting"):
            add("I", f"Integrar la spec {Path(d['spec']).name}")
        return hint if hint.plain else None

    def _specs(self, snap: Snapshot) -> None:
        if snap.specs == self._spec_lines:
            return
        self._spec_lines = snap.specs
        self.query_one("#specs", Static).update(
            "\n".join(snap.specs) if snap.specs else "Sin specs todavía: pulsa s para empezar una.")

    def _attempts(self, snap: Snapshot) -> None:
        rows = [a.cells for a in snap.attempts]
        self._attempt_started = [a.started_at if a.running else None for a in snap.attempts]
        if rows == self._attempt_rows:  # sin cambios: no redibujar
            return
        old, self._attempt_rows = self._attempt_rows, rows
        table = self.query_one("#attempts", DataTable)
        if old is None or snap.run_id != self._attempt_run or len(rows) < len(old):
            self._attempt_run = snap.run_id
            table.clear()
            for row in rows:
                table.add_row(*row)
            return
        # solo lo que cambió (la duración del intento en curso cambia cada segundo): rehacer la
        # tabla devolvía el scroll y la selección al principio. `rows` puede traer filas nuevas
        for i, (before, after) in enumerate(zip(old, rows, strict=False)):
            for j, (a, b) in enumerate(zip(before, after, strict=True)):
                if a != b:
                    table.update_cell_at(Coordinate(i, j), b)
        for row in rows[len(old):]:
            table.add_row(*row)

    def _tick_durations(self) -> None:
        """Sin datos nuevos solo cambia el reloj del intento en curso: ni SQL ni repintados."""
        if not self._attempt_rows:
            return
        table = self.query_one("#attempts", DataTable)
        for i, started in enumerate(self._attempt_started):
            if started and i < len(self._attempt_rows):
                text = clock.duration(started, None)
                if text != self._attempt_rows[i][4]:
                    row = list(self._attempt_rows[i])
                    row[4] = text
                    self._attempt_rows[i] = tuple(row)
                    table.update_cell_at(Coordinate(i, 4), text)

    def _log(self, snap: Snapshot) -> None:
        log = self.query_one("#log", RichLog)
        if snap.log_reset:
            log.clear()
            self._last_day = None
        self.shown_run, self.last_seq = snap.run_id, snap.last_seq
        for created_at, text in snap.log:
            if (day := clock.day_key(created_at)) != self._last_day:  # el día cuando cambia
                self._last_day = day
                log.write(Text(f"── {clock.day_label(created_at)} ──", style="dim"))
            log.write(text)

    def _evidence(self, snap: Snapshot) -> None:
        body = self.query_one("#evidence-body", Static)
        if snap.evidence is None:
            if self.tab == "evidence":
                body.update(Text("Esta tarea no tiene ninguna ejecución todavía."
                                 if snap.run_id is None else "Preparando la evidencia…",
                                 style="dim"))
            return
        ansi, tests = snap.evidence
        shown = (snap.run_id, ansi, tests, self.raw)
        if self._shown_extra.get("evidence") == shown:
            return
        self._shown_extra["evidence"] = shown
        parts = [Text.from_ansi(ansi)]
        if tests:
            parts += [Text("\nSalida de las pruebas (últimas líneas)", style="bold underline"),
                      Text(tests, style="dim")]
        body.update(Text("\n").join(parts))

    def _changes(self, snap: Snapshot) -> None:
        files_w = self.query_one("#changes-files", Static)
        patch_w = self.query_one("#changes-patch", Static)
        if snap.changes is None:
            if self.tab == "changes":
                files_w.update(Text("Todavía no hay cambios: la ejecución no ha llegado a un "
                                    "commit probado." if snap.run_id else
                                    "Esta tarea no tiene ninguna ejecución todavía.",
                                    style="dim"))
                patch_w.update("")
            return
        files, patch, truncated = snap.changes
        shown = (snap.run_id, len(patch), len(files))
        if self._shown_extra.get("changes") == shown:
            return
        self._shown_extra["changes"] = shown
        table = Text()
        for path, added, removed in files:
            table.append(f"{path:<60.60} ")
            table.append(f"+{added:>5}", style=self._color("done"))
            table.append(f" -{removed:>5}\n", style=self._color("failed"))
        if not files:
            table = Text("Sin archivos cambiados.", style="dim")
        files_w.update(table)
        note = ("\n… parche recortado a 60 000 caracteres; el diff completo está en git.\n"
                if truncated else "")
        patch_w.update(Syntax(patch + note, "diff", theme="ansi_dark", word_wrap=True,
                              background_color="default"))

    def _memory(self, snap: Snapshot) -> None:
        if snap.memory is None:
            return
        shown = ("memory", snap.memory)
        if self._shown_extra.get("memory") == shown:
            return
        self._shown_extra["memory"] = shown
        from rich.markdown import Markdown
        body = self.query_one("#memory-body", Static)
        body.update(Markdown(snap.memory) if snap.memory.strip() else Text(
            "umbra aún no ha aprendido nada en este repo: cada hallazgo que decidas, cada "
            "respuesta y cada autorización quedarán aquí.", style="dim"))

    def _agent(self, snap: Snapshot) -> None:
        log = self.query_one("#agent", RichLog)
        if snap.agent is None:
            return
        if snap.agent_reset:
            log.clear()
            if snap.agent_empty:
                log.write(Text(snap.agent_empty, style="dim"))
        for line in snap.agent:
            style = "bold" if line.startswith(("Terminó", "Falló")) else ""
            log.write(Text(line, style=style) if style else line)

    # ---------- spec ----------
    def action_spec(self) -> None:
        if not service.interactive():
            self.notify("La conversación de una spec requiere una terminal interactiva.",
                        severity="error")
            return
        ctx = service.load(self.root)
        try:
            open_conv = service.spec_open_conversation(ctx)
        finally:
            ctx.conn.close()

        def ask() -> None:
            self.push_screen(AskText("¿Qué quieres construir?"),
                             lambda idea: self._spec_open(idea) if idea else None)

        if not open_conv:
            return ask()
        what = open_conv["spec_dir"] or open_conv["idea"]
        self.push_screen(
            Confirm(f"¿Retomar la conversación de {what}?", "Hay una conversación abierta.",
                    "Retomar"),
            lambda ok: self._spec_open(None, open_conv["id"]) if ok else ask())

    def _spec_open(self, idea: str | None, conv_id: str = "") -> None:
        """Apila la pantalla de la spec (origen watch) sobre esta vista; al volver, refresca."""
        from umbra.cli.spec_screen import SpecScreen  # evita el import circular
        ctx = service.load(self.root)
        try:
            service.spec_max_cost(ctx)
            service.preflight(ctx)
            lock = service.spec_lock(ctx, conv_id) if conv_id else None
            if conv_id:
                idea = ctx.conn.execute("SELECT idea FROM conversation WHERE id = ?",
                                        (conv_id,)).fetchone()["idea"]
        except service.OpError as e:
            ctx.conn.close()
            self.notify(str(e), severity="error", markup=False)
            return

        def back(_result) -> None:  # la pantalla cierra su propia conexión al desmontarse
            self._force = True
            self.refresh_data()

        self.push_screen(SpecScreen(ctx, idea, conv_id=conv_id, lock=lock, origin=ORIGIN), back)
