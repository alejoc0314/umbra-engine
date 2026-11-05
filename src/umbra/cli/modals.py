"""Ventanas modales compartidas por watch y la pantalla de spec. Los estilos viven en watch.tcss."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static

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
