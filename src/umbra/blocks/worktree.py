"""Un git worktree por ejecución."""

import re
import shutil
from pathlib import Path

from umbra.actions import git

WORKTREES = "worktrees"


def slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].rstrip("-") or "task"


def branch_name(task_number: int, title: str) -> str:
    return f"umbra/{task_number}-{slug(title)}"


def ensure(root: Path, udir: Path, run_id: str, branch: str, base_sha: str,
           path: Path | None = None) -> Path:
    """Crea el worktree si no existe; idempotente. `path`: otra ubicación (el de un repo
    dentro de la carpeta de una tarea entre repos)."""
    path = path or udir / WORKTREES / run_id[:12]
    if (path / ".git").exists():
        return path
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    git.run(root, "worktree", "prune")
    if git.ok(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"):
        git.run(root, "worktree", "add", str(path), branch)
    else:
        git.run(root, "worktree", "add", "-b", branch, str(path), base_sha)
    return path


def remove(root: Path, path: Path) -> None:
    if path.exists():
        git.ok(root, "worktree", "remove", "--force", str(path))
        shutil.rmtree(path, ignore_errors=True)
    git.ok(root, "worktree", "prune")
