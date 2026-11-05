"""Comandos de ejecución: run, log, evidence, approve, reject, exec y el worker interno.

La lógica vive en umbra.service (compartida con `umbra watch`); aquí solo se presenta.
"""

import time
from pathlib import Path

import typer
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from umbra import service
from umbra.actions import commands, git
from umbra.cli import context
from umbra.routines import engine as eng
from umbra.routines import worker
from umbra.unified import clock
from umbra.unified.events import add_event, events_for
from umbra.unified.explain import narrate, spend_text
from umbra.unified.output import console, emit, fail
from umbra.unified.store import _unpriced as store_unpriced

JsonOpt = typer.Option(False, "--json", help="Salida en JSON")


def _op(fn, *args, as_json: bool = False, **kwargs):
    """Ejecuta una operación del servicio y convierte sus errores en salida de la CLI."""
    try:
        return fn(*args, **kwargs)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)


def run(
    numbers: list[int] = typer.Argument(..., help="Números de tarea"),
    routine: str | None = typer.Option(None, "--routine", "-r",
                                       help="Rutina (por defecto [project] default_routine)"),
    foreground: bool = typer.Option(False, "--foreground", help="Ejecutar en esta terminal"),
    new: bool = typer.Option(False, "--new",
                             help="Empezar de cero aunque haya una ejecución detenida"),
    trust_repo_config: bool = typer.Option(
        False, "--trust-repo-config",
        help="Confiar en .claude/settings.json y .mcp.json del repo (Claude Code -p los carga)"),
    as_json: bool = JsonOpt,
) -> None:
    """Encola tareas y las ejecuta en segundo plano."""
    ctx = context.load(as_json)
    results = _op(service.run, ctx, numbers, routine=routine, new=new,
                  trust_repo_config=trust_repo_config, foreground=foreground, as_json=as_json)

    def render(c):
        for r in results:
            verb = "encolada" if r["created"] else f"ya activa ({r['status']})"
            c.print(f"tarea {r['task']}: ejecución {r['run_id'][:8]} {verb}")
        if not foreground:
            c.print("sigue el progreso con `umbra watch` o `umbra log <n> -f`")

    emit(results, as_json, render)


def log(
    number: int,
    stage: str | None = typer.Option(None, "--stage"),
    follow: bool = typer.Option(False, "--follow", "-f"),
    raw: bool = typer.Option(False, "--raw", help="Registro técnico completo (sin narrar)"),
    as_json: bool = JsonOpt,
) -> None:
    """Qué ha pasado en la última ejecución de una tarea, contado en frases."""
    ctx = context.load(as_json)
    run_row = context.latest_run(ctx, number, as_json)
    seen, last_day = 0, None
    while True:
        events = [e for e in events_for(ctx.conn, run_row["id"], seen)
                  if not stage or e["payload"].get("stage") in (stage, None)]
        if events:
            seen = max(seen, *(e["seq"] for e in events))
        if as_json:
            emit(events, True, lambda c: None)
        else:
            for e in events:
                if raw:
                    extra = " ".join(f"{k}={v}" for k, v in e["payload"].items()
                                     if k != "trace" and v is not None)
                    line = f"{e['type']} {extra}"
                elif (line := narrate(e)) is None:
                    continue
                if (day := clock.day_key(e["created_at"])) != last_day:  # hora local; el día
                    last_day = day                                        # cuando cambia
                    console.print(f"[dim]── {clock.day_label(e['created_at'])} ──[/dim]")
                stamp = clock.hhmmss(e["created_at"]) if raw else clock.hhmm(e["created_at"])
                console.print(f"[dim]{stamp}[/dim] ", end="")
                console.print(line, markup=False, highlight=False)
        status = ctx.conn.execute("SELECT status FROM run WHERE id = ?",
                                  (run_row["id"],)).fetchone()["status"]
        if not follow or status in (*eng.TERMINAL, "WAITING_APPROVAL"):
            return
        time.sleep(1)


