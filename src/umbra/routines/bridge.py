"""Puente con Telegram: un solo proceso atiende el teléfono para todos tus repos con umbra.

Cada botón es un comando de umbra que ya existe (`approve`, `reject`, `retry`, `task allow`,
`task answer`, `finding waive`, `approve --spec`); el puente lo invoca con origen `telegram` y
deja registrado quién lo pidió. Lo que escribes sin más es una conversación con umbra sobre el
proyecto actual (`umbra chat --allow-changes`: responde y actúa, salvo aprobar, rechazar,
push y merge, que son botones). La conversación sabe de todas las carpetas de tu espacio de
trabajo (la carpeta que contiene tus repos, p. ej. C:/apps) y puede pedir al puente cambiar
de proyecto, adoptar una carpeta o crear un proyecto con líneas `UMBRA> …` al final de su
respuesta. Los cambios de BD que propone llegan con botones. Solo atiende al `chat_id`
configurado.
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from umbra import service
from umbra.blocks import telegram
from umbra.blocks.process import background_kwargs
from umbra.management import projects
from umbra.routines import console
from umbra.unified import config as cfg
from umbra.unified import project as proj
from umbra.unified.events import add_event

ORIGIN = "telegram"
TTL_S = 90
LOCK = "bridge.json"  # ~/.umbra: un solo puente lee el bot, para todos los repos
CHUNK = 3900
COMMANDS = [
    ("tareas", "Tareas del proyecto actual, por situación"),
    ("estado", "Qué te necesita ahora"),
    ("explicar", "N · qué pasa con la tarea y qué puedes hacer"),
    ("registro", "N · qué ha pasado, contado en frases"),
    ("evidencia", "N · qué se hizo y cómo se comprobó"),
    ("cambios", "N · archivos tocados y PR"),
    ("agente", "N · qué está haciendo el agente"),
    ("hallazgos", "N · observaciones abiertas"),
    ("tarea", "título | criterio | criterio · crear y aceptar"),
    ("aceptar", "N · aceptar un borrador"),
    ("ejecutar", "N · encolar"),
    ("reintentar", "N [etapa] · reintentar"),
    ("decero", "N · empezar de cero"),
    ("pausar", "N"), ("retomar", "N"), ("cancelar", "N"), ("descartar", "N"),
    ("integrar", "N · aprobar e integrar"),
    ("rechazar", "N motivo"),
    ("noaplica", "N · los hallazgos no aplican"),
    ("despues", "N · dejar los hallazgos para otra tarea"),
    ("noche", "[spec] · aceptar y encolar todo"),
    ("integrar_spec", "nombre · integrar la spec completa"),
    ("spec", "idea · conversar la spec de una funcionalidad"),
    ("spec_seguir", "[NNN] · retomar una conversación de spec"),
    ("spec_ver", "el archivo de la spec o el plan en curso"),
    ("spec_salir", "dejar la conversación de spec (se puede retomar)"),
    ("plan", "ruta/spec.md · proponer tareas desde una spec escrita"),
    ("nuevo_proyecto", "nombre stack [idea] · crear un repo con playbook"),
    ("proyectos", "tus repos y carpetas, y cuál es el actual"),
    ("adoptar", "carpeta · poner umbra en una carpeta que ya existe"),
    ("onboarding", "[de cero] · que umbra estudie a fondo el proyecto actual"),
    ("constitucion", "la constitución del proyecto actual"),
    ("sistema", "[nombre] · el sistema de diseño del proyecto"),
    ("replicar", "réplica del diseño actual de la app en design/"),
    ("enmendar", "texto · proponer un cambio a la constitución"),
    ("usar", "nombre · cambiar de proyecto"),
    ("hacer", "lo que quieres · igual que escribirlo sin más"),
    ("nuevo", "empezar la conversación de cero"),
    ("gusto", "lo que umbra sabe de tu gusto en diseño"),
    ("actualizar", "instalar la última versión de umbra (el puente vuelve solo)"),
    ("ayuda", "esta lista"),
]
HELP = ("Soy umbra en tu teléfono. Escríbeme como a una persona: te cuento qué pasa en el "
        "proyecto actual y hago lo que me pidas (encolar, aceptar, reintentar, crear tareas, "
        "consultar tu MySQL…); puedo pasar a otro proyecto, adoptar una carpeta o crear uno "
        "nuevo si me lo pides; los cambios a la BD te los propongo con botones; "
        "aprobar, rechazar e integrar solo con los botones o /integrar. Cuando una tarea queda "
        "lista te llega su informe y sus capturas. Para responder al agente: «3 tu respuesta» o "
        "responde a su mensaje. Comandos:\n"
        + "\n".join(f"/{c} — {d}" for c, d in COMMANDS))


@dataclass
class State:
    tg: dict
    roots: dict[str, Path]  # nombre del repo → raíz
    current: str
    offset: int = 0
    sessions: dict[str, str] = field(default_factory=dict)  # repo → conversación de Telegram
    talks: dict[str, "console.SpecTalk"] = field(default_factory=dict)  # repo → spec en curso
    onboards: dict = field(default_factory=dict)  # repo → OnboardTalk en curso
    pending_specs: dict[str, str] = field(default_factory=dict)  # repo → idea (falta sistema)
    jobs: dict[str, threading.Thread] = field(default_factory=dict)  # repo → trabajo largo
    workspace: Path | None = None  # la carpeta con tus repos (la del repo que arrancó el puente)


def home(state: State) -> Path:
    return state.workspace or state.roots[state.current].parent


def folders(state: State) -> list[str]:
    """Carpetas del espacio de trabajo que todavía no tienen umbra (se pueden adoptar)."""
    try:
        dirs = sorted(d for d in home(state).iterdir() if d.is_dir())
    except OSError:
        return []
    return [d.name for d in dirs if not d.name.startswith(".")
            and not (d / proj.UMBRA_DIR / proj.PROJECT_FILE).is_file()]


# ---------- repos que atiende ----------
def served(start: Path | None = None) -> dict[str, Path]:
    """Repos con Telegram configurado (el mismo bot): los registrados y los que tienen umbra en
    la carpeta de `start` (entran al índice, para `umbra watch --all`). Nombre → raíz."""
    roots: dict[str, Path] = {}
    entries = projects.load()
    known = {Path(p["root"]) for p in entries}
    if start:
        try:
            near = sorted(d for d in start.parent.iterdir()
                          if (d / proj.UMBRA_DIR / proj.PROJECT_FILE).is_file())
        except OSError:
            near = []
        for root in [start, *near]:
            if root not in known:
                known.add(root)
                entries.append({"root": root.as_posix(), "name": root.name})
                if root != start:
                    try:
                        stack = proj.load_project(root)["project"].get("stack", "generic")
                        projects.register(root, stack)
                    except (proj.NotInitialized, proj.InvalidProject, OSError, KeyError):
                        pass
    for p in entries:
        root = Path(p["root"])
        try:
            if telegram.settings(proj.load_project(root)):
                roots[root.name] = root
        except (proj.NotInitialized, OSError):
            continue
    return roots


def _ctx(state: State, name: str | None = None) -> service.Ctx:
    return service.load(state.roots[name or state.current])


def _split(data: str) -> tuple[str, str | None]:
    """`approve:3@demo` → (`approve:3`, `demo`)."""
    body, _, name = data.partition("@")
    return body, name or None


# ---------- acciones ----------
def act(ctx: service.Ctx, data: str, who: str) -> str:
    """Ejecuta el botón pulsado y devuelve qué pasó, en una frase."""
    kind, _, arg = data.partition(":")
    add_event(ctx.conn, None, "telegram.decided", ORIGIN, action=data, user=who)
    try:
        if kind == "spec":
            r = service.approve_spec(ctx, arg, ORIGIN)
            return f"Spec {arg} integrada: merge {r['merge_sha'][:10]}."
        if kind == "dr":
            from umbra.management import replica
            try:
                if arg == "approve":
                    sha = replica.accept(ctx.conn, ctx.root, ORIGIN)
                    return f"Réplica guardada (commit {sha[:10]})."
                replica.discard(ctx.conn, ctx.root, ORIGIN)
                return "Réplica descartada."
            except replica.ReplicaError as e:
                return f"No se pudo: {e}"
        if kind == "ce":
            from umbra.management import constitution as con
            try:
                if arg == "approve":
                    sha = con.accept(ctx.conn, ctx.root, ORIGIN)
                    return f"Enmienda aprobada (commit {sha[:10]})."
                con.discard(ctx.conn, ctx.root, ORIGIN)
                return "Enmienda descartada: la constitución queda como estaba."
            except con.ConstitutionError as e:
                return f"No se pudo: {e}"
        if kind == "dbok":
            r = service.db_apply(ctx, arg, ORIGIN)
            return f"Cambio {arg} aplicado en la BD: {r['affected']} filas afectadas."
        if kind == "dbno":
            service.db_discard(ctx, arg, ORIGIN)
            return f"Cambio {arg} descartado: la BD no se tocó."
        n = int(arg.split(":", 1)[0])
        if kind == "approve":
            r = service.approve(ctx, n, ORIGIN)
            return f"Tarea {n} integrada ({r['pr']})."
        if kind == "reject":
            service.reject(ctx, n, f"rechazada desde Telegram por {who}", ORIGIN)
            return f"Tarea {n} rechazada: PR cerrado."
        if kind == "diff":
            run = service.latest_run(ctx, n)
            wt = Path(run["worktree"] or "")
            if not run["head_sha"] or not wt.is_dir():
                return f"La tarea {n} no tiene cambios evaluados todavía."
            pr = service.engine(ctx, ORIGIN).pr_info(run["id"]) or {}
            stat = service.diff_stat(ctx, run)
            return f"Cambios de la tarea {n}:\n{stat}" + (f"\n{pr['url']}" if pr else "")
        if kind == "allow":
            paths = service.blocked_paths(ctx, n)
            if not paths:
                return f"La política no frenó ninguna ruta en la tarea {n}."
            service.allow_paths(ctx, n, paths, ORIGIN)
            return f"Autorizado {', '.join(paths)} en la tarea {n}: sigue desde Construir."
        if kind == "retry":
            stage = service.retry(ctx, n, None, origin=ORIGIN)
            return f"Tarea {n}: reintento en cola desde {stage}."
        if kind == "new":
            service.run(ctx, [n], new=True, origin=ORIGIN)
            return f"Tarea {n}: empieza de cero."
        if kind == "waive":
            service.decide_findings(ctx, n, [], "waived", f"desde Telegram por {who}", ORIGIN)
            stage = service.retry(ctx, n, None, origin=ORIGIN)
            return f"Hallazgos marcados como «no aplica»; la tarea {n} sigue desde {stage}."
        if kind == "answer":
            r = service.answer(ctx, n, data.split(":", 2)[2], ORIGIN)
            return f"Respuesta registrada; la tarea {n} sigue desde {r['resumed_from']}."
        if kind == "dok":
            r = service.design_approve(ctx, n, ORIGIN)
            return f"Diseño aprobado; la tarea {n} sigue desde {r['resumed_from']}."
        if kind == "dpick":
            r = service.design_pick(ctx, n, int(data.split(":", 2)[2]), ORIGIN)
            return f"Elegiste «{r['chosen']}»; el diseñador de la tarea {n} sigue en esa línea."
        if kind == "dchg":
            service.design_changes(ctx, n, data.split(":", 2)[2], ORIGIN)
            return f"Cambios pedidos al diseñador de la tarea {n}; te mando el diseño nuevo."
    except (service.OpError, ValueError) as e:
        return f"No se pudo: {e}"
    return f"No entiendo «{data}»."


TEXT_REPLIES = {"agent_questions": "answer", "design_review": "dchg",  # código → acción
                "design_choice": "dchg"}


def reply_action(ctx: service.Ctx, n: int) -> str | None:
    """Si la tarea n espera un texto de la persona (preguntas del agente o cambios al diseño),
    la acción que lo recibe; si no, None y «n texto» es conversación."""
    try:
        run = service.latest_run(ctx, n)
    except service.OpError:
        return None
    if run["status"] not in ("BLOCKED", "FAILED"):
        return None
    last = ctx.conn.execute("SELECT payload FROM event WHERE run_id = ? AND type IN"
                            " ('run.blocked', 'run.failed') ORDER BY id DESC LIMIT 1",
                            (run["id"],)).fetchone()
    return TEXT_REPLIES.get(json.loads(last[0]).get("code")) if last else None


DIRECTIVE = re.compile(r"^[ \t>*`]*UMBRA>\s*(usar|adoptar|nuevo_proyecto|spec)\s+(.+?)[ \t`*]*$",
                       re.M)


def workspace_prompt(state: State) -> str:
    """Lo que la conversación sabe de tus otros proyectos y cómo pedir al puente que se mueva."""
    from umbra.management import playbooks
    stacks = "|".join(sorted(playbooks.available())) or "stack"
    where = home(state).as_posix()
    return f"""
