"""Perfil: una forma de trabajar sobre un agente."""

from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

ACTIONS = ("read", "search", "edit", "run_tests", "run_lint", "browse", "render")


class Limits(BaseModel):
    max_minutes: float = 20
    max_cost_usd: Decimal = Decimal("2.00")


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
