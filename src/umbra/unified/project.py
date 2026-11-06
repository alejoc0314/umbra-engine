"""Raíz del repo (o del espacio de trabajo), detección de stack y configuración .umbra/."""

import json
import re
import subprocess
import tomllib
from pathlib import Path

UMBRA_DIR = ".umbra"
PROJECT_FILE = "project.toml"
LOCAL_FILE = "local.toml"  # tu configuración personal o secreta: nunca se versiona
GITIGNORE_LINES = (".umbra/umbra.db*", ".umbra/artifacts/", ".umbra/worktrees/",
                   ".umbra/local.toml")

STACKS = {
    "python": {"test": "pytest -q", "lint": "ruff check ."},
    "node": {"test": "npm test", "lint": "npm run lint"},
    "php": {"test": "vendor/bin/phpunit", "lint": "vendor/bin/pint --test"},
    "generic": {},
}


class NotARepo(Exception):
    pass


class NotInitialized(Exception):
    pass


class InvalidProject(NotInitialized):
    """project.toml existe pero no se puede leer; se reporta igual que 'no inicializado'."""


def _git_root(start: Path) -> Path | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=start, capture_output=True, text=True,
    )
    return Path(proc.stdout.strip()) if proc.returncode == 0 else None


def find_root(start: Path) -> Path:
    """El espacio de trabajo si `start` está en él (en la carpeta padre o dentro de uno de sus
    repos); si no, el repo git."""
    if (ws := find_workspace(start)) is not None:
        return ws
    root = _git_root(start)
    if root is None:
        raise NotARepo(f"{start} no es un repositorio git")
    return root


# ---------- espacios de trabajo (spec 032): una carpeta padre con varios repos ----------
def repo_names(config: dict) -> list[str]:
    return list(config.get("workspace", {}).get("repos") or [])


def members(root: Path, config: dict) -> dict[str, Path]:
    """Repos del espacio, en su orden de integración; vacío en un proyecto de un repo."""
    return {name: root / name for name in repo_names(config)}


def find_workspace(start: Path) -> Path | None:
    start = Path(start).resolve()
    for cand in (start, *start.parents):
        path = cand / UMBRA_DIR / PROJECT_FILE
        if not path.is_file():
            continue
        try:
            repos = repo_names(_read_toml(path))
        except InvalidProject:
            continue
        inside = [cand / UMBRA_DIR, *(cand / r for r in repos)]
        if repos and (cand == start or any(start.is_relative_to(p) for p in inside)):
            return cand
    return None


def repo_config(ws_config: dict, member: Path) -> dict:
    """La configuración de un repo del espacio: la suya (stack, comandos, rama base, política)
    con la compartida del espacio encima (avisos, paralelo, piloto automático, editor)."""
    if not (member / UMBRA_DIR / PROJECT_FILE).is_file():
        raise NotInitialized(f"el repo {member.name} del espacio no está en {member.as_posix()} "
                             "o no está inicializado: revisa [workspace] repos")
    return merge(load_project(member), {k: v for k, v in ws_config.items() if k != "workspace"})


def child_repos(folder: Path) -> list[str]:
    """Repos git hijos directos, en el orden del `.code-workspace` si lo hay; si no, alfabético."""
    names = sorted(d.name for d in folder.iterdir() if d.is_dir() and (d / ".git").exists())
    order = []
    for ws_file in sorted(folder.glob("*.code-workspace")):
        text = re.sub(r"^\s*//.*$", "", ws_file.read_text(encoding="utf-8-sig"), flags=re.M)
        try:  # JSON con comentarios y comas finales, como lo guarda VS Code
            data = json.loads(re.sub(r",(\s*[\]}])", r"\1", text))
        except ValueError:
            continue
        order += [Path(f.get("path", "")).name for f in data.get("folders", [])
                  if isinstance(f, dict)]
    return [n for n in dict.fromkeys(order) if n in names] + [n for n in names if n not in order]


