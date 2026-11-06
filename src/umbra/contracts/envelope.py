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
    context: str | None = None  # paquete de Explorar para esta tarea (con tope)


class DesignOption(BaseModel):
    """Una dirección visual propuesta para que la persona elija."""

    name: str = Field(description="Nombre corto y evocador de la dirección")
    images: list[str] = Field(description="Pantallas exportadas de esta dirección (rutas)")


class StageOutput(BaseModel):
    """Lo que el agente devuelve (salida estructurada)."""

    status: Literal["done", "blocked"] = "done"
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    needs_design: bool | None = Field(
        None, description="Solo PLAN: true si la tarea crea o cambia algo que la persona ve")
    images: list[str] = Field(
        default_factory=list,
        description="Solo DESIGN: rutas (dentro de design/) de las pantallas exportadas")
    options: list[DesignOption] = Field(
        default_factory=list,
        description="Solo DESIGN: 2 o 3 direcciones visuales distintas para que la persona elija")


class LessonDraft(BaseModel):
    """Lo que devuelve el redactor de lecciones (spec 035). El motor lo valida y decide."""

    skip: bool = Field(False, description="true si no hay nada generalizable (p. ej. red)")
    text: str = Field("", description="Regla corta e imperativa, ≤ 280 caracteres")
    zone: list[str] = Field(default_factory=list,
                            description="Globs relativos al proyecto; [] = todo el proyecto")
    same_as: int | None = Field(None, description="Equivale a la lección L<n> recibida")
    conflicts_with: list[int] = Field(default_factory=list,
                                      description="Contradice estas lecciones recibidas")


def output_schema() -> dict:
    return StageOutput.model_json_schema()