def evidence(number: int, as_json: bool = JsonOpt,
             raw: bool = typer.Option(False, "--raw", help="Detalle técnico: intentos, "
                                      "comandos, SHAs, logs y hallazgos completos")) -> None:
    """Qué se hizo y cómo se comprobó (con --raw, la evidencia técnica completa)."""
    ctx = context.load(as_json)
    data = _op(service.evidence, ctx, number, as_json=as_json)
    emit(data, as_json, lambda c: (render_evidence if raw else render_report)(c, data))


def _mark(ok: bool | None) -> str:
    return {True: "✓", False: "✗", None: "·"}[ok]


def _line(c, text: str, indent: int) -> None:
    """Una línea que, si no cabe, sigue con la misma sangría."""
    c.print(Padding(Text(text), (0, 0, 0, indent)))


def render_report(c, data: dict) -> None:
    """La evidencia contada para quien aprueba; el detalle técnico queda en --raw / tecla t."""
    rep = data["report"]
    c.print(Text(f"Tarea {rep['number']} · {rep['title']}", style="bold"))
    c.print(rep["state"], markup=False)
    c.print()
    c.print(Text("QUÉ SE HIZO", style="bold"))
    c.print(Padding(Text(rep["what"] or "Todavía no hay trabajo terminado."), (0, 0, 0, 2)))
    if rep["what"]:
        c.print(Text(f"  (lo cuenta {rep['what_by']})", style="dim"))
    c.print()
    c.print(Text("CÓMO SE COMPROBÓ", style="bold"))
    lines: list[tuple[bool | None, str]] = []
    t = rep["tests"]
    if not t:
        lines.append((None, "Pruebas: todavía no se ejecutaron"))
    else:
        n = t["counts"]
        skipped = n.get("skipped", 0)
        extra = f" ({skipped} omitida{'s' if skipped > 1 else ''})" if skipped else ""
        if t["ok"]:
            done = f"{n['passed']} pasan" if n.get("passed") else "pasan"
            where = "sobre la versión final" if t["current"] else "sobre una versión anterior"
            lines.append((t["current"], f"Pruebas: {done} {where}{extra}"))
        else:
            failed = n.get("failed", 0) + n.get("error", 0)
            lines.append((False, f"Pruebas: fallan{f' {failed}' if failed else ''}{extra}"))
    crit = rep["criteria"]
    total = len(crit["items"])
    if not crit["checked"]:
        lines.append((None, f"Criterios de aceptación ({total}): todavía sin verificar"))
    elif crit["unmet"]:
        lines.append((False, f"Criterios de aceptación: {len(crit['unmet'])} de {total} sin "
                             "cumplir"))
    else:
        lines.append((True, f"Criterios de aceptación: {total} de {total} cumplidos"))
    for mark, text in lines:
        _line(c, f"{_mark(mark)} {text}", 2)
    for i, item in enumerate(crit["items"], 1):
        _line(c, f"{i}. {item}", 6)
    for item in crit["unmet"]:
        _line(c, f"✗ {item}", 6)
    if rep.get("screenshots"):
        n = rep["screenshots"]
        _line(c, f"{_mark(True)} Visto en el navegador: {n} captura{'s' if n > 1 else ''} "
                 f"(umbra evidence {rep['number']} --raw)", 2)
    obs, rounds = rep["observations"], rep["review_rounds"]
    if rounds:
        pending = [o for o in obs if not o["resolved"]]
        one = len(obs) == 1
        if not obs:
            state = "sin observaciones importantes"
        elif pending:
            state = f"{len(obs)} observaciones importantes, {len(pending)} sin resolver"
        else:
            state = ("1 observación importante, corregida" if one
                     else f"{len(obs)} observaciones importantes, todas corregidas")
        _line(c, f"{_mark(not pending)} Revisión independiente: {rounds} "
                 f"{'ronda' if rounds == 1 else 'rondas'} · {state}", 2)
        for o in obs:
            _line(c, f"· {o['text']} → {'corregida' if o['resolved'] else 'pendiente'}", 6)
    if rep["scan"]:
        ok = rep["scan"] == "done"
        _line(c, f"{_mark(ok)} Seguridad: " + ("sin secretos ni problemas detectados" if ok
                                              else "hay problemas (ver detalle técnico)"), 2)
    c.print()
    ch = rep["changes"]
    added = sum(v[1] for v in ch.values())
    removed = sum(v[2] for v in ch.values())
    c.print(Text("QUÉ CAMBIÓ   ", style="bold") + Text(
        " · ".join(f"{k} {v[0]}" for k, v in ch.items()) + f"   (+{added} −{removed} líneas)"))
    cost = spend_text(rep["cost"], rep["unpriced_tokens"])
    c.print(Text("COSTO        ", style="bold") + Text(
        f"{cost} · {rep['minutes']} min · {rep['attempts']} intentos"))
    if rep["pr"]:
        c.print(Text(f"PR: {rep['pr']}"))


