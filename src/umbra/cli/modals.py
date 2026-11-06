"""Ventanas modales compartidas por watch y la pantalla de spec. Los estilos viven en watch.tcss."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from umbra.unified import explain as ex


class Confirm(ModalScreen[bool]):
    BINDINGS = [("y", "answer(True)", "Sí"), ("n", "answer(False)", "No"),
                ("escape", "answer(False)", "No")]

    def __init__(self, question: str, body: str = "", yes: str = "Sí"):
        super().__init__()
        self.question, self.body, self.yes = question, body, yes

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static(self.question, classes="question", markup=False)
            if self.body:
                with VerticalScroll(id="body"):
                    yield Static(self.body, markup=False)
            with Horizontal(id="buttons"):
                yield Button(f"{self.yes} (y)", id="yes", variant="warning")
                yield Button("No (n)", id="no")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()  # lo seguro es lo que está seleccionado

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)


class AskText(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancelar")]

    def __init__(self, question: str, default: str = ""):
        super().__init__()
        self.question, self.default = question, default

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static(self.question, markup=False)
            yield Input(value=self.default, id="answer")
            yield Static("Enter confirma · Esc cancela", classes="hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or self.default)

    def action_cancel(self) -> None:
        self.dismiss(None)


class PickStage(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancelar")]

    def __init__(self, stages: list[str], suggested: str):
        super().__init__()
        self.stages, self.suggested = stages, suggested

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static("¿Desde qué etapa reintentar? (Enter elige · Esc cancela)")
            yield OptionList(*[f"{ex.STAGES.get(s, s)}" + (" (donde quedó)" if s ==
                                                           self.suggested else "")
                               for s in self.stages], id="stages")

    def on_mount(self) -> None:
        options = self.query_one("#stages", OptionList)
        options.highlighted = self.stages.index(self.suggested)
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.stages[event.option_index])

    def action_cancel(self) -> None:
        self.dismiss(None)


class PickOne(ModalScreen[int | None]):
    BINDINGS = [("escape", "cancel", "Cancelar")]

    def __init__(self, question: str, options: list[str]):
        super().__init__()
        self.question, self.options = question, options

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static(f"{self.question} (Enter elige · Esc cancela)", markup=False)
            yield OptionList(*self.options, id="options")

    def on_mount(self) -> None:
        self.query_one("#options", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_index)

    def action_cancel(self) -> None:
        self.dismiss(None)


LESSON_COLORS = {"proposed": "#ffb86c", "approved": "#50fa7b", "retired": "#6272a4",
                 "discarded": "#6272a4"}
LESSON_MARK = {"proposed": "●", "approved": "✓", "retired": "↺", "discarded": "−"}
LESSON_STATUS = {"proposed": "propuesta", "approved": "aprobada", "discarded": "descartada",
                 "retired": "retirada"}


class LessonsScreen(Screen[None]):
    """Panel Lecciones de watch: a la izquierda la lista (por decidir primero), a la derecha la
    lección elegida con sus orígenes. Decide la persona: a aprobar, d descartar, x retirar."""

    BINDINGS = [("escape", "close", "Volver a tareas"), ("l", "close", "Tareas"),
                ("j", "move(1)", "Bajar"), ("k", "move(-1)", "Subir"),
                ("a", "approve", "Aprobar…"), ("d", "discard", "Descartar"),
                ("x", "retire", "Retirar"), ("f", "toggle_all", "Cambiar vista"),
                ("h", "harvest", "Cosechar ahora")]
    DEFAULT_CSS = """
    LessonsScreen { layout: vertical; }
    LessonsScreen #lessons-title { height: 1; padding: 0 1; }
    LessonsScreen #lessons-body { height: 1fr; }
    LessonsScreen #lessons-list { width: 65%; border: none; }
    LessonsScreen #lesson-detail { width: 35%; border-left: solid #44475a; padding: 0 2; }
    LessonsScreen #lessons-hidden, LessonsScreen #lessons-keys { height: 1; padding: 0 1;
        color: #6272a4; }
    """

    def __init__(self, root):
        super().__init__()
        self.root, self.all, self.items, self.rows = root, False, [], []

    def compose(self) -> ComposeResult:
        yield Static("", id="lessons-title")
        with Horizontal(id="lessons-body"):
            yield OptionList(id="lessons-list")
            with VerticalScroll(id="lesson-detail"):
                yield Static("", id="lesson-text")
        yield Static("", id="lessons-hidden")
        yield Static(Text.assemble(("j k", "bold #bd93f9"), " moverse   ",
                                   ("f", "bold #bd93f9"), " cambiar vista   ",
                                   ("h", "bold #bd93f9"), " cosechar ahora   ",
                                   ("Esc", "bold #bd93f9"), " volver a tareas"),
                     id="lessons-keys")

    def on_mount(self) -> None:
        self.reload()
        self.query_one("#lessons-list", OptionList).focus()

    def _call(self, op):
        from umbra import service
        ctx = service.load(self.root)
        try:
            return op(service, ctx)
        except service.OpError as e:
            self.app.notify(str(e), severity="error")
            return None
        finally:
            ctx.conn.close()

    # ---------- pintar ----------
    def reload(self, keep: str | None = None) -> None:
        everything = self._call(lambda s, ctx: s.lesson_list(ctx, all_=True)) or []
        shown = everything if self.all else [i for i in everything
                                             if i["status"] in ("proposed", "approved")]
        groups = [("POR DECIDIR", "#ffb86c", [i for i in shown if i["status"] == "proposed"]),
                  ("VIGENTES", "#50fa7b", [i for i in shown if i["status"] == "approved"])]
        if self.all:
            groups.append(("CERRADAS", "#6272a4", [i for i in shown if i["status"] in
                                                   ("retired", "discarded")]))
        options = self.query_one("#lessons-list", OptionList)
        options.clear_options()
        self.rows = []
        for title, color, items in groups:
            if not items:
                continue
            options.add_option(Option(Text(f"{title} · {len(items)}", f"bold {color}"),
                                      disabled=True))
            self.rows.append(None)
            for item in items:
                options.add_option(Option(self._line(item)))
                self.rows.append(item)
        if not shown:
            options.add_option(Option(Text("No hay lecciones todavía.", "dim"), disabled=True))
            self.rows.append(None)
        self.items = shown
        view = "todas" if self.all else "por decidir + vigentes"
        self.query_one("#lessons-title", Static).update(Text.assemble(
            ("Lecciones", "bold"), ("  propuestas primero", "dim"), ("     f", "bold #bd93f9"),
            (f" vista: {view}", "dim")))
        discarded = sum(i["status"] == "discarded" for i in everything)
        retired = sum(i["status"] == "retired" for i in everything)
        self.query_one("#lessons-hidden", Static).update(
            "" if self.all or not (discarded or retired) else
            f"ocultas: − {discarded} descartadas · ↺ {retired} retiradas · f para ver todas")
        target = next((n for n, r in enumerate(self.rows) if r and r["id"] == keep), None)
        target = target if target is not None else next(
            (n for n, r in enumerate(self.rows) if r), None)
        if target is not None:
            options.highlighted = target
        self._detail()

    @staticmethod
    def _line(item: dict) -> Text:
        color = LESSON_COLORS[item["status"]]
        zone = ", ".join(item["zone"]) or "todo el proyecto"
        line = Text.assemble((f"{LESSON_MARK[item['status']]} ", color),
                             (f"{item['id']:<4} ", "bold"), item["text"][:70], "  ",
                             (zone, "#6272a4"))
        if item["stale"]:
            line.append("\n      △ posible obsoleta: ningún archivo cae en su zona", "#8be9fd")
        if item["conflicts"]:
            line.append(f"\n      ≠ conflicto con {', '.join(item['conflicts'])}", "#ff5555")
        return line

    def current(self) -> dict | None:
        n = self.query_one("#lessons-list", OptionList).highlighted
        return self.rows[n] if n is not None and n < len(self.rows) else None

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._detail()

    def _detail(self) -> None:
        box = self.query_one("#lesson-text", Static)
        item = self.current()
        if not item:
            box.update("")
            return
        full = self._call(lambda s, ctx: s.lesson_show(ctx, item["id"])) or item
        color = LESSON_COLORS[item["status"]]
        text = Text.assemble((f"{item['id']} ", "bold #bd93f9"),
                             (f" {LESSON_STATUS[item['status']]} ", f"{color} on #44475a"),
                             "\n\n", (full["text"], "bold"), "\n\n", ("ZONA\n", "dim"),
                             ", ".join(full["zone"]) or "todo el proyecto", "\n\n")
        keys = {"proposed": [("a", "aprobar…"), ("d", "descartar")],
                "approved": [("x", "retirar")], "retired": [("a", "volver a aprobar…")],
                "discarded": []}[item["status"]]
        for key, label in keys:
            text.append(f" {key} ", "bold #bd93f9 on #44475a")
            text.append(f" {label}   ")
        origins = full.get("origins_detail") or []
        text.append(f"\n\nPOR QUÉ SE PROPONE · {len(origins)} orígenes\n", "dim")
        for o in origins:
            text.append(f"#{o['task']} ", "bold #bd93f9")
            text.append(f"{o['stage'] or ''} · {o['created_at'][:10]}\n", "dim")
            text.append(f"{o['detail']}\n")
        if full.get("applied_in"):
            text.append("\nSE APLICÓ EN\n", "dim")
            text.append(", ".join(f"#{a['task']}" for a in full["applied_in"]))
        box.update(text)

    # ---------- acciones ----------
    def action_move(self, step: int) -> None:
        options = self.query_one("#lessons-list", OptionList)
        options.action_cursor_down() if step > 0 else options.action_cursor_up()

    def _decide(self, allowed: tuple[str, ...], op, done: str) -> None:
        item = self.current()
        if not item or item["status"] not in allowed:
            self.app.notify("Esa acción no aplica a esta lección.")
            return
        if self._call(lambda s, ctx: op(s, ctx, item)) is not None:
            self.app.notify(f"{item['id']} {done}.")
            self.reload(keep=item["id"])

    def action_approve(self) -> None:
        item = self.current()
        if not item or item["status"] not in ("proposed", "retired"):
            self.app.notify("Solo se aprueban propuestas o retiradas.")
            return

        def approve(text: str | None) -> None:
            if text is None:
                return
            edited = text if text != item["text"] else None
            self._decide(("proposed", "retired"), lambda s, ctx, i: s.lesson_approve(
                ctx, i["id"], edited, channel="watch"), "aprobada")
        self.app.push_screen(AskText(
            f"Aprobar {item['id']} · texto que se aplicará (si lo editas, el original queda en "
            f"su historial). Se aplicará en las tareas nuevas de "
            f"{', '.join(item['zone']) or 'todo el proyecto'}.", item["text"]), approve)

    def action_discard(self) -> None:
        self._decide(("proposed",), lambda s, ctx, i: s.lesson_discard(
            ctx, i["id"], channel="watch"), "descartada")

    def action_retire(self) -> None:
        self._decide(("approved",), lambda s, ctx, i: s.lesson_retire(
            ctx, i["id"], channel="watch"), "retirada")

    def action_toggle_all(self) -> None:
        self.all = not self.all
        self.reload()

    def action_harvest(self) -> None:
        out = self._call(lambda s, ctx: s.lesson_harvest(ctx, "watch"))
        if out is not None:
            self.app.notify(f"{out['proposed']} lecciones nuevas por decidir.")
            self.reload()

    def action_close(self) -> None:
        self.dismiss(None)


class TextView(ModalScreen[None]):
    BINDINGS = [("escape", "close", "Cerrar"), ("q", "close", "Cerrar"),
                ("t", "toggle", "Técnico/explicado")]

    def __init__(self, title: str, text: str, technical: str | None = None):
        super().__init__()
        self.title_text, self.text, self.technical = title, text, technical
        self.showing_technical = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="box") as box:
            hint = " · t detalle técnico" if self.technical else ""
            box.border_title = f"{self.title_text} (Esc cierra{hint})"
            yield Static(self.text, markup=False, id="text")

    def action_toggle(self) -> None:
        if self.technical:
            self.showing_technical = not self.showing_technical
            self.query_one("#text", Static).update(
                self.technical if self.showing_technical else self.text)

    def action_close(self) -> None:
        self.dismiss(None)
