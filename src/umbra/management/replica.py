"""Réplica del diseño actual: umbra recorre la app con el navegador y deja cada vista en
`design/actual/` (captura + índice) y, con una herramienta de diseño conectada, en tableros
`Actual · <Vista>`; además extrae el sistema visual del código. La persona lo aprueba."""

import os
import re
from pathlib import Path

from umbra.actions import commands, git
from umbra.management import design_systems
from umbra.management import onboarding as ob
from umbra.unified import project as proj
from umbra.unified.events import add_event

FOLDER = "design"
INDEX = "design/actual/indice.md"
INVENTORY = "specs/000-linea-base/vistas.md"


class ReplicaError(Exception):
    pass


def app_repo(root: Path, config: dict) -> tuple[Path, dict]:
    """Dónde vive la app (y su `design/`): el repo; en un espacio de trabajo, el de
    `[workspace] app` o el último de la lista (el front)."""
    members = proj.members(root, config)
    if not members:
        return root, config
    name = config.get("workspace", {}).get("app") or list(members)[-1]
    if name not in members:
        raise ReplicaError(f"[workspace] app = «{name}» no es un repo del espacio")
    return members[name], proj.repo_config(config, members[name])


def _start(root: Path, udir: Path, config: dict, app: Path) -> list[dict]:
    """Levanta la app; en un espacio, antes los repos que la preceden (el back), y cada uno
    recibe las URLs de los anteriores como `UMBRA_URL_<REPO>`."""
    members = proj.members(root, config) or {app.name: app}
    devs, env = [], {}
    try:
        for name, path in members.items():
            cfg = config if path == root else proj.repo_config(config, path)
            if dev := commands.start_background(cfg, "dev", path, udir, env=env):
                devs.append(dev)
                env[f"UMBRA_URL_{re.sub(r'[^A-Z0-9]', '_', name.upper())}"] = dev["url"]
            if path == app:
                return devs
    except commands.NotReady as e:
        for dev in devs:
            commands.stop_background(dev)
        raise ReplicaError(f"la app no arrancó: {e}") from e
    return devs


def replicate(conn, root: Path, udir: Path, config: dict, origin: str = "cli") -> dict:
    """Levanta la app, corre el replicador y devuelve {summary, images, root}. Lo que toque
    fuera de `design/` se restaura. En un espacio, trabaja en el repo de la app."""
    home = root
    root, app_config = app_repo(home, config)
    if not commands.background(app_config, "dev"):
        where = f"{root.name}/" if root != home else ""
        raise ReplicaError("hace falta el comando `dev` (con `background = true` y `url`) en "
                           f"{where}.umbra/project.toml para ver la app")
    design = design_systems.resolved(app_config)
    feedback = []
    inventory = root / INVENTORY if (root / INVENTORY).is_file() else home / INVENTORY
    feedback.append("# Inventario de vistas\n\n" + (
        inventory.read_text(encoding="utf-8", errors="replace") if inventory.is_file() else
        "(no hay inventario: descubre las vistas en el código del router)"))
    if login := design.get("replica"):
        password = os.environ.get(login.get("clave_env", ""), "")
        feedback.append(f"Para entrar: usuario `{login.get('usuario', '')}`, contraseña "
                        f"`{password}` (usuario de prueba local).")
    for raw in design.get("guides") or []:
        path = Path(raw).expanduser()
        path = path if path.is_absolute() else root / path
        if path.is_file():
            feedback.append(path.read_text(encoding="utf-8", errors="replace")[:ob.NOTE_CHARS])
    devs = _start(home, udir, config, root)
    before = ob._dirty(root)
    try:
        result, invocation = ob.agent(
            root, udir, "replicator", "Replicar el diseño actual",
            "Recorre la app y replica cada vista del inventario.", feedback,
            app_url=devs[-1]["url"], mcp=design.get("mcp") or {})
    finally:
        for dev in reversed(devs):
            commands.stop_background(dev)
    others = sorted(p for p in ob._dirty(root) - before if not p.startswith(f"{FOLDER}/"))
    if others:
        for p in others:
            if git.ok(root, "ls-files", "--error-unmatch", p):
                git.ok(root, "checkout", "--", p)
            else:
                (root / p).unlink(missing_ok=True)
        raise ReplicaError(f"el replicador tocó archivos que no debía: {', '.join(others)}")
    if not result.ok:
        raise ReplicaError(result.error or "el replicador falló")
    ob.record_usage(conn, result, invocation)
    images = [p for p in result.output.images if (root / p).is_file()]
    add_event(conn, None, "design.replicated", origin, views=len(images))
    return {"summary": result.output.summary, "images": images, "root": root}


def pending(root: Path) -> list[str]:
    return sorted(p for p in ob._dirty(root) if p.startswith(f"{FOLDER}/"))


def accept(conn, root: Path, origin: str = "cli") -> str:
    files = pending(root)
    if not files:
        raise ReplicaError("no hay ninguna réplica pendiente")
    git.run(root, "add", "--", *files)
    git.run(root, "commit", "--no-verify", "-q", "-m", "umbra: réplica del diseño actual",
            "--", *files)
    sha = git.head(root)
    add_event(conn, None, "design.replica_approved", origin, sha=sha, files=len(files))
    return sha


def discard(conn, root: Path, origin: str = "cli") -> None:
    for p in pending(root):
        if git.ok(root, "ls-files", "--error-unmatch", p):
            git.ok(root, "checkout", "--", p)
        else:
            (root / p).unlink(missing_ok=True)
    add_event(conn, None, "design.replica_discarded", origin)

