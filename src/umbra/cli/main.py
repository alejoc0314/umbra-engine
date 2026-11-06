"""Punto de entrada de la CLI `umbra`."""

import sys

import typer

from umbra.cli import agents, chat, db, explain, findings, management, routines, selfupdate, unified
from umbra.cli import constitution as constitution_cli
from umbra.cli import design as design_cli
from umbra.cli import lessons as lessons_cli
from umbra.cli import memory as memory_cli
from umbra.cli import onboard as onboard_cli
from umbra.cli import spec as spec_cli
from umbra.unified.version import label

# Windows arranca la consola en cp1252: sin esto, un «−» o un «✓» en un aviso tumba el comando
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

app = typer.Typer(
    name="umbra",
    help="umbra-engine: orquestador de agentes de IA (Unified · Management · Blocks · "
    "Routines · Actions).",
    no_args_is_help=True,
    add_completion=False,
)

# Unified
app.command()(unified.init)
app.command()(unified.doctor)
app.command()(unified.status)
app.command()(explain.explain)
app.command()(unified.watch)
app.command("projects")(unified.projects_cmd)
app.command()(unified.new)
app.add_typer(unified.playbook_app, name="playbook")
app.add_typer(unified.pack_app, name="pack")
app.add_typer(design_cli.app, name="design")
app.command("onboard")(onboard_cli.onboard)
app.add_typer(constitution_cli.app, name="constitucion")
app.command()(unified.metrics)
app.command("self-update")(selfupdate.self_update)
# Management
app.add_typer(management.app, name="task")
app.command()(management.plan)
app.add_typer(spec_cli.app, name="spec")
app.add_typer(memory_cli.app, name="memory")
app.add_typer(memory_cli.context_app, name="context")
app.add_typer(lessons_cli.app, name="lesson")
# Agentes y perfiles
app.add_typer(agents.agent_app, name="agent")
app.add_typer(agents.profile_app, name="profile")
# Conversación
app.command()(chat.chat)
app.command("_hook", hidden=True)(chat.hook_cmd)
# Routines / Blocks / Actions
app.command()(routines.run)
app.command()(routines.log)
app.command()(routines.evidence)
app.command()(routines.approve)
app.command()(routines.reject)
app.add_typer(findings.app, name="finding")
app.add_typer(db.app, name="db")
app.command()(routines.pause)
app.command()(routines.resume)
app.command()(routines.cancel)
app.command()(routines.retry)
app.command("open")(routines.open_)
app.command()(routines.done)
app.command()(routines.night)
app.command("bridge")(routines.bridge_cmd)
app.command("exec")(routines.exec_)
app.command("_worker", hidden=True)(routines.worker_cmd)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"umbra {label()}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True,
                                 help="Muestra la versión."),
) -> None:
    pass


if __name__ == "__main__":
    app()
