"""Comandos de conversación: chat y el hook interno."""

import json
import sys
from pathlib import Path

import typer

from umbra.chat import hook, launcher
from umbra.cli import context
from umbra.unified.output import fail


def chat(message: str | None = typer.Argument(
        None, help="Pregunta de una línea (o `-` para leerla de la entrada estándar); sin ella "
                   "abre la sesión interactiva."),
        as_json: bool = typer.Option(False, "--json", help="Salida en JSON"),
        allow_changes: bool = typer.Option(
            False, "--allow-changes",
            help="Permite que Claude ejecute comandos que cambian estado (nunca aprobar, "
                 "rechazar, push, merge ni editar la política)"),
        continue_: bool = typer.Option(
            False, "--continue", help="Sigue la última conversación de `umbra chat` del proyecto"),
        session: str | None = typer.Option(
            None, "--session", help="Continúa la conversación con este identificador")) -> None:
    """Abre una conversación con Claude sobre este proyecto (opcional; todo existe como comando)."""
    def error(msg: str):
        if as_json:
            typer.echo(json.dumps({"status": "error", "answer": None, "session_id": None,
                                   "cost_usd": "0", "commands": [], "error": msg},
                                  ensure_ascii=False))
            raise typer.Exit(2)
        fail(msg, code=2)

    if message == "-":
        message = sys.stdin.read()
    if message is not None and not message.strip():
        error("el mensaje está vacío")
    if message is None and as_json:
        error("--json requiere un mensaje")
    if message is None and allow_changes:
        error("--allow-changes requiere un mensaje")
    if continue_ and session is not None:
        error("usa --continue o --session, no las dos")
    if message is None and (continue_ or session is not None):
        error("estas opciones necesitan un mensaje")
    ctx = context.load(as_json)
    resume = session
    if continue_:
        resume = launcher.last_session(ctx.udir)
        if resume is None:
            typer.echo("no hay conversación anterior; empiezo una nueva", err=True)
    try:
        if message is None:
            raise typer.Exit(launcher.launch(ctx.root, ctx.udir, ctx.conn, ctx.config))
        res = launcher.ask(ctx.root, ctx.udir, ctx.conn, ctx.config, message.strip(),
                          allow_changes=allow_changes, resume=resume)
    except (FileNotFoundError, ValueError) as e:
        error(str(e))
    if as_json:
        typer.echo(json.dumps(res, ensure_ascii=False))
        raise typer.Exit(0 if res["status"] == "ok" else 1)
    if res["status"] != "ok":
        typer.echo(res["error"], err=True)
        raise typer.Exit(1)
    typer.echo(res["answer"])


def hook_cmd(kind: str = typer.Argument(..., help="chat-event")) -> None:
    """(interno) Hook de Claude Code."""
    if kind == "chat-event":
        hook.main(sys.stdin.read(), Path.cwd())
