"""Temas de umbra: colores con nombre por estado y por etapa, disponibles en todo tema.

`$state-*` y `$stage-*` se usan en el CSS y en los renderizados Rich; los temas integrados de
Textual (dracula incluido) los reciben desde `VARIABLES` y «umbra» los redefine a su paleta.
"""

import json

from textual.theme import Theme

from umbra.unified import config as cfg

STATE_KEYS = ("blocked", "failed", "waiting", "running", "queued", "paused", "done",
              "cancelled", "draft", "ready")
STAGE_KEYS = ("plan", "build", "review", "verify", "scan", "ship", "summary")

# valores por defecto (se ven bien sobre los temas integrados oscuros y claros)
VARIABLES = {
    "state-blocked": "#F6C177", "state-failed": "#EB6F92", "state-waiting": "#9CCFD8",
    "state-running": "#56B6C2", "state-queued": "#8A8FA3", "state-paused": "#E0AF68",
    "state-done": "#9ECE6A", "state-cancelled": "#6E6A86", "state-draft": "#8A8FA3",
    "state-ready": "#C4A7E7",
    "stage-plan": "#B4BEFE", "stage-build": "#89B4FA", "stage-review": "#F5C2E7",
    "stage-verify": "#94E2D5", "stage-scan": "#FAB387", "stage-ship": "#A6E3A1",
    "stage-summary": "#CDD6F4",
}

UMBRA = Theme(
    name="umbra", primary="#C4A7E7", secondary="#908CAA", accent="#EBBCBA",
    success="#9ECE6A", warning="#F6C177", error="#EB6F92", foreground="#E0DEF4",
    background="#16141F", surface="#1F1D2E", panel="#26233A", dark=True,
    variables=VARIABLES | {"footer-key-foreground": "#EBBCBA",
                           "block-cursor-background": "#393552",
                           "block-cursor-foreground": "#E0DEF4",
                           "block-cursor-text-style": "bold",
                           "border": "#393552"},
)

UMBRA_LIGHT = Theme(
    name="umbra-claro", primary="#907AA9", secondary="#797593", accent="#B4637A",
    success="#56949F", warning="#EA9D34", error="#B4637A", foreground="#575279",
    background="#FAF4ED", surface="#FFFAF3", panel="#F2E9E1", dark=False,
    variables=VARIABLES | {
        "state-blocked": "#EA9D34", "state-failed": "#B4637A", "state-waiting": "#286983",
        "state-running": "#286983", "state-queued": "#9893A5", "state-paused": "#EA9D34",
        "state-done": "#56949F", "state-cancelled": "#9893A5", "state-draft": "#9893A5",
        "state-ready": "#907AA9", "stage-plan": "#907AA9", "stage-build": "#286983",
        "stage-review": "#B4637A", "stage-verify": "#56949F", "stage-scan": "#EA9D34",
        "stage-ship": "#56949F", "stage-summary": "#575279",
        "footer-key-foreground": "#B4637A", "border": "#DFDAD9"},
)

THEMES = (UMBRA, UMBRA_LIGHT)
DEFAULT_THEME = "umbra"

# estado de la ejecución / tarea → clave de color
STATE_OF = {"BLOCKED": "blocked", "FAILED": "failed", "WAITING_APPROVAL": "waiting",
            "RUNNING": "running", "QUEUED": "queued", "PAUSED": "paused", "SUCCEEDED": "done",
            "CANCELLED": "cancelled", "draft": "draft", "accepted": "ready", "done": "done",
            "dropped": "cancelled"}


def state_key(status: str | None) -> str:
    return STATE_OF.get(status or "", "queued")


# ---------- preferencia de la persona (~/.umbra/watch.json) ----------
PREFS = "watch.json"


def load_prefs() -> dict:
    try:
        return json.loads((cfg.umbra_home() / PREFS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_prefs(**changes) -> None:
    try:
        path = cfg.umbra_home() / PREFS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(load_prefs() | changes), encoding="utf-8")
    except OSError:
        pass  # una preferencia que no se guarda no debe romper la pantalla


def apply_saved_theme(app) -> str | None:
    """Registra los temas de umbra y aplica el guardado (o «umbra»). Devuelve un aviso si el
    guardado ya no existe."""
    for t in THEMES:
        app.register_theme(t)
    saved = load_prefs().get("theme")
    warning = None
    if saved and saved not in app.available_themes:
        warning = f"El tema guardado «{saved}» ya no existe; se usa «{DEFAULT_THEME}»."
        saved = None
    app.theme = saved or DEFAULT_THEME
    return warning
