"""Pull requests con la CLI `gh` (usa el login existente del usuario)."""

import json
import subprocess
from pathlib import Path

from umbra.blocks.process import resolve

TIMEOUT = 60


class GhError(Exception):
    pass


def _gh(cwd: Path, *args: str) -> str:
    try:
        proc = subprocess.run([resolve("gh"), *args], cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired as e:
        raise GhError(f"gh {args[0]} {args[1]}: sin respuesta en {TIMEOUT}s") from e
    if proc.returncode != 0:
        raise GhError(f"gh {' '.join(args[:2])}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def find_pr(cwd: Path, branch: str) -> dict | None:
    out = _gh(cwd, "pr", "list", "--head", branch, "--state", "all",
              "--json", "number,url,state,headRefOid")
    prs = json.loads(out or "[]")
    return prs[0] if prs else None


def create_pr(cwd: Path, branch: str, base: str, title: str, body: str) -> dict:
    """Crea el PR; si falla o no responde, busca uno existente antes de rendirse."""
    try:
        _gh(cwd, "pr", "create", "--head", branch, "--base", base, "--title", title,
            "--body", body)
    except GhError:
        existing = find_pr(cwd, branch)
        if existing:
            return existing
        raise
    pr = find_pr(cwd, branch)
    if not pr:
        raise GhError(f"PR creado pero no encontrado para {branch}")
    return pr


def view_pr(cwd: Path, number: int) -> dict:
    return json.loads(_gh(cwd, "pr", "view", str(number),
                          "--json", "number,url,state,headRefOid,mergeCommit,mergeable"))


def merge_pr(cwd: Path, number: int, head_sha: str) -> None:
    _gh(cwd, "pr", "merge", str(number), "--squash", "--match-head-commit", head_sha)


def close_pr(cwd: Path, number: int, comment: str) -> None:
    _gh(cwd, "pr", "close", str(number), "--comment", comment)



def repo_create(cwd: Path, name: str) -> None:
    """Crea el repo privado en GitHub desde la carpeta y publica la rama actual."""
    _gh(cwd, "repo", "create", name, "--private", "--source", ".", "--push")
