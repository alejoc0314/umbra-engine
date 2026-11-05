"""Comandos `umbra agent` y `umbra profile`: integrar agentes y gestionar perfiles."""

import tomllib
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.table import Table

from umbra.adapters import UnknownAgent
from umbra.cli import context
from umbra.unified import agent_check, agents
from umbra.unified import config as cfg
from umbra.unified.output import emit, fail

agent_app = typer.Typer(help="Agentes: registrar, listar y verificar.", no_args_is_help=True)
profile_app = typer.Typer(help="Perfiles: cada agente con su forma de trabajar.",
                          no_args_is_help=True)
JsonOpt = typer.Option(False, "--json", help="Salida en JSON")


def _udir_or_none() -> Path | None:
    from umbra.unified import project
    try:
        return project.umbra_dir(Path.cwd())[1]
    except (project.NotARepo, project.NotInitialized):
        return None


def _result_dict(result) -> dict:
    return {"ok": result.ok, "error": result.error, "timed_out": result.timed_out,
            "output": result.output.model_dump() if result.output else None,
            "cost": str(result.cost)}


@agent_app.command("list")
def agent_list(as_json: bool = JsonOpt) -> None:
    """Agentes integrados y registrados, con disponibilidad y verificación."""
    rows = agents.listing(_udir_or_none())

    def render(c):
        t = Table("agente", "tipo", "disponible", "verificado", "ubicación")
        for r in rows:
            t.add_row(r["name"], "integrado" if r["builtin"] else r["adapter"],
                      "sí" if r["available"] else "[red]no[/red]",
                      "sí" if r["verified"] else "[yellow]no[/yellow]", r["path"] or "-")
        c.print(t)

    emit(rows, as_json, render)


@agent_app.command("add")
def agent_add(
    source: Path = typer.Argument(..., exists=True, file_okay=False,
                                  help="Directorio con agent.toml"),
    project: bool = typer.Option(False, "--project", help="Registrar solo en este proyecto"),
    as_json: bool = JsonOpt,
) -> None:
    """Registra un agente a partir de su manifiesto (queda sin verificar)."""
    udir = _udir_or_none()
    if project and udir is None:
        fail("--project requiere un proyecto inicializado", code=2, as_json=as_json)
    try:
        manifest, target = agents.register(source, udir, project)
    except (FileNotFoundError, ValidationError, tomllib.TOMLDecodeError, ValueError) as e:
        fail(f"manifiesto inválido: {e}", code=2, as_json=as_json)
    emit({"name": manifest.name, "path": target.as_posix(), "verified": False}, as_json,
         lambda c: c.print(f"agente {manifest.name} registrado en {target}. Verifícalo con "
                           f"`umbra agent test {manifest.name}`."))


@agent_app.command("test")
def agent_test(name: str, as_json: bool = JsonOpt) -> None:
    """Ejecuta el agente contra una tarea de ejemplo y, si cumple el contrato, lo verifica."""
    udir = _udir_or_none()
    try:
        result = agent_check.run_sample(agent_check.default_profile(name), udir)
    except UnknownAgent as e:
        fail(str(e), code=2, as_json=as_json)
    agent_dir = agents.find(name, udir)
    if result.ok and agent_dir:
        agents.seal(agent_dir)
    data = _result_dict(result) | {"verified": result.ok}
    emit(data, as_json, lambda c: c.print(
        f"[green]{name} verificado[/green]: {result.output.summary}" if result.ok
        else f"[red]{name} no pasó la prueba[/red]: {result.error}"))
    if not result.ok:
        raise typer.Exit(1)


@profile_app.command("list")
def profile_list(as_json: bool = JsonOpt) -> None:
    """Perfiles disponibles y de dónde vienen (paquete, global o proyecto)."""
    udir = _udir_or_none() or Path("__sin_proyecto__")
    rows = []
    for name, path in cfg.list_names(udir, "profiles", ".toml").items():
        p = cfg.load_profile(udir, name)
        origin = ("paquete" if cfg.DEFAULTS in path.parents else
                  "global" if cfg.umbra_home() in path.parents else "proyecto")
        rows.append({"name": name, "agent": p.agent, "roles": p.roles, "model": p.model,
                     "actions": p.actions, "origin": origin})

    def render(c):
        t = Table("perfil", "agente", "roles", "modelo", "acciones", "origen")
        for r in rows:
            t.add_row(r["name"], r["agent"], ",".join(r["roles"]), r["model"] or "-",
                      ",".join(r["actions"]), r["origin"])
        c.print(t)

    emit(rows, as_json, render)


@profile_app.command("show")
def profile_show(name: str, as_json: bool = JsonOpt) -> None:
    """Configuración e instrucciones de un perfil."""
    udir = _udir_or_none() or Path("__sin_proyecto__")
    try:
        p = cfg.load_profile(udir, name)
    except cfg.ConfigError as e:
        fail(str(e), code=2, as_json=as_json)
    ins = p.instructions_path()
    data = p.model_dump(mode="json") | {
        "instructions_text": ins.read_text(encoding="utf-8") if ins and ins.exists() else ""}
    emit(data, as_json, lambda c: (c.print(p.source.read_text(encoding="utf-8")),
                                   c.rule("instrucciones"), c.print(data["instructions_text"])))


@profile_app.command("new")
def profile_new(
    name: str,
    from_: str = typer.Option("builder-tdd", "--from", help="Perfil base"),
    agent: str | None = typer.Option(None, "--agent"),
    model: str | None = typer.Option(None, "--model"),
    as_json: bool = JsonOpt,
) -> None:
    """Crea un perfil del proyecto a partir de otro; su .md define su forma de trabajar."""
    ctx = context.load(as_json)
    base = cfg.load_profile(ctx.udir, from_)
    target = ctx.udir / "profiles" / f"{name}.toml"
    if target.exists():
        fail(f"el perfil {name} ya existe en el proyecto", code=4, as_json=as_json)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'name         = "{name}"', f'agent        = "{agent or base.agent}"',
             f"roles        = {base.roles!r}".replace("'", '"')]
    if model or base.model:
        lines.append(f'model        = "{model or base.model}"')
    lines += [f'instructions = "{name}.md"', f"actions      = {base.actions!r}".replace("'", '"'),
              f'output       = "{base.output}"', "", "[limits]",
              f"max_minutes  = {base.limits.max_minutes}",
              f"max_cost_usd = {base.limits.max_cost_usd}", ""]
    target.write_text("\n".join(lines), encoding="utf-8")
    base_ins = base.instructions_path()
    (target.parent / f"{name}.md").write_text(
        base_ins.read_text(encoding="utf-8") if base_ins else f"Perfil {name}.\n",
        encoding="utf-8")
    emit({"name": name, "path": target.as_posix()}, as_json,
         lambda c: c.print(f"perfil {name} creado en {target}; edita {name}.md para definir "
                           "su forma de trabajar"))


@profile_app.command("test")
def profile_test(name: str, as_json: bool = JsonOpt) -> None:
    """Prueba un perfil contra una tarea de ejemplo (no cambia nada en el proyecto)."""
    udir = _udir_or_none()
    try:
        profile = cfg.load_profile(udir or Path("__sin_proyecto__"), name)
        result = agent_check.run_sample(profile, udir)
    except (cfg.ConfigError, UnknownAgent) as e:
        fail(str(e), code=2, as_json=as_json)
    emit(_result_dict(result), as_json, lambda c: c.print(
        f"[green]{name} ok[/green]: {result.output.summary}" if result.ok
        else f"[red]{name} falló[/red]: {result.error}"))
    if not result.ok:
        raise typer.Exit(1)
