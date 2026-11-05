"""Contexto común de comandos: envuelve umbra.service y convierte sus errores en salida CLI."""

from pathlib import Path

from umbra import service
from umbra.service import Ctx  # noqa: F401  (se reexporta para los comandos)
from umbra.unified.output import fail


def load(as_json: bool = False, start: Path | None = None) -> service.Ctx:
    try:
        return service.load(start)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)


def task_by_number(ctx: service.Ctx, number: int, as_json: bool = False):
    try:
        return service.task_row(ctx, number)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)


def latest_run(ctx: service.Ctx, number: int, as_json: bool = False):
    try:
        return service.latest_run(ctx, number)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)