def render_evidence(c, data: dict) -> None:
    r = data["run"]
    c.print(f"ejecución {r['id'][:8]} · {r['status']} · rama {r['branch']}")
    c.print(f"base {r['base_sha'][:10] if r['base_sha'] else '-'} → "
            f"head {r['head_sha'][:10] if r['head_sha'] else '-'} · costo "
            f"{spend_text(data['cost'], data['unpriced_tokens'])}")
    t = Table("etapa", "#", "perfil", "estado", "costo")
    for a in data["attempts"]:
        t.add_row(a["stage"], str(a["attempt_no"]), a["profile"] or "-", a["status"],
                  (spend_text(a["cost"], store_unpriced(a)) if a["cost"] else "-"))
    c.print(t)
    for a in data["artifacts"]:
        if a["kind"] == "screenshot":
            c.print(f"  captura sobre {(a['tested_sha'] or '-')[:10]}: {a['path']}", markup=False)
            continue
        c.print(f"  {a['command']} → exit {a['exit_code']} sobre "
                f"{(a['tested_sha'] or '-')[:10]} ({a['path']})", markup=False)
    for f in data["findings"]:
        where = f" ({f['file']}:{f['line']})" if f["file"] else ""
        c.print(f"  [{f['severity']}] {f['message']}{where}", markup=False)
    for a in data["approvals"]:
        c.print(f"  {a['decision']} por {a['actor']} sobre {a['head_sha'][:10]}")
    if data["diff_stat"]:
        c.print(data["diff_stat"], markup=False)
    if data["pr"]:
        c.print(f"PR: {data['pr']['url']}")


