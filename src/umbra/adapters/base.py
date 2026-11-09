"""Interfaz de adaptador: cómo umbra lanza un agente concreto."""

import dataclasses
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from umbra.contracts.envelope import Envelope, StageOutput
from umbra.contracts.profile import Profile


@dataclass
class AgentRun:
    envelope: Envelope
    profile: Profile
    workspace: Path
    log_path: Path
    allowed_commands: list[str] = field(default_factory=list)  # comandos registrados permitidos
    resume_session: str | None = None
    output_model: type[BaseModel] = StageOutput  # contrato que debe cumplir la salida


@dataclass
class AgentResult:
    ok: bool
    output: BaseModel | None
    session_id: str | None = None
    cost: Decimal = Decimal(0)
    estimated: bool = False
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    timed_out: bool = False
    error: str | None = None
    resumed: bool = False  # se cortó por tiempo y se retomó su misma sesión


class Adapter(Protocol):
    name: str

    def check(self) -> bool:
        """El binario existe y puede usarse."""

    def run(self, req: AgentRun) -> AgentResult:
        """Ejecuta el agente sobre el workspace y devuelve el resultado validado."""


CONTINUE = ("umbra detuvo tu sesión por tiempo: pasaste demasiado rato sin dar señales de vida o "
            "llegaste al techo de tu bloque. Continúa exactamente donde quedaste, sin repetir lo "
            "que ya hiciste, y termina entregando la salida que se te pidió.")


def timeout_error(proc, limits) -> str:
    """Por qué se cortó, en una frase (empieza por «tiempo agotado»: así lo reconoce explain)."""
    if proc.idle:
        return f"tiempo agotado: {limits.idle_s() / 60:g} min sin señales de vida"
    return f"tiempo agotado: llegó al techo de {limits.ceiling_s() / 60:g} min"


def first_id(output: str, *keys: str) -> str | None:
    """El id de sesión que el agente anuncia al arrancar (para retomarla si se corta)."""
    for line in output.splitlines():
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        for key in keys:
            if isinstance(event, dict) and event.get(key):
                return str(event[key])
    return None


def resume_on_timeout(run: Callable[["AgentRun"], "AgentResult"], req: "AgentRun",
                      result: "AgentResult") -> "AgentResult":
    """Un corte por tiempo con la sesión conocida se retoma una vez, con su contexto: el agente
    sigue donde iba en lugar de empezar de cero."""
    if not result.timed_out or not result.session_id or req.resume_session:
        return result
    again = run(dataclasses.replace(req, resume_session=result.session_id))
    again.cost += result.cost
    again.resumed = True
    if again.timed_out:
        again.error = f"{again.error} (también tras retomar la sesión)"
    return again


def render_prompt(envelope: Envelope, commands: list[str]) -> str:
    if commands:
        allowed = ("Los únicos comandos de shell permitidos son estos, escritos exactamente así "
                   "(puedes añadir argumentos al final): "
                   + ", ".join(f"`{c}`" for c in commands) + ". Cualquier otro será denegado.")
    else:
        allowed = "No tienes permitido ejecutar comandos de shell."
    notes = ""
    if envelope.project_notes:
        notes = ("Contexto del proyecto y decisiones ya tomadas por la persona responsable "
                 f"(respétalas):\n\n{envelope.project_notes.rstrip()}\n\n")
    if envelope.design:
        notes += ("Diseño aprobado por la persona (pantallas en `design`; míralas con Read antes "
                  "de empezar). Al construir, maqueta fiel a él: estructura, jerarquía, colores, "
                  "tipografía y espaciado. Al verificar, compara la app con él y reporta como "
                  "hallazgo cada diferencia visible.\n\n")
    return (
        "Ejecuta la etapa indicada en este sobre de umbra-engine. Trabaja solo en el directorio "
        f"actual. {allowed} Responde con la salida estructurada solicitada.\n\n{notes}"
        f"```json\n{envelope.model_dump_json(indent=2)}\n```\n"
    )
