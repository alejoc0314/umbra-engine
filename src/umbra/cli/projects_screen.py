"""`umbra watch --all`: la lista de repos con umbra; Enter entra en uno."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header

from umbra.cli import theme


class ProjectsApp(App[str | None]):
    TITLE = "umbra · proyectos"
    BINDINGS = [Binding("enter", "choose", "Entrar"), Binding("q", "quit", "Salir")]
    CSS = "#projects { height: 1fr; border: round $accent; }"

    def __init__(self, rows: list[dict]):
        super().__init__()
        self.rows = rows

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="projects", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        theme.apply_saved_theme(self)
        table = self.query_one("#projects", DataTable)
        table.border_title = "Proyectos (Enter entra · q sale)"
        table.add_columns("proyecto", "stack", "te necesitan", "en marcha", "gasto", "ruta")
        for p in self.rows:
            table.add_row(p["name"], p.get("stack", "-"), str(p["needs"]), str(p["working"]),
                          p["cost"], p["root"], key=p["root"])
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.exit(str(event.row_key.value))

    def action_choose(self) -> None:
        table = self.query_one("#projects", DataTable)
        if table.row_count:
            self.exit(str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value))