Atiendes a la persona por Telegram. El proyecto actual es «{state.current}», pero umbra trabaja
con todas las carpetas de {where}:
- Con umbra: {", ".join(sorted(state.roots))}.
- Sin umbra todavía: {", ".join(folders(state)) or "ninguna"}.
Nunca digas que no puedes trabajar en otro proyecto o carpeta. Cuando el mensaje pida trabajar
en otro proyecto, adoptar una carpeta o crear un proyecto nuevo, termina tu respuesta con UNA
de estas líneas, sola y exacta, y umbra lo hace:
UMBRA> usar <proyecto con umbra>   (umbra cambia de proyecto y te repite el mensaje allí)
UMBRA> adoptar <carpeta sin umbra>   (pone umbra en esa carpeta; luego se puede usar)
UMBRA> nuevo_proyecto <nombre> <{stacks}> [idea]   (crea la carpeta en {where})
UMBRA> spec <la idea en una línea, con todo el contexto que tengas>   (abre aquí mismo la
conversación de spec del proyecto actual: spec, plan y tareas, con preguntas y botones)
Crear specs desde aquí SÍ se puede: nunca mandes a la persona a `umbra spec new` ni a su
terminal; usa `UMBRA> spec`. Hay una spec en curso a la vez por proyecto: si te piden varias,
abre la primera y di que las demás siguen cuando esa termine.
No inventes nombres: usa los de las listas. Fuera de {where} no trabajas.
"""


def _offer_db_changes(state: State, ctx: service.Ctx, before: set[str]) -> None:
    """Los cambios de BD que propuso la conversación llegan con botones: solo la persona los
    aplica."""
    for change in service.db_pending(ctx):
        if change["id"] in before:
            continue
        where = (change.get("database") or ctx.config.get("mysql", {}).get("database")
                 or "la base por defecto")
        telegram.send(state.tg, f"Cambio propuesto en MySQL ({where}), en {state.current}:\n"
                      f"```\n{change['sql'][:3000]}\n```\nNo se aplica hasta que lo decidas.",
                      [[("Aplicar cambio", f"dbok:{change['id']}@{state.current}"),
                        ("Descartar", f"dbno:{change['id']}@{state.current}")]])


def converse(state: State, text: str, allow_changes: bool = True, hop: bool = True) -> str:
    """Hablar con umbra sobre el proyecto actual: la conversación de `umbra chat`, hilada, y
    con permiso para actuar (lo que `--allow-changes`; aprobar, rechazar, push y merge siguen
    prohibidos: para eso están los botones). Si responde `UMBRA> usar X`, el puente cambia a X
    y le repite el mensaje allí (una sola vez)."""
    from umbra.chat import launcher
    name = state.current
    ctx = _ctx(state)
    extra = workspace_prompt(state)
    try:
        before = {c["id"] for c in service.db_pending(ctx)}
        res = launcher.ask(ctx.root, ctx.udir, ctx.conn, ctx.config, text,
                           allow_changes=allow_changes, resume=state.sessions.get(name),
                           extra=extra)
        if res["status"] != "ok" and state.sessions.get(name):
            # la sesión retomada pudo caducar o romperse: una vez más, de cero
            state.sessions.pop(name, None)
            res = launcher.ask(ctx.root, ctx.udir, ctx.conn, ctx.config, text,
                               allow_changes=allow_changes, resume=None, extra=extra)
        _offer_db_changes(state, ctx, before)
    except (FileNotFoundError, ValueError) as e:
        return f"No pude preguntar a umbra: {e}"
    finally:
        ctx.conn.close()
    if res["status"] != "ok":
        state.sessions.pop(name, None)
        return f"umbra no respondió: {res.get('error') or 'sin respuesta'}"
    state.sessions[name] = res["session_id"]
    directives = DIRECTIVE.findall(res["answer"])
    answer = DIRECTIVE.sub("", res["answer"]).strip()
    if res["commands"]:
        answer += "\n\n(ejecuté: " + "; ".join(res["commands"][:6]) + ")"
    for word, arg in directives[:1]:  # ponytail: una por mensaje basta para moverse
        if word == "usar" and hop and arg in state.roots and arg != name:
            state.current = arg
            return f"Paso a {arg}.\n\n" + converse(state, text, allow_changes, hop=False)
        if out := command(state, f"/{word} {arg}", "umbra"):
            answer += "\n\n" + out
    return answer.strip() or "(sin respuesta)"


def status_text(state: State) -> str:
    """Qué te necesita ahora en el proyecto actual (sin gastar un modelo)."""
    ctx = _ctx(state)
    try:
        from umbra.unified import explain
        lines = []
        for task in ctx.conn.execute("SELECT * FROM task WHERE status = 'accepted'"
                                     " ORDER BY number"):
            exp = explain.explain_number(ctx.conn, ctx.udir, task)
            if exp.state.startswith(("Detenida", "Falló", "Espera tu")):
                lines.append(f"#{task['number']} {task['title']}: {explain.short(exp)}")
        for d in service.waiting_specs(ctx):
            lines.append(f"spec {d.split('/')[-1]}: espera tu aprobación")
    finally:
        ctx.conn.close()
    head = f"{state.current}: "
    return head + ("\n".join(lines) if lines else "nada te necesita ahora mismo.")


def projects_text(state: State) -> str:
    lines = []
    for p in projects.overview():
        if p["name"] not in state.roots:
            continue
        mark = "▶ " if p["name"] == state.current else "  "
        lines.append(f"{mark}{p['name']} · te necesitan {p['needs']} · en marcha {p['working']}"
                     f" · {p['cost']}")
    free = folders(state)
    return ("Proyectos (▶ el actual; /usar <nombre> cambia):\n" + "\n".join(lines)
            + (f"\n\nSin umbra en {home(state).name} (/adoptar <carpeta>):\n" + ", ".join(free)
               if free else ""))


def _say(state: State):
    """Cómo habla con la persona un trabajo largo o la conversación de spec (botones con el
    repo actual, para que vuelvan al repo correcto)."""
    name = state.current

    def say(text: str, buttons=None) -> None:
        if buttons:
            buttons = [[(label, f"{data}@{name}") for label, data in row] for row in buttons]
            telegram.send(state.tg, text, buttons)
        else:
            send(state.tg, text)
    return say


def _job(state: State, work, say) -> str:
    """Lo que tarda minutos (crear un proyecto, un turno de spec, planificar) corre aparte y
    avisa al terminar; mientras, el puente sigue atendiendo."""
    name = state.current
    if (t := state.jobs.get(name)) and t.is_alive():
        return "Sigo con lo anterior; te aviso en cuanto termine."

    def run():
        try:
            work()
        except Exception as e:  # ponytail: un trabajo roto no tumba el puente
            say(f"No se pudo: {e}")

    t = threading.Thread(target=run, daemon=True)
    state.jobs[name] = t
    t.start()
    return ""


def _onboard(state: State):
    talk = state.onboards.get(state.current)
    return talk if talk and not talk.done else None


def _onboard_step(state: State, talk, step) -> str:
    """Un paso de la persona en el onboarding (puede redactar o explorar: corre aparte)."""
    if talk.busy:
        return "Sigo con el onboarding; un momento."
    say = _say(state)

    def run():
        talk.busy = True
        try:
            step()
        finally:
            talk.busy = False
    return _job(state, run, say) or ""


def _talk(state: State):
    talk = state.talks.get(state.current)
    return talk if talk and not talk.done else None


def with_task(fn):
    """Comandos «/algo N [resto]»: resuelven la tarea y el contexto del repo actual."""
    def run(state: State, text: str, who: str) -> str:
        m = console.NUMBER.match(text)
        if not m:
            return "Indica el número de la tarea: /" + text.lstrip("/").split()[0] + " N"
        n, rest = int(m.group(1)), (m.group(2) or "").strip()
        ctx = _ctx(state)
        try:
            return fn(ctx, n, rest, who)
        except service.OpError as e:
            return f"No se pudo: {e}"
        finally:
            ctx.conn.close()
    return run


def _retry(ctx, n, rest, who):
    stage = service.retry(ctx, n, rest or None, origin=ORIGIN)
    return f"Tarea {n}: reintento en cola desde {ex_stage(stage)}."


def ex_stage(stage: str) -> str:
    from umbra.unified import explain
    return explain.STAGES.get(stage, stage)


def _reject(ctx, n, rest, who):
    service.reject(ctx, n, rest or f"rechazada desde Telegram por {who}", ORIGIN)
    return f"Tarea {n} rechazada: PR cerrado."


def _decide(decision: str):
    def run(ctx, n, rest, who):
        r = service.decide_findings(ctx, n, [], decision, rest or f"desde Telegram por {who}",
                                    ORIGIN)
        extra = f"; tareas nuevas en borrador: {r['tasks']}" if r.get("tasks") else ""
        if r.get("next_stage"):
            stage = service.retry(ctx, n, r["next_stage"], origin=ORIGIN)
            extra += f"; la tarea sigue desde {ex_stage(stage)}"
        return f"Decidido ({r['decided']} hallazgos){extra}."
    return run


TASK_COMMANDS = {
    "explicar": with_task(lambda ctx, n, rest, who: console.explain_text(ctx, n)),
    "registro": with_task(lambda ctx, n, rest, who: console.log_text(ctx, n)),
    "evidencia": with_task(lambda ctx, n, rest, who: console.evidence_text(ctx, n)),
    "cambios": with_task(lambda ctx, n, rest, who: console.changes_text(ctx, n)),
    "agente": with_task(lambda ctx, n, rest, who: console.agent_text(ctx, n)),
    "hallazgos": with_task(lambda ctx, n, rest, who: console.findings_text(ctx, n)),
    "aceptar": with_task(lambda ctx, n, rest, who: (service.accept(ctx, [n], ORIGIN),
                                                    f"Tarea {n} aceptada: ya se puede ejecutar"
                                                    " (/ejecutar {n}).".replace("{n}", str(n))
                                                    )[1]),
    "ejecutar": with_task(lambda ctx, n, rest, who: (service.run(ctx, [n], origin=ORIGIN),
                                                     f"Tarea {n} en cola.")[1]),
    "reintentar": with_task(_retry),
    "decero": with_task(lambda ctx, n, rest, who: (service.run(ctx, [n], new=True,
                                                               origin=ORIGIN),
                                                   f"Tarea {n}: empieza de cero.")[1]),
    "pausar": with_task(lambda ctx, n, rest, who: f"Tarea {n}: {service.pause(ctx, n, ORIGIN)}"
                        " (se detiene al terminar la etapa actual)."),
    "retomar": with_task(lambda ctx, n, rest, who: (service.resume(ctx, n, origin=ORIGIN),
                                                    f"Tarea {n}: retomada.")[1]),
    "cancelar": with_task(lambda ctx, n, rest, who: (service.cancel(ctx, n, ORIGIN),
                                                     f"Tarea {n}: cancelada.")[1]),
    "descartar": with_task(lambda ctx, n, rest, who: (service.drop(ctx, [n], ORIGIN),
                                                      f"Tarea {n}: descartada.")[1]),
    "integrar": with_task(lambda ctx, n, rest, who: f"Tarea {n} integrada "
                          f"({service.approve(ctx, n, ORIGIN)['pr']})."),
    "rechazar": with_task(_reject),
    "noaplica": with_task(_decide("waived")),
    "despues": with_task(_decide("deferred")),
}


def command(state: State, text: str, who: str) -> str:
    """Mensajes de texto: comandos con barra, la conversación de spec, respuestas al agente o
    conversación con umbra."""
    low = text.lower()
    word = low.split()[0].lstrip("/") if low.startswith("/") else ""
    arg = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
    say = _say(state)
    if word in ("start", "ayuda", "help"):
        return HELP
    if word == "proyectos":
        return projects_text(state)
    if word == "usar":
        if arg not in state.roots:
            return f"No conozco «{arg}». " + projects_text(state)
        state.current = arg
        return f"Proyecto actual: {arg}.\n" + status_text(state)
    if word == "nuevo":
        state.sessions.pop(state.current, None)
        return f"Conversación nueva sobre {state.current}."
    if word == "estado":
        return status_text(state)
    if word == "actualizar":
        return update_text()
    if word == "gusto":
        from umbra.management import taste
        return taste.load()[-3500:] or ("Todavía no sé nada de tu gusto: se llena con lo que "
                                        "eliges, pides y apruebas en los diseños.")
    if word == "tareas":
        ctx = _ctx(state)
        try:
            return console.tasks_text(ctx)
        finally:
            ctx.conn.close()
    if word in TASK_COMMANDS:
        return TASK_COMMANDS[word](state, text, who)
    if word == "tarea":
        if not arg:
            return "Escribe: /tarea título | criterio de aceptación | otro criterio"
        title, acceptance = console.parse_task(arg)
        ctx = _ctx(state)
        try:
            n = console.add_task(ctx, title, acceptance)
        finally:
            ctx.conn.close()
        return f"Tarea {n} registrada y aceptada: {title}. /ejecutar {n} la encola."
    if word == "noche":
        ctx = _ctx(state)
        try:
            r = service.night(ctx, arg or None, ORIGIN)
        except service.OpError as e:
            return f"No se pudo: {e}"
        finally:
            ctx.conn.close()
        return (f"Aceptadas {len(r['accepted'])}; en marcha {r['started']} (hasta "
                f"{r['parallel']} a la vez); esperan su turno {r['waiting']}."
                + ("" if r["autopilot"] else " Aviso: [autopilot] enabled = false."))
    if word == "integrar_spec":
        return act(_ctx(state), f"spec:{arg}", who) if arg else "Indica la spec: /integrar_spec 018"
    if word == "hacer":
        return converse(state, arg) if arg else "¿Qué quieres que haga?"
    if word == "spec":
        if not arg:
            return "Escribe la idea: /spec una app para…"
        if _talk(state):
            return "Ya hay una spec en curso en este proyecto; /spec_salir la deja."
        from umbra.management import design_systems as ds
        if ds.needs_choice(proj.load_project(state.roots[state.current])):
            state.pending_specs[state.current] = arg
            say("Antes de la spec: ¿qué sistema de diseño usa este proyecto?",
                [[(label[:60], f"ds:{key}")] for key, label in ds.choices()])
            return ""
        ctx = _ctx(state)
        try:
            state.talks[state.current] = console.SpecTalk(ctx.root, "", arg)  # reserva
            return _job(state, lambda: state.talks.__setitem__(
                state.current, console.SpecTalk.start(service.load(ctx.root), arg, say)),
                say) or "Empiezo la spec; te escribo con la primera pregunta."
        finally:
            ctx.conn.close()
    if word == "spec_seguir":
        if _talk(state):
            return "Ya hay una spec en curso; /spec_salir la deja."
        ctx = _ctx(state)
        try:
            talk = console.SpecTalk.resume(ctx, arg or None, say)
        except service.OpError as e:
            return f"No se pudo: {e}"
        finally:
            ctx.conn.close()
        state.talks[state.current] = talk
        return ""
    if word == "spec_ver":
        talk = _talk(state)
        path = talk.spec_file() if talk else None
        if not path:
            return "No hay una spec en curso con archivo todavía."
        return "" if telegram.send_document(state.tg, path, path.as_posix()) \
            else "No pude enviar el archivo."
    if word == "spec_salir":
        talk = state.talks.pop(state.current, None)
        if talk and not talk.done:
            talk.close()
            return "Dejo la conversación de spec; /spec_seguir la retoma."
        return "No hay una spec en curso."
    if word == "onboarding":
        from umbra.routines.onboard_talk import OnboardTalk
        if (talk := _onboard(state)) and talk.busy:
            return "Sigo con el onboarding; te escribo en cuanto tenga algo."
        root, name = state.roots[state.current], state.current
        fresh = arg.lower().replace("-", " ") in ("de cero", "decero")

        def go():
            state.onboards[name] = OnboardTalk(root, ORIGIN)
            state.onboards[name].busy = True
            try:
                state.onboards[name] = OnboardTalk.start(root, say, ORIGIN, fresh)
            finally:
                state.onboards[name].busy = False
        return _job(state, go, say) or ""
    if word == "sistema":
        from umbra.management import design_systems as ds
        root = state.roots[state.current]
        if arg:
            try:
                ds.set_system(root, arg)
            except ValueError as e:
                return str(e)
            return f"{state.current} usa ahora el sistema de diseño «{arg}»."
        current = ds.chosen(proj.load_project(root))
        say(f"Sistema de diseño de {state.current}: {current or 'sin elegir'}. ¿Cuál usa?",
            [[(label[:60], f"ds:{key}")] for key, label in ds.choices()])
        return ""
    if word == "replicar":
        from umbra.management import replica

        def rep():
            ctx = _ctx(state)
            try:
                r = replica.replicate(ctx.conn, ctx.root, ctx.udir, ctx.config, ORIGIN)
            except replica.ReplicaError as e:
                return say(f"No se pudo: {e}")
            finally:
                ctx.conn.close()
            telegram.send_photos(state.tg, [ctx.root / f for f in r["images"]],
                                 f"Diseño actual de {ctx.root.name}")
            say(f"{len(r['images'])} vistas replicadas en design/actual/.\n{r['summary']}",
                [[("✅ Guardar en el repo", "dr:approve"), ("🗑 Descartar", "dr:discard")]])
        return _job(state, rep, say) or ("Levanto la app y recorro sus vistas; tarda unos "
                                         "minutos.")
    if word == "constitucion":
        from umbra.management import constitution as con
        root = state.roots[state.current]
        if not con.path(root).is_file():
            return "Este proyecto no tiene constitución todavía: /onboarding la redacta."
        return "" if telegram.send_document(state.tg, con.path(root), "constitution.md") \
            else "No pude enviar el archivo."
    if word == "enmendar":
        from umbra.management import constitution as con
        if not arg:
            return "Escribe la enmienda: /enmendar los endpoints nuevos llevan test de contrato"
        root = state.roots[state.current]

        def amend():
            ctx = _ctx(state)
            try:
                diff = con.amend(ctx.conn, ctx.root, ctx.udir, arg, ORIGIN)
            except con.ConstitutionError as e:
                return say(f"No se pudo: {e}")
            finally:
                ctx.conn.close()
            say(f"Enmienda propuesta:\n```\n{diff[-3000:]}\n```",
                [[("✅ Aprobar enmienda", "ce:approve"), ("🗑 Descartar", "ce:discard")]])
        return _job(state, amend, say) or f"Redacto la enmienda en {root.name}…"
    if word == "plan":
        if not arg:
            return "Indica la spec: /plan specs/001-x/spec.md"
        root = state.roots[state.current]
        path = (root / arg).resolve()
        if not path.is_file():
            return f"No existe {arg}."
        return _job(state, lambda: say(console.plan_from_spec(service.load(root), path)),
                    say) or "Planificando: el proponente propone tareas; te aviso al terminar."
    if word == "adoptar":
        if not arg:
            return "Escribe: /adoptar carpeta (una de /proyectos)"
        if arg in state.roots:
            return f"{arg} ya tiene umbra: /usar {arg}"
        if arg not in folders(state):
            return f"No hay una carpeta «{arg}» sin umbra en {home(state).as_posix()}."
        folder = home(state) / arg

        def adopt():
            r = service.adopt(folder, ORIGIN)
            state.roots = served(state.roots[state.current])
            if arg in state.roots:
                state.current = arg
            say(f"umbra adoptó {r['root']} ({r['stack']}): " + ", ".join(r["steps"])
                + f".\nProyecto actual: {state.current}.\n"
                + ("Cada historia de una spec dice en qué repo se hace (**Repo**: nombre). "
                   "Empieza con /spec." if r.get("workspace") else
                   "Antes de trabajar en él, ¿lo estudio a fondo? /onboarding"))
        return _job(state, adopt, say) or f"Adoptando {arg}…"
    if word == "nuevo_proyecto":
        parts = arg.split(maxsplit=2)
        if len(parts) < 2:
            return "Escribe: /nuevo_proyecto nombre stack [idea]"
        name, stack = parts[0], parts[1]
        idea = parts[2] if len(parts) > 2 else None
        parent = home(state)

        def work():
            r = service.new_project(name, stack, parent, True, True, idea, ORIGIN)
            state.roots = served(state.roots[state.current])
            if name in state.roots:
                state.current = name
            say(f"Proyecto creado en {r['root']}: " + ", ".join(r["steps"])
                + (f"\nSin repo en GitHub: {r['remote_error']}" if r.get("remote_error") else "")
                + (f"\nCONTEXT.md: {r['context_error']}" if r.get("context_error") else "")
                + ("\nSpec abierta con tu idea: /spec_seguir" if r.get("conversation") else "")
                + f"\nProyecto actual: {state.current}.")
        return _job(state, work, say) or f"Creando {name} ({stack}) junto a {parent.name}…"
    if word:
        return f"No conozco /{word}. /ayuda muestra los comandos."
    if (onb := _onboard(state)) and onb.pending:
        return _onboard_step(state, onb, lambda: onb.text(text, say))
    if talk := _talk(state):
        if talk.busy:
            return "Sigo con el turno anterior de la spec; te escribo en cuanto termine."
        talk.busy = True
        return _job(state, lambda: talk.do(lambda: talk.text(text, say)), say) or ""
    if m := re.match(r"^#?(\d+)[:\s]+(.+)$", text, re.S):
        ctx = _ctx(state)
        try:
            if kind := reply_action(ctx, int(m.group(1))):
                return act(ctx, f"{kind}:{m.group(1)}:{m.group(2).strip()}", who)
        finally:
            ctx.conn.close()
    return converse(state, text)


def handle(state: State, update: dict) -> str | None:
    """Atiende una actualización de Telegram; devuelve la respuesta enviada (o None)."""
    tg = state.tg
    if cb := update.get("callback_query"):
        msg = cb.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != tg["chat_id"]:
            return None  # otro chat: ni caso
        who = str((cb.get("from") or {}).get("username") or (cb.get("from") or {}).get("id"))
        data, name = _split(cb.get("data") or "")
        if name and name in state.roots:
            state.current = name
        if msg.get("message_id"):
            telegram.clear_buttons(tg, msg["message_id"])
        if data.startswith("ds:"):  # el sistema de diseño del proyecto
            from umbra.management import design_systems as ds
            key = data.partition(":")[2]
            try:
                ds.set_system(state.roots[state.current], key)
                reply = f"{state.current} usa el sistema de diseño «{key}»."
            except ValueError as e:
                reply = str(e)
            telegram.ack(tg, cb["id"], reply[:60])
            send(tg, reply)
            if idea := state.pending_specs.pop(state.current, None):
                if follow := command(state, f"/spec {idea}", who):
                    send(tg, follow)
            return reply
        if data.startswith(("oq:", "or:")):  # el onboarding
            talk = _onboard(state)
            say = _say(state)
            kind, _, choice = data.partition(":")
            reply = ("No hay un onboarding en curso; /onboarding lo retoma." if not talk else
                     _onboard_step(state, talk, lambda: (talk.option if kind == "oq"
                                                         else talk.decide)(choice, say)))
            telegram.ack(tg, cb["id"], reply[:60])
            if reply:
                send(tg, reply)
            return reply
        if data.startswith(("sq:", "sr:")):  # la conversación de spec
            talk = _talk(state)
            if not talk:
                reply = "No hay una spec en curso."
            elif talk.busy:
                reply = "Sigo con el turno anterior; un momento."
            else:
                kind, _, choice = data.partition(":")
                say = _say(state)
                if kind == "sq":
                    def step(): talk.option(choice, say)  # noqa: E704
                else:
                    def step(): talk.decide(choice, say)  # noqa: E704
                talk.busy = True  # desde ya: el hilo puede tardar en arrancar
                reply = _job(state, lambda: talk.do(step), say)
            telegram.ack(tg, cb["id"], reply[:60])
            if reply:
                send(tg, reply)
            return reply
        ctx = _ctx(state)
        try:
            reply = act(ctx, data, who)
        finally:
            ctx.conn.close()
        telegram.ack(tg, cb["id"], reply)
        send(tg, reply)
        return reply
    if msg := update.get("message"):
        if str((msg.get("chat") or {}).get("id")) != tg["chat_id"]:
            return None
        who = str((msg.get("from") or {}).get("username") or (msg.get("from") or {}).get("id"))
        text = (msg.get("text") or "").strip()
        replied = (msg.get("reply_to_message") or {}).get("text") or ""
        if m := re.search(r"umbra · (\S+) · tarea #(\d+)", replied):
            if m.group(1) in state.roots:
                state.current = m.group(1)
            ctx = _ctx(state)
            try:
                if text and (kind := reply_action(ctx, int(m.group(2)))):
                    reply = act(ctx, f"{kind}:{m.group(2)}:{text}", who)
                    send(tg, reply)
                    return reply
            finally:
                ctx.conn.close()
        reply = command(state, text, who) if text else HELP
        if reply:  # vacío = un trabajo largo o la spec ya respondieron por su cuenta
            send(tg, reply)
        return reply
    return None


def send(tg: dict, text: str) -> None:
    for i in range(0, max(len(text), 1), CHUNK):  # Telegram corta a 4096 caracteres
        telegram.send(tg, text[i:i + CHUNK])


def run_once(state: State, timeout: float = telegram.POLL_TIMEOUT_S) -> int:
    """Una ronda de long polling; devuelve cuántas actualizaciones atendió."""
    seen = 0
    for update in telegram.updates(state.tg, state.offset, timeout):
        state.offset = max(state.offset, int(update.get("update_id", 0)) + 1)
        seen += 1
        try:
            handle(state, update)
        except Exception as e:  # ponytail: el puente no se cae por una decisión fallida
            try:
                ctx = _ctx(state)
                add_event(ctx.conn, None, "telegram.error", ORIGIN, error=str(e))
                ctx.conn.close()
            except Exception:
                pass
    return seen


# ---------- un solo puente para todos los repos ----------
def _lock() -> Path:
    return cfg.umbra_home() / LOCK


def _me() -> str:
    return f"{os.getpid()}@{socket.gethostname()}"


def alive() -> bool:
    """Hay un puente atendiendo el bot (su latido tiene menos de TTL_S segundos)."""
    try:
        data = json.loads(_lock().read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["beat"]) + timedelta(seconds=TTL_S) \
            > datetime.now(UTC)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _beat(root: Path | None = None) -> None:
    _lock().parent.mkdir(parents=True, exist_ok=True)
    data = {"owner": _me(), "beat": datetime.now(UTC).isoformat()}
    if root:  # para relanzarlo en su carpeta tras actualizar
        data["root"] = root.as_posix()
    _lock().write_text(json.dumps(data), encoding="utf-8")


def _mine() -> bool:
    try:
        return json.loads(_lock().read_text(encoding="utf-8")).get("owner") == _me()
    except (OSError, ValueError):
        return False


def stop() -> bool:
    try:
        _lock().unlink()
        return True
    except FileNotFoundError:
        return False


def handoff() -> dict | None:
    """Antes de actualizar: detiene el puente vivo y devuelve su proceso y carpeta, para esperar
    a que salga (`stop` solo avisa; el proceso termina tras su espera de Telegram) y relanzarlo
    después."""
    if not alive():
        return None
    try:
        data = json.loads(_lock().read_text(encoding="utf-8"))
        pid = int(str(data["owner"]).split("@")[0])
    except (OSError, ValueError, KeyError):
        return None
    stop()
    return {"pid": pid, "root": data.get("root")}


def begin_update(latest: str) -> str:
    """`umbra self-update` y `/actualizar`: detiene el puente (si hay) y lanza la instalación,
    que lo relanza al terminar y avisa por Telegram."""
    from umbra import __version__
    from umbra.unified import version
    held = handoff()
    try:
        root = Path(held["root"]) if held and held.get("root") else service.load().root
        tg = telegram.target(proj.load_project(root))
    except (service.OpError, OSError, ValueError):
        tg = None
    previous = None if version.is_dev() else __version__
    try:
        return version.install(latest, previous, held, tg)
    except version.VersionError:
        if held and held.get("root"):  # no se llegó a instalar: el puente vuelve como estaba
            spawn(Path(held["root"]))
        raise


def update_text() -> str:
    """`/actualizar`: qué trae la versión nueva y lanzarla (el puente se reinicia solo)."""
    from umbra import __version__
    from umbra.unified import version
    try:
        latest = version.latest()
    except version.VersionError as e:
        return f"No pude consultar las versiones: {e}"
    if not latest or version.parse(latest) <= version.parse(__version__):
        return f"Ya estás en v{__version__}, la última."
    notes = version.notes(latest)
    try:
        started = begin_update(latest)
    except version.VersionError as e:
        return f"No se pudo actualizar: {e}"
    return (f"Actualizando de v{__version__} a v{latest}. {started}"
            + (f"\n\nQué trae:\n{notes[:1500]}" if notes else ""))


def serve(root: Path) -> int:
    """Atiende el teléfono para todos tus repos hasta `umbra bridge --stop`. Devuelve cuántas
    actualizaciones atendió."""
    roots = served(root)
    tg = telegram.settings(proj.load_project(root)) if root in roots.values() else None
    if not tg:
        raise service.OpError("Telegram no está configurado: [notify.telegram] token_env y "
                              "chat_id en .umbra/project.toml, y el token en el entorno", 2)
    if alive() and not _mine():
        return 0  # otro puente ya atiende el bot
    _beat(root)
    telegram.set_commands(tg, COMMANDS)
    state = State(tg, roots, root.name, workspace=root.parent)
    seen, rounds = 0, 0
    try:
        while _mine():
            _beat(root)
            rounds += 1
            if rounds % 10 == 0:  # repos nuevos (umbra init / umbra new) entran solos
                state.roots = served(root)
            got = run_once(state)
            seen += got
            if not got:
                time.sleep(0.5)
    finally:
        if _mine():
            stop()
    return seen


def spawn(root: Path) -> None:
    """Lanza el puente en segundo plano (como el worker); no hace nada si ya hay uno vivo."""
    log = root / proj.UMBRA_DIR / "artifacts" / "bridge.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as out:
        subprocess.Popen([sys.executable, "-m", "umbra.cli.main", "bridge", "--root", str(root)],
                         cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                         close_fds=True, **background_kwargs())
