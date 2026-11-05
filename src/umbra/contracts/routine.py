"""Rutina: pipeline declarado en YAML."""

from typing import Literal

from pydantic import BaseModel, Field

AGENT_STAGES = ("plan", "design", "build", "review", "verify")
STAGES = (*AGENT_STAGES, "scan", "ship")


class Stage(BaseModel):
    name: Literal["plan", "design", "build", "review", "verify", "scan", "ship"]
    profile: str | None = None
    fallback_profile: str | None = None  # si el agente falla (p. ej. modelo saturado)
    escalation: list[str] = Field(default_factory=list)  # perfiles más fuertes, en orden
    arbiter: str | None = None  # review: tercer agente cuando constructor y revisor se enredan
    critic: str | None = None  # design: un segundo agente critica las pantallas con una rúbrica
    max_fix_cycles: int = 2
    block_on: Literal["low", "medium", "high", "critical"] = "high"
    human_approval: bool = True


class Routine(BaseModel):
    name: str
    stages: list[Stage] = Field(min_length=1)

    def stage(self, name: str) -> Stage | None:
        return next((s for s in self.stages if s.name == name), None)
