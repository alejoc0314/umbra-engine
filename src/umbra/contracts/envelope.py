"""Sobre de entrada/salida entre el motor y los agentes (interfaz estable, versionada)."""

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1"

Severity = Literal["info", "low", "medium", "high", "critical"]


class Finding(BaseModel):
    severity: Severity
    message: str
    file: str | None = None
    line: int | None = None
    rule: str | None = None


class TaskInfo(BaseModel):
    number: int
    title: str
    description: str = ""
    acceptance: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)


class Envelope(BaseModel):
    """Lo que el motor entrega al agente."""

    schema_version: str = SCHEMA_VERSION
    run_id: str
    stage: str
    attempt_id: str
    input_sha: str
    task: TaskInfo
    plan: str | None = None  # salida de PLAN, contexto para BUILD
    diff: str | None = None  # base..head, para REVIEW y VERIFY
    feedback: list[str] = Field(default_factory=list)  # tests fallidos o retrabajo
    findings: list[Finding] = Field(default_factory=list)
    project_notes: str | None = None  # mapa del repo (CONTEXT.md) + lo aprendido (aprendido.md)
    app_url: str | None = None  # VERIFY con navegador: la app de desarrollo ya levantada
    screenshots_dir: str | None = None  # dónde dejar las capturas (fuera del workspace)
    design: list[str] = Field(default_factory=list)  # pantallas aprobadas (rutas del workspace)


class StageOutput(BaseModel):
    """Lo que el agente devuelve (salida estructurada)."""

    status: Literal["done", "blocked"] = "done"
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    needs_design: bool | None = None  # PLAN: la tarea crea o cambia interfaz
    images: list[str] = Field(default_factory=list)  # DESIGN: pantallas exportadas (rutas)


def output_schema() -> dict:
    return StageOutput.model_json_schema()
