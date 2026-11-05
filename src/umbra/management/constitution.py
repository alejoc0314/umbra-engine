"""La constitución del proyecto (`.specify/memory/constitution.md`): verla y enmendarla.

Un agente redacta la enmienda que pide la persona (solo puede tocar ese archivo) y la persona
la aprueba (commit) o la descarta (se restaura). Ninguna enmienda queda sin su aprobación."""

from pathlib import Path

from umbra.actions import git
from umbra.management import onboarding as ob
from umbra.management.memory import CONSTITUTION
from umbra.unified.events import add_event


class ConstitutionError(Exception):
    pass


def path(root: Path) -> Path:
    return root / CONSTITUTION


def show(root: Path) -> str:
    f = path(root)
    if not f.is_file():
        raise ConstitutionError("este proyecto no tiene constitución todavía: `umbra onboard` "
                                "la redacta a partir del código")
    return f.read_text(encoding="utf-8", errors="replace")


def pending(root: Path) -> str:
    """El diff de una enmienda redactada y aún sin decidir (vacío si no hay)."""
    if not path(root).is_file():
        return ""
    if not git.ok(root, "ls-files", "--error-unmatch", CONSTITUTION):
        return path(root).read_text(encoding="utf-8")  # nueva: todo es enmienda
    return git.run(root, "diff", "--", CONSTITUTION)


def amend(conn, root: Path, udir: Path, text: str, origin: str = "cli") -> str:
    """Redacta la enmienda y devuelve el diff para que la persona decida."""
    show(root)
    text = text.strip()
    if not text:
        raise ConstitutionError("di qué quieres cambiar en la constitución")
    before = ob._dirty(root)
    result, invocation = ob.agent(
        root, udir, "onboarder", "Enmendar la constitución", text,
        ["# Constitución actual\n\n" + show(root)])
    others = sorted(p for p in ob._dirty(root) - before if p != CONSTITUTION)
    if others:
        for p in others:
            if git.ok(root, "ls-files", "--error-unmatch", p):
                git.ok(root, "checkout", "--", p)
            else:
                (root / p).unlink(missing_ok=True)
        raise ConstitutionError(f"el redactor tocó archivos que no debía: {', '.join(others)}")
    if not result.ok:
        raise ConstitutionError(result.error or "el redactor falló")
    ob.record_usage(conn, result, invocation)
    diff = pending(root)
    if not diff:
        raise ConstitutionError("el redactor no cambió nada")
    add_event(conn, None, "constitution.drafted", origin, request=text)
    return diff


def accept(conn, root: Path, origin: str = "cli") -> str:
    if not pending(root):
        raise ConstitutionError("no hay ninguna enmienda pendiente")
    git.run(root, "add", "--", CONSTITUTION)
    git.run(root, "commit", "--no-verify", "-q", "-m", "umbra: enmienda de la constitución",
            "--", CONSTITUTION)
    sha = git.head(root)
    add_event(conn, None, "constitution.amended", origin, sha=sha)
    return sha


def discard(conn, root: Path, origin: str = "cli") -> None:
    if not pending(root):
        raise ConstitutionError("no hay ninguna enmienda pendiente")
    git.run(root, "checkout", "--", CONSTITUTION)
    add_event(conn, None, "constitution.discarded", origin)
