"""Pantalla de `umbra spec new`: conversación con el asistente, preguntas y puntos de control.

`SpecScreen` vive dentro de cualquier app de umbra (watch la apila encima de su vista; `SpecApp`
la usa como pantalla única para `umbra spec new/resume`).
"""

import json
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input, RichLog, Static

from umbra import service
from umbra.chat import elicit
from umbra.chat.stream import Stream, TextDelta, ToolUse
from umbra.cli.modals import AskText, Confirm, PickOne
from umbra.cli.theme import apply_saved_theme
from umbra.unified.store import open_store

REVIEWS = ("spec_review", "plan_review")
OTHER = "Otra respuesta…"
CHOICES = ["Aprobar", "Pedir cambios", "Descartar"]


class SpecScreen(Screen):
    BINDINGS = [Binding("ctrl+r", "review", "Revisar"),
                Binding("escape", "leave", "Volver (la conversación se puede retomar)")]

    def __init__(self, ctx: service.Ctx, idea: str, exe: str = "claude",
                 conv_id: str = "", lock: tuple[str, int] | None = None,
                 origin: str = "spec"):
        super().__init__()
        self.ctx, self.idea, self.exe = ctx, idea, exe
        self.max_cost = service.spec_max_cost(ctx)
        self.conv_id = conv_id  # con valor = reanudación
        self.lock, self.origin = lock, origin
        self.lost = False  # el lease se perdió: la entrada queda deshabilitada
        self.lines: list[str] = []  # lo mismo que muestra el historial, en texto plano
        self.live = ""
        self._stream: Stream | None = None
        self._stream_phase = ""

    def compose(self) -> ComposeResult:
        yield RichLog(id="history", wrap=True, markup=False)
        yield Static("", id="live", markup=False)
        yield Static("", id="activity", markup=False)
        yield Static("", id="bar", markup=False)
        yield Input(placeholder="Escribe aquí…", id="entry")

    def on_mount(self) -> None:
        self.query_one("#history").border_title = f"Spec · {self.idea}"[:80]
        resumed = bool(self.conv_id)
        if not resumed:
            self.conv_id = service.spec_new(self.ctx, self.idea, self.origin)
        self.lock = self.lock or service.spec_lock(self.ctx, self.conv_id)
        self.set_interval(20, self._renew)
        if not resumed:
            self._say(f"Tú: {self.idea}")
            return self._start_turn(elicit.phase_message("specify", self.idea))
        for text in service.spec_history(self.ctx, self.conv_id):
            self._say(text, keep=False)
        self._bar()
        phase = elicit.phase_of(self.ctx.conn, self.conv_id)
        if phase in REVIEWS:
            self._review()
        else:
            self._say(f"— Conversación retomada en la fase {phase}. Puedes seguir escribiendo.",
                      keep=False)
            self._enable()

    def on_unmount(self) -> None:
        self.workers.cancel_all()
        if self._stream:
            self._stream.close()  # termina el proceso de claude y, con él, el hilo del turno
        if self.lock:
            service.spec_unlock(self.ctx, self.lock)
        self.ctx.conn.close()  # la pantalla es la dueña de su conexión

    def _close(self) -> None:
        """Cierra la pantalla: sola (umbra spec new) → termina la app; dentro de watch → vuelve."""
        if self.app.screen_stack[0] is self:
            return self.app.exit()
        while self.app.screen is not self:  # una pregunta o confirmación abierta encima
            self.app.pop_screen()
        self.dismiss(None)

    def action_leave(self) -> None:
        self._close()

    def _renew(self) -> None:
        if self.lock and not self.lost and not service.spec_renew(self.ctx, self.lock):
            self.lost = True
            self._say("Aviso: se perdió el bloqueo de esta conversación (otra pantalla pudo "
                      "abrirla). Ciérrala y usa `umbra spec resume`.", keep=False)
            self._enable(False)

    # --- salida --------------------------------------------------------------------------
    def _say(self, text: str, keep: bool = True) -> None:
        self.lines.append(text)
        self.query_one("#history", RichLog).write(text)
        if keep:
            service.spec_log(self.ctx, self.conv_id, text)

    def _bar(self) -> None:
        phase = elicit.phase_of(self.ctx.conn, self.conv_id)
        spent = elicit.spent(self.ctx.conn, self.conv_id)
        self.query_one("#bar", Static).update(
            f"Fase: {phase} · Costo: ${spent:.2f} / ${self.max_cost}")

    def _enable(self, on: bool = True) -> None:
        entry = self.query_one("#entry", Input)
        entry.disabled = not on or self.lost
        if on and not self.lost:
            entry.focus()

    # --- turnos (hilo aparte) ------------------------------------------------------------
    def _start_turn(self, message: str) -> None:
        self._enable(False)
        self.live = ""
        self.run_worker(lambda: self._turn(message), thread=True)

    def _turn(self, message: str) -> None:
        try:
            conn = open_store(self.ctx.udir)
            phase = elicit.phase_of(conn, self.conv_id)
            res = elicit.run_turn(conn, self.ctx.root, self.conv_id,
                                  self._stream_for(conn, phase), message, self.max_cost,
                                  self._on_event)
        except Exception as e:  # el hilo nunca debe cerrar la pantalla
            res = elicit.TurnResult(error=True, text=f"No se pudo hablar con claude: {e}")
        if res.error and self._stream:  # el proceso pudo morir: el próximo turno reabre
            self._stream.close()
            self._stream = None
        if self.is_mounted:  # la persona pudo cerrar la pantalla a mitad de turno
            self.app.call_from_thread(self._after_turn, res)

    def _stream_for(self, conn, phase: str) -> Stream:
        """`--settings` se fija al arrancar: cada fase abre un `claude` nuevo con --resume."""
        if self._stream and self._stream_phase == phase:
            return self._stream
        if self._stream:
            self._stream.close()
        path = self.ctx.udir / "artifacts" / "spec" / f"settings-{phase}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(elicit.phase_settings(phase, service.spec_script())),
                        encoding="utf-8")
        sid = conn.execute("SELECT session_id FROM conversation WHERE id = ?",
                           (self.conv_id,)).fetchone()["session_id"]
        self._stream = Stream(self.ctx.root, path, resume=sid, exe=self.exe)
        self._stream_phase = phase
        return self._stream

    def _on_event(self, ev) -> None:
        if not self.is_mounted:
            return
        if isinstance(ev, TextDelta):
            self.app.call_from_thread(self._live, ev.text)
        elif isinstance(ev, ToolUse):
            verb = "Escribiendo" if ev.name in ("Write", "Edit") else ev.name
            self.app.call_from_thread(self.query_one("#activity", Static).update,
                                      f"{verb} {ev.target}".strip())

    def _live(self, text: str) -> None:
        self.live += text
        self.query_one("#live", Static).update(self.live)

    # --- después de cada turno -----------------------------------------------------------
    def _after_turn(self, res: elicit.TurnResult) -> None:
        if not self.is_mounted:
            return
        self.query_one("#live", Static).update("")
        self.query_one("#activity", Static).update("")
        if res.text:
            self._say(res.text)
        for w in res.warnings:
            self._say(f"Aviso: {w}")
        self._bar()
        phase = elicit.phase_of(self.ctx.conn, self.conv_id)
        if res.error:
            self._say("Error del asistente. Puedes escribir de nuevo para reintentar.")
            self.notify("Error del asistente", severity="error")
            self._enable()
        elif res.paused:
            self.notify("Conversación en pausa por costo", severity="warning")
            self._enable()
        elif res.question:
            self._ask(res.question)
        elif phase == "specify":
            clarify = "[NEEDS CLARIFICATION]" in res.text
            self._go("next" if clarify else "skip_clarify")
        elif phase in ("clarify", "plan"):
            self._go("next")
        elif phase == "tasks":
            self._make_tasks()

    def _go(self, event: str) -> None:
        """Avanza de fase y arranca lo que toca: un turno o un punto de control."""
        phase = elicit.advance(self.ctx.conn, self.conv_id, event)
        self._bar()
        if phase in REVIEWS:
            self._review()
        elif phase == "done":
            self._enable(False)
        else:
            self._start_turn(elicit.phase_message(phase, self.idea))

    def _ask(self, q: elicit.Question) -> None:
        order = sorted(range(len(q.options)), key=lambda i: i != q.recommended)  # recomendada 1ª
        labels = [q.options[i] + (" (recomendada)" if i == q.recommended else "") for i in order]

        def picked(idx: int | None) -> None:
            if idx is None:
                self._enable()
            elif idx < len(order):
                self._answer(q.options[order[idx]])
            else:
                self.app.push_screen(AskText(q.question), lambda t: self._answer(t) if t
                                     else self._ask(q))

        self.app.push_screen(PickOne(q.question, [*labels, OTHER]), picked)

    def _answer(self, text: str) -> None:
        self._say(f"Tú: {text}")
        self._start_turn(text)

    # --- puntos de control ---------------------------------------------------------------
    def action_review(self) -> None:
        if elicit.phase_of(self.ctx.conn, self.conv_id) in REVIEWS:
            self._review()

    def _review(self) -> None:
        phase = elicit.phase_of(self.ctx.conn, self.conv_id)
        what = "la spec" if phase == "spec_review" else "el plan"
        self._enable()
        self.app.push_screen(PickOne(f"Revisa {what} en specs/", CHOICES), self._decided)

    def _decided(self, idx: int | None) -> None:
        phase = elicit.phase_of(self.ctx.conn, self.conv_id)
        if idx is None:
            self._say("Pendiente de revisión: ctrl+r para decidir o escribe los cambios.")
        elif idx == 0:
            self._approve(phase)
        elif idx == 1:
            self.app.push_screen(AskText("¿Qué cambios pides?"),
                                 lambda t: self._changes(t) if t else self._review())
        else:
            self.app.push_screen(Confirm("¿Descartar la conversación? No se crearán tareas."),
                                 lambda yes: self._discard() if yes else self._review())

    def _approve(self, phase: str) -> None:
        if phase == "plan_review":
            folder = elicit.spec_dir_from_feature(self.ctx.root)
            if folder is None:
                self._say("Aviso: falta .specify/feature.json; pide cambios para que el "
                          "asistente lo cree.")
                return self._review()
            elicit.set_spec_dir(self.ctx.conn, self.conv_id, folder)
            if self.lock:  # el lease pasa de `spec:<conversación>` a `spec:<carpeta>`
                service.spec_unlock(self.ctx, self.lock)
                self.lock = service.spec_lock(self.ctx, self.conv_id)
        service.spec_event(self.ctx, "approved", self.conv_id, phase=phase)
        self._say("Aprobado.")
        self._go("approve")

    def _changes(self, comment: str) -> None:
        phase = elicit.phase_of(self.ctx.conn, self.conv_id)
        service.spec_event(self.ctx, "changes", self.conv_id, phase=phase, comment=comment)
        self._say(f"Tú: {elicit.phase_message(phase, comment=comment)}")
        prev = elicit.advance(self.ctx.conn, self.conv_id, "changes")
        self._bar()
        self._start_turn(elicit.phase_message(prev, comment=comment))

    def _discard(self) -> None:
        elicit.advance(self.ctx.conn, self.conv_id, "discard")
        service.spec_event(self.ctx, "discarded", self.conv_id)
        self._close()

    def _make_tasks(self) -> None:
        row = self.ctx.conn.execute("SELECT spec_dir FROM conversation WHERE id = ?",
                                    (self.conv_id,)).fetchone()
        try:
            result = service.spec_tasks(self.ctx, Path(row["spec_dir"]), origin="spec")
        except service.OpError as e:
            self._say(f"No se pudieron crear las tareas: {e}")
            self.notify(str(e), severity="error")
            return self._enable()
        made = result["created"] or result["existing"]
        self._say(f"Tareas en borrador: {made}. Revísalas con `umbra task list` y acéptalas "
                  "con `umbra task accept`. Pulsa q para salir.")
        self._go("next")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if event.input.id != "entry":  # el Input de AskText también burbujea hasta aquí
            return
        event.input.value = ""
        if not text:
            return
        if elicit.phase_of(self.ctx.conn, self.conv_id) in REVIEWS:
            self._changes(text)
        else:
            self._answer(text)

    def on_key(self, event) -> None:
        if event.key == "q" and self.query_one("#entry", Input).disabled \
                and elicit.phase_of(self.ctx.conn, self.conv_id) == "done":
            self._close()


class SpecApp(App):
    """`umbra spec new/resume` fuera de watch: la pantalla de spec como única pantalla."""

    CSS_PATH = "watch.tcss"

    def __init__(self, ctx: service.Ctx, idea: str, exe: str = "claude",
                 conv_id: str = "", lock: tuple[str, int] | None = None,
                 origin: str = "spec"):
        super().__init__()
        self.spec_screen = SpecScreen(ctx, idea, exe, conv_id, lock, origin)

    def get_default_screen(self) -> Screen:
        return self.spec_screen

    @property
    def lines(self) -> list[str]:
        return self.spec_screen.lines

    def on_mount(self) -> None:
        apply_saved_theme(self)
