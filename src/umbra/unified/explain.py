"""Traduce el estado de una tarea a lenguaje llano: qué pasa, por qué y qué puedes hacer.

Los motivos de bloqueo llegan con un código estable (engine.Outcome.code). Para ejecuciones
antiguas sin código, se deduce del texto del motivo.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from umbra.unified.store import run_spend

TASK_STATES = {"draft": "Borrador", "accepted": "Aceptada", "done": "Hecha",
               "dropped": "Descartada"}
RUN_STATES = {
    "QUEUED": "En cola",
    "RUNNING": "Trabajando",
    "PAUSED": "En pausa",
    "WAITING_APPROVAL": "Espera tu aprobación",
    "BLOCKED": "Detenida: necesita tu decisión",
    "FAILED": "Falló por un problema técnico",
    "CANCELLED": "Cancelada",
    "SUCCEEDED": "Integrada",
}
STAGES = {"plan": "Planificar", "design": "Diseñar", "build": "Construir", "review": "Revisar",
          "verify": "Verificar", "scan": "Escanear seguridad", "ship": "Entregar",
          "arbiter": "Arbitrar",
          "summary": "Resumir"}
STAGE_PURPOSE = {
    "plan": "un agente lee el código y decide cómo abordar la tarea",
    "design": "si la tarea toca la interfaz, un agente diseñador la diseña y tú das el visto "
              "bueno antes de construir",
    "build": "el agente constructor escribe el código y umbra corre los tests del proyecto",
    "review": "un segundo agente, distinto del que construyó, revisa el cambio",
    "verify": "un agente comprueba uno por uno los criterios de aceptación",
    "scan": "umbra busca secretos y corre los análisis de seguridad configurados",
    "ship": "umbra publica la rama y abre el PR",
}
AGENTS = {"claude-code": "Claude Code", "codex": "Codex", "umbra": "umbra",
          "human": "tú"}
ATTEMPTS = {"running": "en curso", "done": "bien", "tests_failed": "tests fallaron",
            "policy_violation": "frenado por una regla", "error": "error técnico",
            "timeout": "tiempo agotado", "interrupted": "interrumpido",
            "no_changes": "sin cambios", "findings": "con observaciones",
            "blocked": "con preguntas", "secrets": "secreto detectado",
            "conflicts": "conflictos sin resolver"}

WHY_TESTS = ("Los tests que ya existían son la red de seguridad del proyecto: demuestran que lo "
             "que funcionaba sigue funcionando. Si un agente pudiera cambiarlos o desactivarlos, "
             "podría «hacer pasar» los tests ajustando las comprobaciones en lugar de arreglar el "
             "código. Por eso umbra permite añadir tests nuevos, pero no quitar ni cambiar los "
             "existentes.")


@dataclass
class Action:
    what: str
    command: str | None = None


@dataclass
class Explanation:
    task: int
    title: str
    state: str
    headline: str
    why: str = ""
    details: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    progress: list[tuple[str, str]] = field(default_factory=list)  # (etapa, marca)
    code: str | None = None
    brief: str = ""  # motivo corto para tablas
    about: dict = field(default_factory=dict)  # de qué trata (ver about())
    kind: str = ""  # situación estable para decidir acciones: draft, ready, waiting_deps,
    #                 dropped, done o el estado de la ejecución en minúsculas

    def as_dict(self) -> dict:
        return asdict(self)


# ---------- motivos de bloqueo ----------
def _policy(n, d):
    kinds = {v["code"] for v in d.get("violations", [])}
    files = [v["message"] for v in d.get("violations", [])]
    if kinds <= {"protected_path"}:
        return ("El agente modificó un archivo que umbra protege.",
                "Rutas como `.umbra/` (la configuración y las reglas de umbra) o "
                "`.github/workflows/` (la integración continua) definen los controles. Un agente "
                "no puede cambiarlas, porque podría relajar los mismos controles que lo vigilan.",
                files,
                [Action("Pedirle al agente que lo rehaga sin tocar esos archivos (recibirá este "
                        "motivo)", f"umbra retry {n} --from build"),
                 Action("Si ese cambio sí hace falta, hazlo tú a mano y luego reintenta"),
                 Action("Descartar esta ejecución", f"umbra cancel {n}")])
    headline = {"test_deleted": "El agente borró un archivo de tests que ya existía.",
                "test_skipped": "El agente desactivó un test (lo marcó para saltarse)."}
    first = next(iter(kinds - {"protected_path"}), "test_changed")
    paths = " ".join(v.get("path") for v in d.get("violations", []) if v.get("path"))
    return (headline.get(first, "El agente cambió un test que ya existía."), WHY_TESTS, files,
            [Action("Pedirle que lo rehaga dejando intactos los tests existentes (recibirá este "
                    "motivo y la regla)", f"umbra retry {n} --from build"),
             Action("Si ese cambio sí hace falta (la tarea lo exige), autorízalo y continúa "
                    "(a en watch)", f"umbra task allow {n} {paths}".rstrip()),
             Action("Ver qué cambió exactamente", f"umbra evidence {n}"),
             Action("Descartar esta ejecución", f"umbra cancel {n}")])


def _tests_failing(n, d):
    tail = [ln for ln in (d.get("output") or "").splitlines() if ln.strip()][-6:]
    details = []
    if d.get("command"):
        details.append(f"Comando de tests: `{d['command']}` (terminó con código "
                       f"{d.get('exit_code')})")
    if tail:
        details.append("Últimas líneas de la salida:\n" + "\n".join(f"    {ln}" for ln in tail))
    return (f"Los tests siguen fallando después de {d.get('attempts', 'varios')} intentos.",
            "umbra solo entrega trabajo que pasa los tests del proyecto. En cada intento le "
            "devolvió al agente el error para que lo corrigiera; como no lo logró, se detiene "
            "para no seguir gastando sin tu criterio.",
            details,
            [Action("Ver la salida completa de cada intento", f"umbra evidence {n}"),
             Action("Comprobar que los tests pasaban antes de la tarea", "umbra exec test"),
             Action("Precisar la tarea (descripción o criterios) si era ambigua o muy grande",
                    f'umbra task edit {n} -d "..."'),
             Action("Darle otra ronda de intentos", f"umbra retry {n} --from build")])


def _questions(n, d):
    stage = d.get("stage", "plan")
    return ("El agente tiene preguntas antes de seguir.",
            "Cuando una tarea es ambigua en algo que cambia el resultado, umbra prefiere "
            "preguntarte antes que dejar que el agente invente reglas de negocio.",
            [f"Pregunta: {q}" for q in d.get("questions", [])],
            [Action("Respóndele: el agente recibe tu respuesta y sigue desde donde quedó "
                    "(r en watch)", f'umbra task answer {n} "..."'),
             Action("Si pide permiso para cambiar tests o rutas protegidas, autorízalo "
                    "(a en watch)", f"umbra task allow {n} <ruta>"),
             Action("O ajusta la descripción o los criterios y reintenta",
                    f'umbra task edit {n} -d "..." && umbra retry {n} --from {stage}')])


def _simple(headline, why, actions):
    return lambda n, d: (headline, why, [], [Action(w, c.format(n=n) if c else None)
                                             for w, c in actions])


def _findings(n, d):
    stage = d.get("stage", "review")
    items = [f"[{f.get('severity')}] {f.get('message')}"
             + (f" ({f['file']}:{f.get('line')})" if f.get("file") else "")
             for f in d.get("findings", [])]
    if stage == "verify":
        head = "Algunos criterios de aceptación no se cumplen, aun después de corregir."
        why = ("Un agente verificador comprueba cada criterio que definiste. Lo que no se cumple "
               "vuelve a Construir; si tras varios ciclos sigue sin cumplirse, umbra se detiene.")
    elif stage == "scan":
        head = "El análisis de seguridad sigue fallando, aun después de corregir."
        why = ("Los análisis de seguridad configurados en el proyecto deben pasar antes de "
               "entregar. Lo que fallan vuelve a Construir; si persiste, umbra se detiene.")
    else:
        head = "El revisor encontró problemas importantes que siguen sin resolverse."
        why = ("Un segundo agente, distinto del que construyó, revisa el cambio. Lo que marca como "
               "importante (severidad alta o crítica) vuelve a Construir para corregirse; si "
               "persiste tras varios ciclos, umbra se detiene para que decidas tú.")
    return (head, why, items,
            [Action("Ver todos los hallazgos y la evidencia", f"umbra evidence {n}"),
             Action("Si un hallazgo no aplica, aclara la tarea para que no se repita",
                    f'umbra task edit {n} -d "..."'),
             Action("Si alguno no aplica o puede esperar, decídelo tú (h en watch)",
                    f"umbra finding list {n}"),
             Action("Darle otra ronda de correcciones", f"umbra retry {n} --from build"),
             Action("Descartar esta ejecución", f"umbra cancel {n}")])


def _secrets(n, d):
    items = [f"{f.get('file')}:{f.get('line')} parece un {f.get('rule')}"
             for f in d.get("findings", [])]
    return ("Se detectó lo que parece un secreto (una clave o un token) en el cambio.",
            "Un secreto subido a un repositorio queda en el historial aunque después se borre, "
            "así que umbra lo bloquea siempre y el agente no puede saltarse esta regla.",
            items,
            [Action("Si es una credencial real, revócala ya en su servicio"),
             Action("Pedirle al agente que lo rehaga sin incluirla (por ejemplo, leyéndola de "
                    "una variable de entorno)", f"umbra retry {n} --from build"),
             Action("Descartar esta ejecución", f"umbra cancel {n}")])


def _failure(headline, why_extra=""):
    def build(n, d):
        details = [f"Detalle técnico: {d['error']}"] if d.get("error") else []
        return (headline,
                "No es un problema de tu código ni de la tarea: algo impidió completar el "
                "trabajo (la sesión del agente, la red, un límite de uso o un error interno)."
                + why_extra,
                details,
                [Action("Comprobar herramientas y sesiones", "umbra doctor"),
                 Action("Reintentar", f"umbra retry {n}"),
                 Action("Ver el registro técnico completo", f"umbra log {n} --raw")])
    return build


REASONS = {
    "policy": _policy,
    "tests_failing": _tests_failing,
    "agent_questions": _questions,
    "findings": _findings,
    "secrets": _secrets,
    "no_changes": _simple(
        "El agente terminó sin cambiar ningún archivo.",
        "Puede que considere que la tarea ya estaba hecha o que no entendió qué debía cambiar. "
        "umbra no entrega un PR vacío.",
        [("Ver qué dijo el agente", "umbra log {n}"),
         ("Precisar qué debe cambiar", 'umbra task edit {n} -d "..."'),
         ("Reintentar", "umbra retry {n} --from build"),
         ("Si ya estaba hecha, descartar esta ejecución", "umbra cancel {n}")]),
    "dev_not_ready": _simple(
        "La aplicación de desarrollo no llegó a responder y la verificación en el navegador "
        "no pudo hacerse.",
        "umbra levanta el comando `dev` de .umbra/project.toml sobre el código de la tarea y "
        "espera a que su `url` responda. Revisa el comando, el puerto y el registro que cita el "
        "motivo.",
        [("Ver el registro", "umbra log {n}"),
         ("Reintentar la verificación", "umbra retry {n} --from verify")]),
    "agent_timeout": _simple(
        "El agente superó su tiempo máximo y umbra lo detuvo.",
        "Cada agente trabaja en un bloque de tiempo y costo acotado, para que una tarea no se "
        "quede consumiendo sin control.",
        [("Dividir la tarea en partes más pequeñas", 'umbra task edit {n} -d "..."'),
         ("Ver el límite de tiempo del perfil (max_minutes)", "umbra profile show builder-tdd"),
         ("Reintentar", "umbra retry {n}")]),
    "readonly_modified": _simple(
        "Un agente que solo debía revisar modificó archivos.",
        "Revisar y verificar son etapas de solo lectura: si quien revisa pudiera cambiar el "
        "código, la revisión dejaría de ser independiente.",
        [("Reintentar desde la revisión", "umbra retry {n} --from review"),
         ("Revisar las instrucciones del perfil revisor", "umbra profile show reviewer-strict")]),
    "base_conflict": _simple(
        "Mientras esperaba tu aprobación, la rama base cambió y este cambio ya no encaja limpio.",
        "Otra tarea (u otra persona) integró cambios en las mismas líneas que toca esta. umbra "
        "no fusiona a ciegas: pone la rama al día, el agente resuelve el choque conservando ambos "
        "cambios y se vuelve a probar y revisar antes de pedirte aprobación otra vez. Tu "
        "aprobación anterior no se registró.",
        [("Ponerla al día y volver a verificar", "umbra retry {n} --from build"),
         ("Ver el PR y su conflicto", "umbra evidence {n}"),
         ("Descartar esta ejecución", "umbra cancel {n}")]),
    "base_conflict_unresolved": _simple(
        "El agente no logró resolver el conflicto con la rama base.",
        "Al poner la tarea al día con la rama base hubo choques que el agente debía resolver "
        "conservando ambos cambios. Tras varios intentos siguen quedando marcas de conflicto, así "
        "que umbra se detiene para que decidas.",
        [("Darle otra ronda", "umbra retry {n} --from build"),
         ("Empezar la tarea de cero sobre la base actual", "umbra run {n} --new"),
         ("Descartar esta ejecución", "umbra cancel {n}")]),
    "stale_sha": _simple(
        "El código cambió después de haberse probado.",
        "umbra solo entrega exactamente lo que probó. Si apareció un commit nuevo, hay que volver "
        "a verificarlo antes de integrarlo.",
        [("Volver a construir y verificar", "umbra retry {n} --from build")]),
    "no_test_command": _simple(
        "El proyecto no tiene un comando de tests registrado.",
        "Sin tests, umbra no puede demostrar que el cambio funciona ni que no rompe nada, así "
        "que no entrega.",
        [("Registra `test` en .umbra/project.toml y compruébalo", "umbra exec test"),
         ("Luego reintenta", "umbra retry {n}")]),
    "agent_not_verified": _simple(
        "El agente que usa esta etapa está registrado pero no verificado.",
        "Un agente nuevo debe pasar una prueba antes de trabajar en tareas reales.",
        [("Verificarlo", "umbra agent list"), ("Luego reintenta", "umbra retry {n}")]),
    "design_review": _simple(
        "El diseño está listo y espera tu visto bueno antes de construir.",
        "La tarea toca la interfaz: el diseñador dejó las pantallas en design/ y el constructor "
        "maquetará sobre lo que apruebes.",
        [("Ver las pantallas", "umbra evidence {n}"), ("Aprobarlo", "umbra design ok {n}"),
         ("Pedir cambios", 'umbra design cambios {n} "..."')]),
    "design_outside": _simple(
        "El diseñador tocó archivos fuera de design/.",
        "Diseñar solo puede cambiar la carpeta design/: el código lo escribe el constructor.",
        [("Reintentar el diseño", "umbra retry {n} --from design")]),
    "design_empty": _simple(
        "El diseñador terminó sin exportar pantallas.",
        "Sin imágenes no hay nada que aprobar ni en qué basarse para maquetar.",
        [("Ver qué dijo", "umbra log {n}"),
         ("Reintentar el diseño", "umbra retry {n} --from design")]),
    "agent_error": _failure("El agente falló por un problema técnico."),
    "agent_unknown": _failure("La rutina usa un agente que umbra no conoce."),
    "internal_error": _failure("umbra encontró un error inesperado."),
}

BRIEF = {  # versión corta para tablas y listas
    "tests_failing": "los tests siguen fallando",
    "agent_questions": "el agente tiene preguntas",
    "design_review": "el diseño espera tu visto bueno",
    "design_outside": "el diseñador tocó código",
    "design_empty": "el diseñador no dejó pantallas",
    "findings": "hay problemas sin resolver",
    "secrets": "posible secreto en el cambio",
    "no_changes": "el agente no cambió nada",
    "agent_timeout": "se agotó el tiempo",
    "dev_not_ready": "la app de desarrollo no respondió",
    "readonly_modified": "un revisor modificó archivos",
    "stale_sha": "el código cambió tras probarse",
    "base_conflict": "la base cambió: hay conflictos",
    "base_conflict_unresolved": "conflicto con la base sin resolver",
    "no_test_command": "falta el comando de tests",
    "agent_not_verified": "agente sin verificar",
    "agent_error": "problema técnico del agente",
    "agent_unknown": "agente desconocido",
    "internal_error": "error inesperado",
    "test_changed": "el agente cambió un test existente",
    "test_deleted": "el agente borró un test existente",
    "test_skipped": "el agente desactivó un test",
    "protected_path": "tocó un archivo protegido",
    "policy_relaxed": "regla ajustada: ya puede continuar",
}

LEGACY = [  # motivo en texto (ejecuciones anteriores a los códigos) → código
    (r"^política:", "policy"), (r"tests siguen fallando", "tests_failing"),
    (r"necesita aclaraciones", "agent_questions"), (r"no produjo cambios", "no_changes"),
    (r"tiempo agotado", "agent_timeout"), (r"hallazgos bloqueantes", "findings"),
    (r"^secretos", "secrets"), (r"modificó el workspace", "readonly_modified"),
    (r"SHA actual", "stale_sha"), (r"comando 'test'", "no_test_command"),
    (r"no verificado", "agent_not_verified"),
]
_VIOLATION = [("test existente borrado", "test_deleted"),
              ("test existente desactivado", "test_skipped"),
              ("test existente modificado", "test_changed"),
              ("ruta protegida", "protected_path")]


def classify(payload: dict, status: str) -> tuple[str, dict]:
    if payload.get("code"):
        return payload["code"], payload.get("details") or {}
    reason = payload.get("reason") or ""
    code = next((c for pat, c in LEGACY if re.search(pat, reason)),
                "agent_error" if status == "FAILED" else "unknown")
    details: dict = {"error": reason}
    if code == "policy":
        parts = reason.split(":", 1)[1].split(";")
        details = {"violations": [
            {"code": next((c for k, c in _VIOLATION if k in p), "test_changed"),
             "message": p.strip()} for p in parts if p.strip()]}
    elif code == "agent_questions":
        details = {"questions": [q.strip() for q in reason.split(":", 1)[-1].split(";")],
                   "stage": payload.get("stage", "plan")}
    elif code == "tests_failing":
        m = re.search(r"tras (\d+)", reason)
        details = {"attempts": int(m.group(1)) if m else None}
    elif code == "findings":
        m = re.search(r" en (\w+)", reason)
        details = {"stage": m.group(1) if m else "review", "findings": []}
    return code, details


# ---------- explicación de una tarea ----------
def _last(conn, run_id, *types):
    marks = ",".join("?" * len(types))
    row = conn.execute(f"SELECT payload, created_at FROM event WHERE run_id = ? AND type IN"
                       f" ({marks}) ORDER BY id DESC LIMIT 1", (run_id, *types)).fetchone()
    return (json.loads(row["payload"]), row["created_at"]) if row else (None, None)


def _progress(stages: list[str], run) -> list[tuple[str, str]]:
    status, current = run["status"], run["stage"]
    if status in ("WAITING_APPROVAL", "SUCCEEDED"):
        return [(STAGES.get(s, s), "hecho") for s in stages]
    idx = stages.index(current) if current in stages else 0
    mark = {"BLOCKED": "detenida", "FAILED": "falló", "CANCELLED": "cancelada",
            "PAUSED": "en pausa"}.get(status, "en curso")
    return [(STAGES.get(s, s), "hecho" if i < idx else mark if i == idx else "pendiente")
            for i, s in enumerate(stages)]


def tokens_text(tokens: int) -> str:
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    return f"{tokens / 1000:.0f}k" if tokens >= 1000 else str(tokens)


def spend_text(cost, tokens: int = 0) -> str:
    """Dólares conocidos y, aparte, los tokens de Codex (que no informa dólares)."""
    cost = Decimal(str(cost or 0))
    if not tokens:
        return f"${cost:.2f}"
    unpriced = f"{tokens_text(tokens)} tokens"
    return unpriced if cost == 0 else f"${cost:.2f} + {unpriced}"


def spec_line(p: dict) -> str:
    """Una línea de avance por spec: «specs/001-x · fase plan · 1 de 3 historias · $0.42»."""
    parts = [p["spec_dir"], f"fase {p['phase']}" if p["phase"] else "sin conversación",
             f"{p['stories_done']} de {p['stories_total']} historias"]
    if p["misaligned"]:
        n = len(p["misaligned"])
        parts.append(f"{n} desalineada{'s' if n > 1 else ''}")
    if pr := p.get("pr"):
        parts.append("integrada" if pr["state"] == "merged"
                     else f"espera tu aprobación (PR #{pr['number']})")
    parts.append(spend_text(p["cost"], p["unpriced_tokens"]))
    return " · ".join(parts)


def _cost(conn, run_id) -> str:
    return spend_text(*run_spend(conn, run_id))


def explain_task(conn, task, run=None, stages: list[str] | None = None,
                 waiting_on: list[int] | None = None,
                 policy_now: list | None = None) -> Explanation:
    """policy_now: violaciones de política del cambio actual según la regla vigente (None si no
    se pudo evaluar). Sirve para avisar cuando un bloqueo viejo ya no aplica."""
    n, title = task["number"], task["title"]
    if run is None:
        if task["status"] == "draft":
            return Explanation(n, title, TASK_STATES["draft"],
                               "Es un borrador: todavía no decidiste si hacerla.", kind="draft",
                               actions=[Action("Revisarla y ajustarla", f'umbra task edit {n} ...'),
                                        Action("Aceptarla para poder ejecutarla",
                                               f"umbra task accept {n}"),
                                        Action("Descartarla", f"umbra task drop {n}")])
        if task["status"] == "accepted" and waiting_on:
            deps = ", ".join(map(str, waiting_on))
            return Explanation(n, title, "Esperando otras tareas",
                               f"Está aceptada, pero depende de tareas sin terminar: {deps}.",
                               "umbra respeta el orden de dependencias para no construir sobre "
                               "algo que todavía no existe.", kind="waiting_deps",
                               actions=[Action("Ver en qué van", "umbra task list")])
        if task["status"] == "accepted":
            return Explanation(n, title, "Lista para ejecutar",
                               "Está aceptada y lista para que un agente trabaje en ella.",
                               kind="ready", actions=[Action("Ejecutarla", f"umbra run {n}")])
        return Explanation(n, title, TASK_STATES.get(task["status"], task["status"]),
                           f"La tarea está {TASK_STATES.get(task['status'], '').lower()}.",
                           kind=task["status"])

    status = run["status"]
    exp = Explanation(n, title, RUN_STATES.get(status, status), "",
                      progress=_progress(stages or [], run),
                      kind="dropped" if task["status"] == "dropped" else status.lower())
    stage = STAGES.get(run["stage"], run["stage"] or "")
    if status in ("BLOCKED", "FAILED"):
        payload, _ = _last(conn, run["id"], f"run.{status.lower()}")
        code, details = classify(payload or {}, status)
        builder = REASONS.get(code)
        kinds = [v.get("code") for v in details.get("violations", [])]
        exp.brief = BRIEF.get(next((k for k in kinds if k != "protected_path"),
                                   kinds[0] if kinds else code), "")
        if code == "policy" and policy_now == []:
            exp.brief = BRIEF["policy_relaxed"]
            exp.headline = ("Se detuvo por una regla que ya se ajustó: con la regla actual, este "
                            "cambio está permitido.")
            exp.why = ("Antes umbra bloqueaba cualquier cambio en un archivo de tests. Ahora "
                       "permite añadir tests nuevos (y ampliar imports) y solo bloquea lo que "
                       "debilita los existentes: quitar o cambiar líneas, o desactivarlos. El "
                       "cambio de esta tarea solo añade, así que puede continuar.")
            exp.details = [f"Motivo original: {v['message']}"
                           for v in details.get("violations", [])]
            exp.actions = [Action("Continuar desde Construir (correrá los tests y seguirá)",
                                  f"umbra retry {n} --from build")]
        elif builder:
            exp.headline, exp.why, exp.details, exp.actions = builder(n, details)
        else:
            exp.headline = (payload or {}).get("reason") or "Se detuvo sin un motivo registrado."
            exp.actions = [Action("Ver el registro técnico", f"umbra log {n} --raw"),
                           Action("Reintentar", f"umbra retry {n}")]
        if run["worktree"]:
            exp.actions.append(Action("Arreglarlo tú en el editor (y luego umbra done)",
                                      f"umbra open {n}"))
        exp.code = code
        exp.details.insert(0, f"Se detuvo en la etapa «{stage}».")
        exp.details.append(f"Gasto de esta ejecución hasta ahora: {_cost(conn, run['id'])}.")
    elif status == "WAITING_APPROVAL":
        tests = conn.execute("SELECT exit_code, tested_sha FROM artifact WHERE run_id = ?"
                             " AND kind = 'command:test' ORDER BY created_at DESC LIMIT 1",
                             (run["id"],)).fetchone()
        findings = conn.execute("SELECT COUNT(*) FROM finding f JOIN attempt a"
                                " ON a.id = f.attempt_id WHERE a.run_id = ?",
                                (run["id"],)).fetchone()[0]
        pr, _ = _last(conn, run["id"], "pr.opened")
        exp.headline = "Terminó todas las etapas y espera tu revisión para integrarse."
        exp.why = ("Ningún cambio llega a la rama principal sin tu aprobación explícita: es la "
                   "última barrera de control.")
        if tests:
            exp.details.append(f"Los tests del proyecto pasan sobre el commit "
                               f"{tests['tested_sha'][:10]}.")
        exp.details.append(f"Hallazgos de revisión registrados: {findings}.")
        if pr:
            exp.details.append(f"PR #{pr['number']}: {pr['url']}")
        exp.details.append(f"Gasto: {_cost(conn, run['id'])}.")
        exp.actions = [Action("Revisar la evidencia (tests, intentos, costo)",
                              f"umbra evidence {n}"),
                       Action("Aprobar e integrar", f"umbra approve {n}"),
                       Action("Rechazar", f'umbra reject {n} -m "motivo"')]
    elif status == "RUNNING":
        exp.headline = f"Trabajando en la etapa «{stage}»."
        exp.why = (f"En esta etapa {STAGE_PURPOSE.get(run['stage'], '')}."
                   if run["stage"] in STAGE_PURPOSE else "")
        attempt = conn.execute("SELECT attempt_no, agent FROM attempt WHERE run_id = ? AND"
                               " status = 'running' ORDER BY started_at DESC LIMIT 1",
                               (run["id"],)).fetchone()
        if attempt:
            exp.details.append(f"Intento {attempt['attempt_no']} con "
                               f"{AGENTS.get(attempt['agent'], attempt['agent'])}.")
        exp.actions = [Action("Seguirla en vivo", "umbra watch"),
                       Action("Pausarla al terminar la etapa actual", f"umbra pause {n}"),
                       Action("Cancelarla", f"umbra cancel {n}")]
    elif status == "QUEUED":
        exp.headline = "En cola: empezará en cuanto quede libre el worker."
        exp.why = "umbra trabaja una tarea a la vez por repositorio, en orden de llegada."
        exp.actions = [Action("Seguirla en vivo", "umbra watch")]
    elif status == "PAUSED":
        exp.headline = f"En pausa por tu pedido, antes de la etapa «{stage}»."
        exp.actions = [Action("Retomarla", f"umbra resume {n}"),
                       Action("Cancelarla", f"umbra cancel {n}")]
    elif status == "SUCCEEDED":
        done, _ = _last(conn, run["id"], "run.succeeded")
        spec, _ = _last(conn, run["id"], "run.integrated")
        if spec:
            exp.headline = (f"Integrada en {spec.get('branch')}: la spec se aprueba completa "
                            "cuando estén todas sus historias.")
            exp.details.append(f"PR #{spec.get('pr')} integrado en la rama de la spec.")
        else:
            exp.headline = "Integrada: el cambio ya está en la rama base."
        if done:
            exp.details.append(f"Merge {str(done.get('merge_sha'))[:10]} (PR #{done.get('pr')}).")
        exp.details.append(f"Gasto total: {_cost(conn, run['id'])}.")
    elif status == "CANCELLED":
        rejected, _ = _last(conn, run["id"], "approval.rejected")
        exp.headline = "Cancelada: no se integró nada y su PR quedó cerrado."
        if rejected:
            exp.details.append(f"Motivo del rechazo: {rejected.get('reason')}")
        exp.actions = [Action("Volver a ejecutarla desde cero", f"umbra run {n}")]
    return exp


def explain_number(conn, udir, task) -> Explanation:
    """Explicación de una tarea con su última ejecución, etapas de su rutina y dependencias."""
    from umbra.management.planning import pending_dependencies
    from umbra.unified import config as cfg

    run = conn.execute("SELECT * FROM run WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
                       (task["id"],)).fetchone()
    stages = None
    if run:
        try:
            stages = [s.name for s in cfg.load_routine(udir, run["routine"]).stages]
        except Exception:  # rutina borrada o inválida: se explica sin la barra de progreso
            stages = []
        if "design" in stages and run["stage"] != "design" and not conn.execute(
                "SELECT 1 FROM event WHERE run_id = ? AND type = 'design.ready' LIMIT 1",
                (run["id"],)).fetchone():
            stages.remove("design")  # solo las tareas que se diseñan muestran esa etapa
    exp = explain_task(conn, task, run, stages, pending_dependencies(conn, task["id"]),
                       _policy_now(udir, run) if run and run["status"] == "BLOCKED" else None)
    exp.about = about(conn, task, run, udir.parent)
    return exp


PRIORITIES = {1: "alta", 2: "media", 3: "baja"}


def _origin(task, root) -> dict | None:
    """Historia de la que viene la tarea y si spec.md ya la cambió (compara `story_hash`)."""
    if not task["spec_dir"] or not task["story"]:
        return None
    from umbra.management import specfile
    changed = False
    try:
        body = (root / task["spec_dir"] / "spec.md").read_text(encoding="utf-8")
        cur = next((s for s in specfile.parse_stories(body) if s.id == task["story"]), None)
        changed = bool(cur and cur.story_hash != task["story_hash"])
    except (OSError, AttributeError, TypeError):  # sin spec.md o sin raíz: no se avisa
        pass
    return {"story": task["story"][2:], "spec_dir": task["spec_dir"],
            "requirements": json.loads(task["requirements"] or "[]"), "misaligned": changed}


def about(conn, task, run=None, root=None) -> dict:
    """De qué trata la tarea: lo que se pidió y, si ya se trabajó, qué planeó e hizo el agente."""
    def neighbours(sql):
        rows = conn.execute(sql, (task["id"],)).fetchall()
        return [{"number": r["number"], "title": r["title"],
                 "status": TASK_STATES.get(r["status"], r["status"])} for r in rows]

    spec = conn.execute("SELECT version FROM spec WHERE id = ?",
                        (task["spec_id"],)).fetchone() if task["spec_id"] else None
    info = {
        "about": (task["about"] if "about" in task.keys() else "").strip(),
        "description": (task["description"] or "").strip(),
        "acceptance": json.loads(task["acceptance"] or "[]"),
        "scope": json.loads(task["scope"] or "[]"),
        "priority": PRIORITIES.get(task["priority"], str(task["priority"])),
        "spec_version": spec["version"] if spec else None,
        "depends_on": neighbours(
            "SELECT t.number, t.title, t.status FROM dependency d JOIN task t"
            " ON t.id = d.depends_on_id WHERE d.task_id = ? ORDER BY t.number"),
        "unblocks": neighbours(
            "SELECT t.number, t.title, t.status FROM dependency d JOIN task t"
            " ON t.id = d.task_id WHERE d.depends_on_id = ? ORDER BY t.number"),
        "plan": None,
        "work": None,
        "origin": _origin(task, root),
    }
    if run:
        plan, _ = _last(conn, run["id"], "plan.ready")
        info["plan"] = (plan or {}).get("plan")
        row = conn.execute(
            "SELECT payload FROM event WHERE run_id = ? AND type = 'attempt.finished'"
            " ORDER BY id DESC LIMIT 20", (run["id"],)).fetchall()
        for r in row:  # el último resumen del constructor que terminó bien
            p = json.loads(r["payload"])
            if p.get("stage") == "build" and p.get("ok") and p.get("summary"):
                info["work"] = p["summary"]
                break
    return info


def _policy_now(udir, run) -> list | None:
    """Re-evalúa el cambio de una ejecución detenida con la política vigente."""
    from pathlib import Path

    from umbra.actions import git, policy
    from umbra.unified.project import load_project

    wt = Path(run["worktree"] or "")
    if not run["worktree"] or not wt.exists() or not run["base_sha"]:
        return None
    try:
        protected = load_project(udir.parent).get("policy", {}).get(
            "protected_paths", policy.DEFAULT_PROTECTED)
        changes = git.changed_files(wt, run["base_sha"])
        edits = {p: git.edit_summary(wt, run["base_sha"], "HEAD", p)
                 for s, p in changes if s[0] == "M" and policy.is_test_file(p)}
        allowed = json.loads(run["allowed_paths"] or "[]") if "allowed_paths" in run.keys() \
            else []
        return policy.check_diff(changes, protected, edits, allowed)
    except Exception:  # no poder re-evaluar no debe impedir explicar
        return None


def short(exp: Explanation) -> str:
    """Una línea para tablas: el estado y, si está detenida, el motivo."""
    if exp.state.startswith(("Detenida", "Falló")):
        word = "Detenida" if exp.state.startswith("Detenida") else "Falló"
        return f"{word}: {exp.brief or exp.headline}"
    return exp.state


# ---------- narración de eventos ----------
def narrate(event: dict) -> str | None:
    t, p = event["type"], event.get("payload") or {}
    stage = STAGES.get(p.get("stage"), p.get("stage") or "")
    agent = AGENTS.get(p.get("agent"), p.get("agent") or "")
    match t:
        case "run.queued":
            return "Tarea en cola."
        case "run.started":
            return "Empezó el trabajo."
        case "stage.started":
            return f"▶ {stage}"
        case "attempt.started":
            n = p.get("n", 1)
            return f"  {agent} empieza{'' if n == 1 else f' (intento {n})'}."
        case "attempt.finished":
            if not p.get("ok"):
                return f"  El agente falló: {p.get('error')}"
            summary = (p.get("summary") or "").strip().split("\n")[0][:220]
            spent = spend_text(p.get("cost"), p.get("unpriced_tokens") or 0)
            return f"  Terminó ({spent}). {summary}".rstrip()
        case "evidence.tests":
            ok = p.get("exit_code") == 0
            return "  Tests del proyecto: pasan ✓" if ok else \
                f"  Tests del proyecto: fallan (código {p.get('exit_code')}); vuelve a intentar."
        case "review.result" | "verify.result" | "scan.result":
            f, b = p.get("findings", 0), p.get("blocking", 0)
            if not f:
                return "  Sin observaciones ✓"
            return f"  {f} observaciones, {b} importantes." if b else \
                f"  {f} observaciones menores; sigue adelante."
        case "dev.started":
            return f"  Aplicación levantada en {p.get('url')} para verla en el navegador."
        case "dev.stopped":
            return "  Aplicación detenida."
        case "evidence.screenshots":
            n = p.get("count", 0)
            return f"  {n} captura{'s' if n != 1 else ''} del navegador como evidencia."
        case "run.integrated":
            return (f"Integrada en {p.get('branch')} (PR #{p.get('pr')}): la spec se aprueba "
                    "completa al final.")
        case "design.skipped":
            return f"  Sin diseño: {p.get('reason')}."
        case "design.ready":
            n = len(p.get("images") or [])
            return f"  Diseño listo: {n} pantalla{'s' if n != 1 else ''} en design/."
        case "design.approved":
            return ("  Diseño aprobado automáticamente." if p.get("auto")
                    else f"  Aprobaste el diseño ({p.get('actor')}): se maqueta sobre él.")
        case "design.changes":
            return f"  Pediste cambios al diseño: {p.get('text')}"
        case "takeover.opened":
            return f"  Lo abriste en tu editor ({p.get('editor')}): umbra espera tu arreglo."
        case "takeover.done":
            return f"  Tu arreglo: {p.get('message')}. Se prueba y se revisa como un intento más."
        case "stage.escalated":
            return (f"  ↑ Construir agotó sus intentos ({p.get('reason')}); sigue un perfil más "
                    f"fuerte: {p.get('profile')}.")
        case "stage.arbiter":
            return (f"  Constructor y revisor no se ponen de acuerdo: arbitra "
                    f"{p.get('profile')} sobre {p.get('findings')} hallazgos.")
        case "arbiter.result":
            if p.get("kept"):
                return f"  El árbitro descartó {p.get('dropped')} y mantuvo {p.get('kept')}."
            return "  El árbitro descartó todos los hallazgos: sigue adelante."
        case "stage.fallback":
            who = AGENTS.get(p.get("failed"), p.get("failed"))
            return f"  {who} falló ({p.get('error')}); revisa {p.get('profile')} en su lugar."
        case "stage.rework":
            return f"  Vuelve a Construir para corregir lo que marcó «{stage}»."
        case "git.pushed":
            return "  Rama publicada."
        case "pr.opened":
            return f"  PR #{p.get('number')} abierto: {p.get('url')}"
        case "run.waiting_approval":
            return "Listo: espera tu aprobación (umbra approve)."
        case "run.blocked" | "run.failed":
            code, details = classify(p, "FAILED" if t == "run.failed" else "BLOCKED")
            builder = REASONS.get(code)
            head = builder(0, details)[0] if builder else p.get("reason")
            word = "Falló" if t == "run.failed" else "Detenida"
            return f"■ {word}: {head} (más detalle con umbra explain)"
        case "base.synced":
            return "  Rama puesta al día con la base (sin conflictos)."
        case "base.conflict":
            files = ", ".join(p.get("files") or [])
            return f"  La base cambió y hay conflictos en {files}: el agente los resolverá."
        case "run.retried":
            return f"Reintento desde «{stage}»."
        case "approval.approved":
            return f"Aprobada por {p.get('actor')}."
        case "approval.rejected":
            return f"Rechazada: {p.get('reason')}"
        case "run.succeeded":
            return "Integrada ✓"
        case "run.cancel_requested":
            return "Cancelación solicitada."
        case "run.pause_requested":
            return "Pausa solicitada."
        case "run.resumed":
            return "Retomada."
    return None  # eventos internos que no aportan a la lectura humana