def _active_runs(member: Path) -> int:
    if not (member / UMBRA_DIR / "umbra.db").is_file():
        return 0
    from umbra.unified.store import ACTIVE_RUN_STATES, open_store
    conn = open_store(member / UMBRA_DIR)
    try:
        marks = ",".join("?" * len(ACTIVE_RUN_STATES))
        return conn.execute(f"SELECT COUNT(*) FROM run WHERE status IN ({marks})",
                            ACTIVE_RUN_STATES).fetchone()[0]
    finally:
        conn.close()


def init_workspace(root: Path, repos: list[str] | None = None) -> dict:
    """Crea (o completa) el espacio: inicializa cada repo y escribe `[workspace] repos`."""
    project_file = root / UMBRA_DIR / PROJECT_FILE
    created = not project_file.exists()
    repos = repos if created else repo_names(_read_toml(project_file))
    if created:
        busy = [r for r in repos if _active_runs(root / r)]
        if busy:
            raise NotInitialized(f"{', '.join(busy)} tiene tareas en marcha con su propio umbra: "
                                 "termínalas o cancélalas antes de unirlo al espacio")
    stacks = {r: _init_repo(root / r, register=False)["stack"] for r in repos}
    if created:
        (root / UMBRA_DIR).mkdir(parents=True, exist_ok=True)
        project_file.write_text(_render_workspace(repos), encoding="utf-8", newline="\n")
    from umbra.management import projects
    projects.register(root, "espacio", hide=[root / r for r in repos])
    return {"root": root.as_posix(), "created": created, "stack": "espacio", "workspace": True,
            "repos": [{"name": r, "stack": stacks[r]} for r in repos], "commands": {}}


def detect_stack(root: Path) -> tuple[str, dict[str, str]]:
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        stack = "python"
    elif (root / "package.json").exists():
        stack = "node"
    elif (root / "composer.json").exists():
        stack = "php"
    else:
        stack = "generic"
    commands = dict(STACKS[stack])
    if stack == "php" and (root / "artisan").exists():
        commands["test"] = "php artisan test"
        commands["dev"] = {"run": "php artisan serve --port=8765", "background": True,
                           "url": "http://127.0.0.1:8765"}
    return stack, commands


def current_branch(root: Path) -> str:
    """Rama actual (funciona aun sin commits); 'main' si HEAD está desacoplado."""
    proc = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], cwd=root,
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "main"


def _toml_str(text: str) -> str:
    """Cadena TOML: con comillas dobles dentro (rutas entre comillas) se usa la literal."""
    return f"'{text}'" if '"' in text and "'" not in text else json.dumps(text)


def _render_toml(stack: str, commands: dict, base_branch: str = "main",
                 default_routine: str | None = None) -> str:
    lines = ["[project]", f'stack = "{stack}"', f'base_branch = "{base_branch}"']
    if default_routine:
        lines.append(f'default_routine = "{default_routine}"')
    lines += ["", "[commands]"]
    if commands:
        for name, cmd in commands.items():
            if isinstance(cmd, dict):  # servidor de desarrollo: umbra lo levanta en VERIFY
                lines.append(f'{name} = {{ run = {_toml_str(cmd["run"])}, background = true, '
                             f'url = {_toml_str(cmd["url"])} }}')
            else:
                lines.append(f'{name} = {{ run = {_toml_str(cmd)}, safe = true }}')
    else:
        lines.append('# test = { run = "<tu comando de tests>", safe = true }')
    lines += ["", "[policy]", 'protected_paths = [".umbra/", ".github/workflows/"]', "",
              *_shared_lines()]
    return "\n".join(lines)


def _render_workspace(repos: list[str]) -> str:
    return "\n".join([
        "[workspace]", f"repos = {json.dumps(repos, ensure_ascii=False)}  # orden de integración:"
        " primero lo que los otros necesitan (el back)",
        '# app = "<repo>"  # tareas entre repos: cuya URL abre la verificación en el navegador',
        "# Stack, comandos, rama base y política van en el .umbra/project.toml de cada repo.", "",
        *_shared_lines()])


