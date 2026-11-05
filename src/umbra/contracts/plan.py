"""Contrato del proponente: de una spec a tareas propuestas."""

from pydantic import BaseModel, Field


class ProposedTask(BaseModel):
    title: str
    about: str = ""  # para la persona: qué cambia y para qué, sin código
    description: str  # para el agente: indicaciones técnicas
    acceptance: list[str]
    scope: list[str]
    priority: int = Field(ge=1, le=3)
    depends_on: list[int]  # índices (desde 0) de otras tareas propuestas


class PlanOutput(BaseModel):
    tasks: list[ProposedTask]
    questions: list[str]
