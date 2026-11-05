"""Contrato del agente de resumen: qué se hizo, contado para quien aprueba."""

from pydantic import BaseModel, Field


class SummaryOutput(BaseModel):
    summary: str  # explicación conceptual, sin nombres de código
    observations: list[str] = Field(default_factory=list)  # una por hallazgo, mismo orden
