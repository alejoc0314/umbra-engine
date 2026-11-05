"""Salida humana (rich) o JSON para todos los comandos."""

import json
from collections.abc import Callable

import typer
from rich.console import Console

console = Console()
err_console = Console(stderr=True)


def emit(data, as_json: bool, render: Callable[[Console], None]) -> None:
    if as_json:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        render(console)


def fail(message: str, code: int = 1, as_json: bool = False) -> None:
    if as_json:
        typer.echo(json.dumps({"error": message}, ensure_ascii=False))
    else:
        err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code)