def approve(number: int | None = typer.Argument(None),
            all_: bool = typer.Option(False, "--all",
                                      help="Integra todas las que esperan"),
            spec: str | None = typer.Option(None, "--spec",
                                            help="Integra la spec completa (su carpeta)")) -> None:
    """Revisa y aprueba una ejecución en espera; fusiona el PR. Requiere terminal interactiva."""
    if not service.interactive():
        fail("umbra approve requiere una terminal interactiva", code=3)
    ctx = context.load()
    if spec:
        spec_dir = _op(service.spec_ref, ctx, spec)
        pr = service.spec_pr(ctx, spec_dir)
        if not pr or pr["state"] != "waiting":
            _op(service.approve_spec, ctx, spec_dir)  # explica por qué no se puede
        tasks = ctx.conn.execute("SELECT number, title FROM task WHERE spec_dir = ?"
                                 " ORDER BY number", (spec_dir,)).fetchall()
        console.print(f"Spec {spec_dir}: {len(tasks)} historias integradas en su rama "
                      f"({pr['url']})", highlight=False)
        for t in tasks:
            console.print(f"  #{t['number']} {t['title']}", highlight=False, markup=False)
        if not typer.confirm(f"¿Integrar la spec completa (PR #{pr['number']}) en la rama base?"):
            raise typer.Exit(1)
        result = _op(service.approve_spec, ctx, spec_dir)
        console.print(f"[green]spec integrada[/green]: merge {result['merge_sha'][:10]} "
                      f"({result['pr']})")
        if result.get("pulled"):
            console.print("tu copia de la rama base quedó al día (git pull --ff-only)")
        return
    if all_:
        waiting = service.waiting_tasks(ctx)
        if not waiting:
            fail("ninguna tarea espera aprobación")
        if not typer.confirm(f"¿Integrar las {len(waiting)} que esperan: "
                             f"{', '.join(map(str, waiting))}?"):
            raise typer.Exit(1)
        result = service.approve_all(ctx)
        for n in result["approved"]:
            console.print(f"[green]integrada[/green] la tarea {n}")
        if result["failed"]:
            fail(f"la tarea {result['failed'][0]} no se integró: {result['failed'][1]}")
        return
    if number is None:
        fail("indica la tarea o usa --all")
    run_row = context.latest_run(ctx, number)
    if run_row["status"] != "WAITING_APPROVAL":
        fail(f"la ejecución está en {run_row['status']}, no en WAITING_APPROVAL")
    render_report(console, _op(service.evidence, ctx, number))
    console.print(f"[dim]Detalle técnico: umbra evidence {number} --raw[/dim]")
    if not typer.confirm(f"¿Aprobar e integrar {run_row['head_sha'][:10]} en la rama base?"):
        raise typer.Exit(1)
    result = _op(service.approve, ctx, number)
    console.print(f"[green]integrado[/green]: merge {result['merge_sha'][:10]} ({result['pr']})")
    if result.get("pulled"):
        console.print("tu copia de la rama base quedó al día (git pull --ff-only)")
    if result.get("next"):
        console.print(f"piloto automático: la tarea {result['next']} arrancó sola "
                      f"(umbra explain {result['next']})", highlight=False)


def reject(number: int, reason: str = typer.Option("rechazado", "--reason", "-m")) -> None:
    """Rechaza una ejecución: cierra el PR y la cancela."""
    if not service.interactive():
        fail("umbra reject requiere una terminal interactiva", code=3)
    ctx = context.load()
    _op(service.reject, ctx, number, reason)
    console.print("ejecución cancelada y PR cerrado")


def pause(number: int, as_json: bool = JsonOpt) -> None:
    """Pausa una ejecución en el siguiente punto seguro."""
    ctx = context.load(as_json)
    run_id = _op(service.pause, ctx, number, as_json=as_json)
    emit({"run_id": run_id, "status": "PAUSED"}, as_json,
         lambda c: c.print("pausa solicitada: se detiene al terminar la etapa en curso"))


def resume(number: int, foreground: bool = typer.Option(False, "--foreground"),
           as_json: bool = JsonOpt) -> None:
    """Retoma una ejecución pausada."""
    ctx = context.load(as_json)
    run_id = _op(service.resume, ctx, number, foreground=foreground, as_json=as_json)
    emit({"run_id": run_id, "status": "QUEUED"}, as_json, lambda c: c.print("retomada"))


def cancel(number: int, as_json: bool = JsonOpt) -> None:
    """Cancela una ejecución: cierra su PR y limpia el workspace."""
    ctx = context.load(as_json)
    previous = _op(service.cancel, ctx, number, as_json=as_json)
    msg = ("cancelación solicitada: el worker se detiene en el siguiente punto seguro"
           if previous == "RUNNING" else "ejecución cancelada")
    emit({"status": "CANCELLED"}, as_json, lambda c: c.print(msg))


def retry(
    number: int,
    from_: str | None = typer.Option(None, "--from", help="Etapa desde la que reintentar"),
    foreground: bool = typer.Option(False, "--foreground"),
    as_json: bool = JsonOpt,
) -> None:
    """Reintenta una ejecución bloqueada, fallida o con SHA vencido, con ciclos nuevos."""
    ctx = context.load(as_json)
    stage = _op(service.retry, ctx, number, from_, foreground=foreground, as_json=as_json)
    emit({"status": "QUEUED", "stage": stage}, as_json,
         lambda c: c.print(f"reintento encolado desde {stage}"))


