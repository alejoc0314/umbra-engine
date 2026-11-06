"""`umbra chat`: Claude Code interactivo con el contexto y las reglas de umbra.

Usa el `claude` instalado con el login del propio usuario; umbra no gestiona credenciales.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

from umbra.adapters.claude_code import parse_stream
from umbra.blocks.process import run_bounded
from umbra.chat import elicit
from umbra.unified import store
from umbra.unified.store import status_summary

NO_RESULT = "claude no devolvió un evento result"  # el texto de parse_stream

# db change solo propone: el cambio espera a la persona (db apply / botón de Telegram)
QUERY = ("status", "explain", "log", "evidence", "task list", "doctor", "finding list",
         "spec list", "db query", "db list", "db change", "lesson list", "lesson show")
# lesson approve/discard/retire/resolve: decidir una lección es solo de la persona (spec 035)
# ponytail: `exec` no va aquí: en Claude Code `ask` gana sobre `allow` y taparía los `safe`.
STATEFUL = ("plan", "run", "pause", "resume", "cancel", "retry", "task add", "task edit",
            "task accept", "task drop", "task deps", "spec tasks")
# watch, spec new/resume: pantalla interactiva, colgaría el chat; finding waive/defer: bajar un
# control lo decide la persona
FORBIDDEN_UMBRA = ("approve", "reject", "watch", "finding waive", "finding defer",
                   "spec new", "spec resume", "db apply", "db discard")
FORBIDDEN_SHELL = ("git push", "gh pr merge")
POLICY_FILES = (".umbra/project.toml", ".umbra/routines/**", ".umbra/profiles/**",
                ".github/workflows/**")


def umbra_invocation() -> str:
    """Cómo debe invocar Claude a umbra: el ejecutable del PATH o este intérprete."""
    exe = shutil.which("umbra")
    return "umbra" if exe else f'"{sys.executable}" -m umbra.cli.main'


def _bash(prefix: str) -> list[str]:
    return [f"Bash({prefix})", f"Bash({prefix} *)"]


def chat_limits(config: dict) -> tuple[float, Decimal]:
    """(minutos, costo máximo en USD) por mensaje del chat de una línea."""
    minutes = config.get("chat", {}).get("max_minutes", 2)
    if isinstance(minutes, bool) or not isinstance(minutes, int | float) or minutes <= 0:
        raise ValueError("[chat] max_minutes debe ser un número mayor que 0 en "
                         ".umbra/project.toml")
    return minutes, elicit.max_cost_usd(config, "chat", Decimal("0.5"))


def build_settings(config: dict, umbra: str, *, headless: bool = False,
                   allow_changes: bool = False) -> dict:
    """Sin pantalla (`headless`) no hay quién confirme: lo que pediría permiso se deniega, o se
    permite con `allow_changes`. Lo prohibido sigue denegado siempre."""
    allow, ask, deny = [], [], []
    for sub in QUERY:
        allow += _bash(f"{umbra} {sub}")
    for name, spec in config.get("commands", {}).items():
        (allow if spec.get("safe") else ask).extend(_bash(f"{umbra} exec {name}"))
    for sub in STATEFUL:
        ask += _bash(f"{umbra} {sub}")
    if headless:
        allow += ["Read", "Glob", "Grep"]
        (allow if allow_changes else deny).extend(ask)
        ask = []
    for sub in FORBIDDEN_UMBRA:
        deny += _bash(f"{umbra} {sub}")
    for cmd in FORBIDDEN_SHELL:
        deny += _bash(cmd)
    for path in POLICY_FILES:
        deny += [f"Edit({path})", f"Write({path})"]
    hook = f'"{sys.executable}" -m umbra.cli.main _hook chat-event'
    return {
        "permissions": {"allow": allow, "ask": list(dict.fromkeys(ask)), "deny": deny},
        "hooks": {"PostToolUse": [{"matcher": "Bash",
                                   "hooks": [{"type": "command", "command": hook}]}]},
    }


def build_prompt(conn, config: dict, umbra: str, *, headless: bool = False,
                 allow_changes: bool = False, extra: str = "") -> str:
    summary = status_summary(conn)
    confirm = ("Antes de un comando que cambia estado (plan, run, pause, resume, cancel, retry, "
               "spec tasks,\n  task ...), muestra el comando exacto y espera confirmación.")
    if headless:
        confirm = ("Responde en una sola respuesta y termina: nadie puede contestarte después. "
                   + ("Puedes ejecutar comandos que cambian estado (plan, run, pause, resume, "
                      "cancel, retry, spec tasks, task ...) solo si el mensaje lo pide "
                      "claramente."
                      if allow_changes else
                      "Los comandos que cambian estado (plan, run, pause, resume, cancel, "
                      "retry, spec tasks,\n  task ...) están bloqueados; si hacen falta, dile "
                      "al usuario el comando exacto para que lo ejecute él."))
    tasks = [dict(r) for r in conn.execute(
        "SELECT number, title, status FROM task ORDER BY number DESC LIMIT 30")]
    commands = ", ".join(f"`{umbra} exec {n}`" for n in config.get("commands", {})) or "ninguno"
    return f"""Eres la interfaz conversacional de umbra-engine en este repositorio.

Todo lo que haces pasa por comandos de umbra; nunca hay atajos fuera de ellos.
Invoca umbra exactamente así: `{umbra} <comando>` (añade `--json` cuando necesites leer datos).

Reglas:
- Consultas sin pedir permiso: status, explain, log, evidence, task list, doctor, spec list.
- Cuando pregunten por qué una tarea está como está, ejecuta `{umbra} explain <n>` y
  cuéntalo con tus palabras: qué pasó, por qué umbra se detuvo y qué opciones hay.
  Habla de etapas y situaciones (Construir, Revisar, «detenida»), no de códigos.
