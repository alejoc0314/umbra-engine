"""Operaciones git con argumentos explícitos (sin hooks en commits del motor)."""

import subprocess
from pathlib import Path


class GitError(Exception):
    pass


def run(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def ok(cwd: Path, *args: str) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True).returncode == 0


def head(cwd: Path, ref: str = "HEAD") -> str:
    return run(cwd, "rev-parse", ref)


def head_or_none(cwd: Path, ref: str = "HEAD") -> str | None:
    """Como head(), pero None si la referencia no existe (p. ej. repo sin commits)."""
    try:
        return run(cwd, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except GitError:
        return None


def remote_base(cwd: Path, branch: str) -> str | None:
    """SHA de la rama base en el remoto (lo integrado en GitHub), o de la local si no hay remoto.

    Lo que se integra con PRs llega al remoto, no a la copia local: partir de la local haría
    trabajar sobre una base vieja."""
    if ok(cwd, "fetch", "-q", "origin", branch):
        if sha := head_or_none(cwd, f"refs/remotes/origin/{branch}"):
            return sha
    return head_or_none(cwd, branch)


def is_ancestor(cwd: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    return ok(cwd, "merge-base", "--is-ancestor", ancestor, descendant)


def merge(cwd: Path, ref: str) -> list[str]:
    """Fusiona `ref` en la rama actual. Devuelve los archivos en conflicto ([] = limpio).
    Si hay conflictos, la fusión queda a medias (con marcadores) para resolverla."""
    ok(cwd, "merge", "--no-edit", "--no-verify", ref)
    return unmerged_files(cwd)


def unmerged_files(cwd: Path) -> list[str]:
    return [f for f in run(cwd, "diff", "--name-only", "--diff-filter=U").splitlines() if f]


def files_with_conflict_markers(cwd: Path, files: list[str]) -> list[str]:
    marked = []
    for name in files:
        path = cwd / name
        if path.exists() and any(line.startswith(("<<<<<<< ", ">>>>>>> ", "=======")) for line
                                 in path.read_text(encoding="utf-8", errors="replace")
                                 .splitlines()):
            marked.append(name)
    return marked


def has_changes(cwd: Path) -> bool:
    return bool(run(cwd, "status", "--porcelain"))


def changed_files(cwd: Path, base: str, head_ref: str = "HEAD") -> list[tuple[str, str]]:
    """(estado A/M/D, ruta) entre dos commits."""
    out = run(cwd, "diff", "--name-status", "--no-renames", base, head_ref)
    return [tuple(line.split("\t", 1)) for line in out.splitlines() if line]


def edit_summary(cwd: Path, base: str, head_ref: str, path: str) -> tuple[list[str], list[str]]:
    """(líneas quitadas, líneas añadidas) de un archivo entre dos commits."""
    diff = run(cwd, "diff", "-U0", base, head_ref, "--", path).splitlines()
    removed = [ln[1:] for ln in diff if ln.startswith("-") and not ln.startswith("---")]
    added = [ln[1:] for ln in diff if ln.startswith("+") and not ln.startswith("+++")]
    return removed, added


def commit_all(cwd: Path, message: str) -> str:
    run(cwd, "add", "-A")
    run(cwd, "commit", "--no-verify", "-q", "-m", message)
    return head(cwd)


def diff_stat(cwd: Path, base: str, head_ref: str = "HEAD") -> str:
    return run(cwd, "diff", "--stat", f"{base}..{head_ref}")


def remote_branch_sha(cwd: Path, branch: str) -> str | None:
    out = run(cwd, "ls-remote", "origin", f"refs/heads/{branch}")
    return out.split()[0] if out else None


def push(cwd: Path, branch: str) -> None:
    run(cwd, "push", "--no-verify", "-q", "origin", f"HEAD:refs/heads/{branch}")


def fast_forward(cwd: Path, branch: str) -> bool:
    """Si la copia local está en `branch` y limpia, la pone al día con origin (solo avance).
    Devuelve si lo hizo: nunca toca una rama distinta ni cambios sin guardar."""
    proc = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], cwd=cwd,
                          capture_output=True, text=True)
    dirty = run(cwd, "status", "--porcelain", "--untracked-files=no")  # sin seguimiento no estorba
    if proc.returncode != 0 or proc.stdout.strip() != branch or dirty:
        return False
    return ok(cwd, "pull", "-q", "--ff-only", "origin", branch)