def night(spec: str | None = typer.Option(None, "--spec", help="Solo esta spec (carpeta)"),
          as_json: bool = JsonOpt) -> None:
    """Deja todo encolado: acepta los borradores y arranca lo que quepa; el resto sigue solo."""
    ctx = context.load(as_json)
    r = _op(service.night, ctx, spec, as_json=as_json)

    def show(c):
        c.print(f"aceptadas: {', '.join(map(str, r['accepted'])) or 'ninguna nueva'}",
                highlight=False)
        c.print(f"en marcha: {', '.join(map(str, r['started'])) or 'ninguna'}"
                f" (hasta {r['parallel']} a la vez)", highlight=False)
        if r["waiting"]:
            c.print(f"esperan su turno: {', '.join(map(str, r['waiting']))}", highlight=False)
        if not r["autopilot"]:
            c.print("[yellow]aviso[/yellow]: [autopilot] enabled = false; las que esperan no "
                    "arrancarán solas")
        c.print("Mañana: umbra watch (o umbra status) muestra qué espera tu aprobación.",
                highlight=False)

    emit(r, as_json, show)


def bridge_cmd(stop: bool = typer.Option(False, "--stop", help="Para el puente en marcha"),
               root: Path | None = typer.Option(None, "--root", hidden=True)) -> None:
    """Atiende el teléfono (botones, respuestas y conversación) para todos tus repos."""
    from umbra.routines import bridge
    from umbra.unified import project as proj
    start = root or Path.cwd()
    try:
        repo, _ = proj.umbra_dir(start)
    except (proj.NotARepo, proj.NotInitialized) as e:
        fail(str(e), code=2)
    if stop:
        console.print("puente detenido" if bridge.stop() else "no había ningún puente")
        return
    try:
        n = bridge.serve(repo)
    except service.OpError as e:
        fail(str(e), code=e.code)
    console.print(f"puente cerrado tras {n} decisiones")


def open_(number: int, as_json: bool = JsonOpt) -> None:
    """Abre el espacio de trabajo de una tarea detenida en tu editor para arreglarla a mano."""
    ctx = context.load(as_json)
    result = _op(service.open_workspace, ctx, number, as_json=as_json)
    emit(result, as_json, lambda c: c.print(
        f"abierto con {result['editor']}: {result['worktree']}\n"
        f'Cuando termines: umbra done {number} -m "qué arreglaste"', highlight=False,
        markup=False))


def done(number: int,
         message: str = typer.Option(..., "-m", "--message", help="Qué arreglaste"),
         foreground: bool = typer.Option(False, "--foreground"),
         as_json: bool = JsonOpt) -> None:
    """Confirma tu arreglo, corre los tests como evidencia y umbra retoma desde Revisar."""
    ctx = context.load(as_json)
    result = _op(service.resume_human, ctx, number, message, foreground, as_json=as_json)
    emit(result, as_json, lambda c: c.print(
        f"tarea {number}: tu arreglo pasa los tests; sigue desde {result['resumed_from']}"))


def exec_(name: str, as_json: bool = JsonOpt) -> None:
    """Ejecuta un comando registrado en .umbra/project.toml y guarda su resultado."""
    ctx = context.load(as_json)
    try:
        result = commands.run_registered(ctx.conn, ctx.config, name, ctx.root, ctx.udir,
                                         tested_sha=git.head_or_none(ctx.root))
    except commands.UnknownCommand as e:
        fail(str(e), code=2, as_json=as_json)
    add_event(ctx.conn, None, "command.executed", "cli", name=name,
              exit_code=result["exit_code"])
    emit({k: v for k, v in result.items() if k != "output"} | {"output": result["output"][-4000:]},
         as_json, lambda c: c.print(result["output"]))
    raise typer.Exit(0 if result["exit_code"] == 0 else 1)


def worker_cmd(root: Path = typer.Option(..., "--root")) -> None:
    """(interno) Ejecuta las ejecuciones pendientes del repo."""
    worker.work(root)
