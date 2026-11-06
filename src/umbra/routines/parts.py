"""Partes de una ejecución (spec 033): lo que tiene en cada repo.

Una tarea de un solo repo tiene una sola parte, construida desde la fila `run` (sin tabla
`run_part`): el engine recorre siempre partes y un repo es el caso de una. Una tarea entre repos
de un espacio tiene una parte por repo, en el orden del espacio; su carpeta (`run.worktree`)
agrupa un worktree de cada repo y el agente trabaja en ella."""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from umbra.actions import git
from umbra.blocks import worktree
from umbra.unified import project as proj


@dataclass
class Part:
    repo: str  # "" en una tarea de un solo repo
    root: Path  # el repo
    wt: Path  # su worktree
    config: dict  # la del repo (en un espacio, con la compartida encima)
    base_sha: str
    head_sha: str | None

    def show(self, path: str) -> str:
        """La ruta como la ve la tarea: con el repo delante si hay varios."""
        return f"{self.repo}/{path}" if self.repo else path

    def own(self, path: str) -> str | None:
        """La ruta dentro de este repo de una ruta de la tarea (o None si es de otro)."""
        if not self.repo:
            return path
        head, _, rest = path.replace("\\", "/").partition("/")
        return rest if head == self.repo and rest else None

    @property
    def base_branch(self) -> str:
        return self.config.get("project", {}).get("base_branch", "main")


def fingerprint(shas: dict[str, str | None]) -> str | None:
    """El SHA de la ejecución: el del repo, o una huella de los de cada repo (cambia con
    cualquier commit nuevo en cualquiera de ellos: invalida una aprobación)."""
    if list(shas) == [""]:
        return shas[""]
    if any(s is None for s in shas.values()):
        return None
    text = "\n".join(f"{r}:{s}" for r, s in shas.items())
    return hashlib.sha1(text.encode()).hexdigest()  # noqa: S324 (huella, no seguridad)


def is_multi(conn, run_id: str) -> bool:
    return conn.execute("SELECT 1 FROM run_part WHERE run_id = ? LIMIT 1",
                        (run_id,)).fetchone() is not None


def of(engine, run) -> list[Part]:
    rows = {r["repo"]: r for r in engine.conn.execute(
        "SELECT * FROM run_part WHERE run_id = ?", (run["id"],))}
    if not rows:
        return [Part("", engine.root, Path(run["worktree"] or ""), engine.project,
                     run["base_sha"], run["head_sha"])]
    folder = folder_of(engine, run)
    return [Part(name, path, folder / name, proj.repo_config(engine.space[1], path),
                 rows[name]["base_sha"], rows[name]["head_sha"])
            for name, path in proj.members(*engine.space).items() if name in rows]


def folder_of(engine, run) -> Path:
    return engine.udir / worktree.WORKTREES / run["id"][:12]


def ensure(engine, run) -> Path:
    """La carpeta de la tarea con un worktree de cada repo, en la misma rama (idempotente)."""
    folder = folder_of(engine, run)
    folder.mkdir(parents=True, exist_ok=True)
    for p in of(engine, run):
        worktree.ensure(p.root, engine.udir, run["id"], run["branch"], p.base_sha, path=p.wt)
    return folder


def strays(folder: Path, parts: list[Part]) -> list[str]:
    """Lo que el agente dejó en la carpeta de la tarea fuera de los repos: se borra."""
    names = {p.repo for p in parts}
    out = []
    for item in sorted(folder.iterdir()) if folder.is_dir() else []:
        if item.name in names:
            continue
        out.append(item.name)
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)
    return out


def remove(parts: list[Part], folder: Path) -> None:
    for p in parts:
        worktree.remove(p.root, p.wt)
    shutil.rmtree(folder, ignore_errors=True)


def diff(parts: list[Part], head_of=lambda p: p.head_sha) -> str:
    """El diff de la tarea; con varios repos, cada ruta con su repo delante."""
    out = []
    for p in parts:
        head = head_of(p)
        if not head or head == p.base_sha:
            continue
        prefix = [f"--src-prefix=a/{p.repo}/", f"--dst-prefix=b/{p.repo}/"] if p.repo else []
        out.append(git.run(p.root, "diff", *prefix, f"{p.base_sha}..{head}"))
    return "".join(out)


def diff_stat(parts: list[Part]) -> str:
    if len(parts) == 1:
        p = parts[0]
        return git.diff_stat(p.root, p.base_sha, p.head_sha)
    return "\n".join(f"{p.repo}:\n{git.diff_stat(p.root, p.base_sha, p.head_sha)}"
                     for p in parts if p.head_sha and p.head_sha != p.base_sha)


def numstat(parts: list[Part]) -> str:
    """`git diff --numstat` de la tarea, con el repo delante de cada ruta si hay varios."""
    lines = []
    for p in parts:
        if not p.head_sha or p.head_sha == p.base_sha:
            continue
        for line in git.run(p.root, "diff", "--numstat", p.base_sha, p.head_sha).splitlines():
            added, removed, path = line.split("\t", 2)
            lines.append(f"{added}\t{removed}\t{p.show(path)}")
    return "\n".join(lines)
