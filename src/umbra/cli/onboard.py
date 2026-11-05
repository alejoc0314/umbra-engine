"""`umbra onboard`: umbra estudia a fondo un proyecto ya iniciado antes de trabajar en él."""

import typer

from umbra.cli import context
from umbra.management.onboarding import OnboardingError
from umbra.routines.onboard_talk import OnboardTalk
from umbra.unified.output import console, fail


def onboard(fresh: bool = typer.Option(False, "--de-cero", help="Empezar otra vez")) -> None:
    """Estudia el proyecto (reconocimiento, línea base, exploradores), te pregunta lo que el
    código no dice y redacta CONTEXT.md, la constitución y el inventario para que los apruebes.
    Retoma donde quedó."""
    ctx = context.load(False)
    root = ctx.root
    ctx.conn.close()
    choices: list[str] = []

    def say(text: str, buttons=None) -> None:
        console.print(text, highlight=False, markup=False)
        choices.clear()
        for row in buttons or []:
            for label, data in row:
                choices.append(data)
                console.print(f"  {len(choices)}. {label}", highlight=False, markup=False)

    try:
        talk = OnboardTalk.start(root, say, "cli", fresh)
        while not talk.done and talk.pending:
            try:
                reply = typer.prompt(">", default="", show_default=False).strip()
            except typer.Abort:
                console.print("\nQueda a medias: `umbra onboard` retoma donde quedó.")
                raise typer.Exit(0) from None
            if reply.isdigit() and 1 <= int(reply) <= len(choices):
                kind, _, value = choices[int(reply) - 1].partition(":")
                (talk.option if kind == "oq" else talk.decide)(value, say)
            elif reply:
                talk.text(reply, say)
    except OnboardingError as e:
        fail(f"{e}. `umbra onboard` lo retoma.")
