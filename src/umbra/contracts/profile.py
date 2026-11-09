"""Perfil: una forma de trabajar sobre un agente."""

from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

# shell: comandos libres (preparar la app: seeds locales, servicios); git de escritura vetado
ACTIONS = ("read", "search", "edit", "run_tests", "run_lint", "browse", "render", "shell")


IDLE_MINUTES = 10  # sin señales de vida durante esto, el agente se da por colgado
CEILING_FACTOR = 3  # techo de seguridad: max_minutes × esto


class Limits(BaseModel):
    """`max_minutes` es lo que se espera que tarde. El agente se corta si pasa `idle_minutes`
    sin dar señales de vida (por defecto, lo menor entre `max_minutes` y 10) o si llega al techo
    de `max_minutes × 3`: uno que avanza no se corta por el reloj."""

    max_minutes: float = 20
    idle_minutes: float | None = None
    max_cost_usd: Decimal = Decimal("2.00")

    def idle_s(self) -> float:
        return 60 * (self.idle_minutes or min(self.max_minutes, IDLE_MINUTES))

    def ceiling_s(self) -> float:
        return 60 * self.max_minutes * CEILING_FACTOR


class McpServer(BaseModel):
    """Un servidor MCP que el perfil necesita (solo Claude Code). En `command`, `args` y `env`,
    `{profile_dir}` es la carpeta del perfil (p. ej. dentro de un paquete) y `{workspace}` la de
    la tarea. Sin secretos aquí: el servidor hereda tu entorno."""

    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class Profile(BaseModel):
    name: str
    agent: str
    roles: list[str]
    model: str | None = None
    fallback_model: str | None = None  # Claude Code: si el modelo no está disponible, este
    effort: str | None = None  # Claude Code: low | medium | high | xhigh | max
    reasoning_effort: str | None = None  # hoy solo lo usa Codex
    instructions: str | None = None  # archivo .md junto al .toml
    actions: list[str] = Field(default_factory=lambda: ["read"])
    allowed_paths: list[str] = Field(default_factory=list)  # con edit: solo estas rutas
    mcp: dict[str, McpServer] = Field(default_factory=dict)  # servidores MCP del perfil
    output: str = "stage-output/v1"
    limits: Limits = Field(default_factory=Limits)
    source: Path | None = None  # dónde se cargó (no viene del archivo)

    def instructions_path(self) -> Path | None:
        if not self.instructions or not self.source:
            return None
        return self.source.parent / self.instructions