- {confirm}
- Comandos registrados del proyecto: {commands}.
- MySQL local: `{umbra} db query "SQL"` consulta sin pedir permiso (solo lectura; `--db
  nombre` elige la base). Para cambiar datos o estructura usa `{umbra} db change "SQL"`: solo
  lo propone y la persona decide si se aplica; nunca digas que un cambio ya se aplicó.
- No puedes aprobar ni rechazar ejecuciones, ni hacer push, merge o editar la política de
  `.umbra/`. Si el usuario quiere aprobar, dile que ejecute `umbra approve <n>` en su terminal.
  Igual con `spec new` y `spec resume`: abren una pantalla interactiva, que los ejecute él.

Estado actual del proyecto:
```json
{json.dumps(summary, ensure_ascii=False)}
```
Tareas recientes:
```json
{json.dumps(tasks, ensure_ascii=False)}
```
{extra}"""


def _require_claude() -> None:
    if not shutil.which("claude"):
        raise FileNotFoundError("no se encontró `claude`; instala Claude Code e inicia sesión "
                                "(el resto de umbra funciona sin él)")


def _answer_text(output: str) -> str:
    """Texto de la respuesta: el `result` del último evento result (parse_stream prefiere el
    structured_output, que aquí no se pide)."""
    text = ""
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            text = str(event.get("result") or "")
    return text


def last_session(udir: Path) -> str | None:
    """Id de la última conversación de `umbra chat MENSAJE` en este proyecto, si hay."""
    f = udir / "artifacts" / "chat" / "last-session"
    return (f.read_text(encoding="utf-8").strip() or None) if f.exists() else None


def ask(root: Path, udir: Path, conn, config: dict, message: str, *,
        allow_changes: bool = False, resume: str | None = None, extra: str = "") -> dict:
    """Una pregunta, una respuesta: `claude -p` con el mismo contexto y reglas que el chat
    (`extra` se añade a las instrucciones: Telegram cuenta ahí tus otros proyectos)."""
    _require_claude()
    max_minutes, max_cost = chat_limits(config)
    session_id = resume or str(uuid.uuid4())
    umbra = umbra_invocation()
    with tempfile.TemporaryDirectory() as tmp:  # no en artifacts/chat: lo comparte el interactivo
        prompt_file, settings_file = Path(tmp) / "system-prompt.md", Path(tmp) / "settings.json"
        prompt_file.write_text(build_prompt(conn, config, umbra, headless=True,
                                            allow_changes=allow_changes, extra=extra),
                               encoding="utf-8")
        settings_file.write_text(json.dumps(build_settings(
            config, umbra, headless=True, allow_changes=allow_changes), indent=2),
            encoding="utf-8")
        cmd = ["claude", "-p", "--output-format", "json", "--permission-mode", "dontAsk",
               "--setting-sources", "project",  # sin plugins ni hooks globales de la persona
               "--append-system-prompt-file", str(prompt_file), "--settings", str(settings_file),
               "--max-budget-usd", str(max_cost),
               *(["--resume", resume] if resume else ["--session-id", session_id])]
        started = store.now()
        proc = run_bounded(cmd, root, timeout_s=max_minutes * 60, stdin=message)
    out = {"status": "error", "answer": "", "session_id": session_id, "cost_usd": "0",
           "commands": [], "error": None}
    if proc.timed_out:
        out["error"] = f"se agotó el tiempo ({max_minutes:g} min)"
        return out
    result = parse_stream(proc.output)
    if result.cost:
        with conn:
            conn.execute(
                "INSERT INTO usage (id, agent, model, input_tokens, output_tokens, cost,"
                " invocation_id) VALUES (?, 'claude', ?, ?, ?, ?, ?)",
                (store.new_id(), result.model, result.input_tokens, result.output_tokens,
                 store.to_cost(result.cost), store.new_id()))
    out["cost_usd"] = store.to_cost(result.cost)
    out["session_id"] = result.session_id or session_id
    out["commands"] = [json.loads(r["payload"])["command"] for r in conn.execute(
        "SELECT payload FROM event WHERE type = 'chat.command'"
        " AND json_extract(payload, '$.session_id') = ? AND created_at >= ? ORDER BY id",
        (out["session_id"], started))]
    if result.ok:
        out.update(status="ok", answer=_answer_text(proc.output))
        f = udir / "artifacts" / "chat" / "last-session"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(out["session_id"], encoding="utf-8")
    elif result.error == NO_RESULT:
        out["error"] = ("claude no respondió; comprueba que `claude` funciona y que iniciaste "
                        "sesión")
    else:
        out["error"] = result.error
    if out["error"]:  # la salida cruda, para diagnosticar (umbra chat/Telegram no la muestran)
        log = udir / "artifacts" / "chat" / "last-error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(proc.output[-20000:], encoding="utf-8")
        out["error"] += f" (detalle: {log.as_posix()})"
    return out


def launch(root: Path, udir: Path, conn, config: dict) -> int:
    _require_claude()
    umbra = umbra_invocation()
    chat_dir = udir / "artifacts" / "chat"
    chat_dir.mkdir(parents=True, exist_ok=True)
    prompt_file, settings_file = chat_dir / "system-prompt.md", chat_dir / "settings.json"
    prompt_file.write_text(build_prompt(conn, config, umbra), encoding="utf-8")
    settings_file.write_text(json.dumps(build_settings(config, umbra), indent=2),
                             encoding="utf-8")
    cmd = [shutil.which("claude"), "--append-system-prompt-file", str(prompt_file),
           "--settings", str(settings_file)]
    return _run(cmd, cwd=root).returncode


_run = subprocess.run  # sustituible en pruebas