def _shared_lines() -> list[str]:
    """Lo que en un espacio es común a todos sus repos (y en un repo, suyo)."""
    return ["[report]", "summary = true  # explicación conceptual al terminar cada tarea", "",
            "[notify]", "desktop = true  # aviso del sistema cuando una tarea te necesita",
            "bell = true     # campana en watch",
            "# Telegram ([notify.telegram] token_env y chat_id) y tu editor van en",
            "# .umbra/local.toml, que git ignora: configuración tuya, no del repo.", "",
            "[blocks]", "parallel = 2  # tareas a la vez (cada una en su worktree)", "",
            "[autopilot]", "enabled = true  # al integrar, arranca la siguiente tarea aceptada",
            "", "[editor]",
            'command = "code"  # umbra open / tecla o en watch (si no, $VISUAL o $EDITOR)', ""]


def _ensure_gitignore(root: Path) -> None:
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if missing:
        prefix = "\n" if existing and existing[-1].strip() else ""
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(prefix + "# umbra\n" + "\n".join(missing) + "\n")


def init_project(start: Path, stack: str | None = None, commands: dict | None = None,
                 default_routine: str | None = None) -> dict:
    if (ws := find_workspace(start)) is not None:
        return init_workspace(ws)
    root = _git_root(start)
    if root is None:
        repos = child_repos(Path(start))
        if len(repos) >= 2:
            return init_workspace(Path(start).resolve(), repos)
        hint = f"; para un solo repo, ejecuta `umbra init` dentro de {repos[0]}" if repos else ""
        raise NotARepo(f"{start} no es un repositorio git ni una carpeta con dos o más repos "
                       f"(un espacio de trabajo){hint}")
    return _init_repo(root, stack, commands, default_routine)


def _init_repo(root: Path, stack: str | None = None, commands: dict | None = None,
               default_routine: str | None = None, register: bool = True) -> dict:
    udir = root / UMBRA_DIR
    project_file = udir / PROJECT_FILE
    created = not project_file.exists()
    if created:
        detected, detected_commands = detect_stack(root)
        stack, commands = stack or detected, commands if commands is not None \
            else detected_commands
        for sub in ("routines", "profiles"):
            (udir / sub).mkdir(parents=True, exist_ok=True)
        project_file.write_text(_render_toml(stack, commands, current_branch(root),
                                             default_routine),
                                encoding="utf-8", newline="\n")
    _ensure_gitignore(root)
    config = load_project(root)
    if register:
        from umbra.management import projects
        projects.register(root, config["project"].get("stack", "generic"))
    return {
        "root": root.as_posix(),
        "created": created,
        "stack": config["project"]["stack"],
        "commands": {k: v["run"] for k, v in config.get("commands", {}).items()},
    }


def _read_toml(path: Path) -> dict:
    # utf-8-sig: el Bloc de notas y PowerShell 5.1 guardan con BOM
    try:
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as e:
        raise InvalidProject(f"{path} no es TOML válido: {e}") from e


def merge(base: dict, extra: dict) -> dict:
    """`extra` pisa a `base` clave a clave; las tablas se combinan en vez de reemplazarse."""
    out = dict(base)
    for k, v in extra.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_project(root: Path) -> dict:
    """`project.toml` (versionado), con `~/.umbra/local.toml` (tuyo, para todos tus repos) y
    `.umbra/local.toml` (tuyo, de este repo) encima: ahí van Telegram, tu editor o cualquier
    ajuste que no deba viajar con el repo."""
    from umbra.unified.config import umbra_home
    path = root / UMBRA_DIR / PROJECT_FILE
    if not path.exists():
        raise NotInitialized("proyecto no inicializado: ejecuta `umbra init`")
    config = _read_toml(path)
    for local in (umbra_home() / LOCAL_FILE, root / UMBRA_DIR / LOCAL_FILE):
        if local.exists():
            config = merge(config, _read_toml(local))
    return config


def umbra_dir(start: Path) -> tuple[Path, Path]:
    """Devuelve (raíz del repo, .umbra/) de un proyecto inicializado."""
    root = find_root(start)
    load_project(root)
    return root, root / UMBRA_DIR
