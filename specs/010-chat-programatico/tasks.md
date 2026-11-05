---

description: "Tareas de `umbra chat` programático"
---

# Tasks: `umbra chat` programático

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/chat-cli.md](contracts/chat-cli.md),
[quickstart.md](quickstart.md)

> **Para `umbra plan`**: proponer **una tarea de umbra por fase** (Fase 1 … Fase 6), en este
> orden, cada una dependiente de la anterior. Cada fase se puede mezclar sola: deja
> `uv run pytest -q` y `uv run ruff check .` en verde. La Fase 7 la hace el responsable a mano
> (smoke test con `claude` real).

Reglas para todas las fases: las pruebas no usan red ni modelos (constitution); usan el `claude`
falso de `tests/fakes/claude.py` con el fixture `env` de `tests/acceptance/conftest.py`
(`env.umbra(...)`, modos por `FAKE_CLAUDE_MODE`; `noop` responde `"hecho"` con
`session_id: "sess-fake"` y `total_cost_usd: 0.05`, `error` responde `is_error` y sale con 1; cada
llamada queda en `claude_calls.json` con `args` y `prompt` = stdin). No hace falta un modo nuevo
en el falso. Los mensajes al usuario van en español y en lenguaje llano. Sin dependencias nuevas.
El modo interactivo (`umbra chat` sin mensaje) no cambia: las pruebas de `tests/acceptance/test_e3.py`
siguen pasando sin tocarlas.

**Nota sobre el plan**: las pruebas del chat programático van en
`tests/acceptance/test_chat_oneshot.py` (no en `tests/unit/`), y el falso no necesita el modo
`chat` que menciona [plan.md](plan.md): bastan `noop` y `error`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (otro archivo, sin depender de tareas pendientes)
- **[Story]**: historia de [spec.md](spec.md): US1 preguntar en una línea, US2 salida JSON, US3
  seguir la conversación, US4 cambios de estado sin nadie delante

---

## Fase 1: Fundamentos (bloquea todas las historias)

**Objetivo**: límites, Ctrl+C y reglas de permisos del modo programático listas antes de que
exista el comando, para que el MVP nunca pueda cambiar estado por accidente.

- [ ] T001 [P] En `run_bounded` de `src/umbra/blocks/process.py`, envolver `proc.communicate(...)` para que un `KeyboardInterrupt` llame a `kill_tree(proc.pid)` y vuelva a lanzar la excepción (research R8: `background_kwargs()` aísla el grupo y Ctrl+C no le llega al hijo)
- [ ] T002 [P] Prueba en `tests/unit/test_process.py`: con `subprocess.Popen` sustituido por un doble cuyo `communicate` lanza `KeyboardInterrupt`, `run_bounded` llama a `kill_tree` con su pid y propaga la excepción
- [ ] T003 [P] Generalizar `max_cost_usd` en `src/umbra/chat/elicit.py` a `max_cost_usd(config, section="spec", default=DEFAULT_MAX_COST)`; el mensaje de error nombra la sección (`[chat] max_cost_usd debe ser un número mayor que 0 en .umbra/project.toml`). Los llamadores actuales no cambian
- [ ] T004 En `src/umbra/chat/launcher.py`, `chat_limits(config) -> tuple[float, Decimal]`: `[chat] max_minutes` (número > 0, por defecto 2; booleano, no numérico o ≤ 0 → `ValueError` «[chat] max_minutes debe ser un número mayor que 0 en .umbra/project.toml») y `[chat] max_cost_usd` vía `elicit.max_cost_usd(config, "chat", Decimal("0.5"))`
- [ ] T005 En `src/umbra/chat/launcher.py`, `build_settings(config, umbra, headless=False, allow_changes=False)`: con `headless=False` el resultado es idéntico al actual. Con `headless=True`, todo lo que iría a `ask` (STATEFUL y `exec` no `safe`) va a `allow` si `allow_changes`, si no a `deny`; `ask` queda vacío; se añaden `Read`, `Glob`, `Grep` a `allow`; FORBIDDEN_UMBRA, FORBIDDEN_SHELL y POLICY_FILES siguen en `deny` en ambos casos; el hook `PostToolUse` se mantiene (research R2)
- [ ] T006 En `src/umbra/chat/launcher.py`, `build_prompt(conn, config, umbra, headless=False, allow_changes=False)`: con `headless=False` el texto es idéntico al actual. Con `headless=True` la regla «Antes de un comando que cambia estado… espera confirmación» se sustituye por: sin `allow_changes`, «Nadie puede confirmar en esta conversación: no ejecutes comandos que cambian estado; responde con el comando exacto para que el usuario lo ejecute»; con `allow_changes`, «Puedes ejecutar los comandos que cambian estado sin pedir confirmación; di cuáles ejecutaste». Añadir en ambos: «Responde en una sola respuesta y termina; no hagas preguntas de seguimiento»
- [ ] T007 Pruebas en `tests/acceptance/test_chat_oneshot.py`: `build_settings(..., headless=True)` deja `Bash(umbra run *)` en `deny` y con `allow_changes=True` en `allow`; `Bash(umbra approve *)`, `Bash(git push *)` y `Edit(.umbra/project.toml)` en `deny` en ambos; `ask` vacío; `headless=False` igual que antes. `chat_limits` con valores por defecto, con `max_minutes = 0` y con `max_cost_usd = true` (errores)

**Checkpoint**: reglas y límites listos; nada visible para el usuario todavía.

---

## Fase 2: User Story 1 — Preguntar en una línea (Priority: P1) 🎯 MVP

**Objetivo**: `umbra chat "mensaje"` / `umbra chat -` responde y termina.
**Prueba independiente**: con el falso en `noop`, `umbra chat "¿qué tareas hay?"` imprime
`hecho` y sale con 0; `umbra chat` sin mensaje sigue lanzando la sesión interactiva.

- [ ] T008 [US1] `ask(root, udir, conn, config, message, *, allow_changes=False, resume=None) -> dict` en `src/umbra/chat/launcher.py`: sin `claude` en el PATH → `FileNotFoundError` con el mismo texto que `launch`; `chat_limits(config)`; `session_id = resume or str(uuid.uuid4())`; en un `tempfile.TemporaryDirectory()` escribe `system-prompt.md` (`build_prompt(..., headless=True, allow_changes=...)`) y `settings.json` (`build_settings(..., headless=True, allow_changes=...)`) (research R3: nunca en `.umbra/artifacts/chat/`, que comparte el interactivo); comando `["claude", "-p", "--output-format", "json", "--permission-mode", "dontAsk", "--append-system-prompt-file", prompt, "--settings", settings, "--max-budget-usd", str(max_cost)]` más `--resume <id>` si hay `resume`, si no `--session-id <id>`; `run_bounded(cmd, root, timeout_s=max_minutes * 60, stdin=message)`; resultado con `adapters.claude_code.parse_stream(proc.output)`. Devuelve el dict de [data-model.md](data-model.md) (`status`, `answer`, `session_id`, `cost_usd` como texto decimal, `commands` = `[]` por ahora, `error`): tiempo agotado → `error` «se agotó el tiempo (N min)»; `ok=False` → `error` = texto de `claude`; sin resultado → «claude no respondió; comprueba que `claude` funciona y que iniciaste sesión» (research R9). `session_id` = el del resultado si lo trae, si no el generado
- [ ] T009 [US1] En `ask` (`src/umbra/chat/launcher.py`), registrar el costo cuando `parse_stream` lo traiga: una fila en `usage` con `id` y `invocation_id` nuevos (`store.new_id()`), `agent='claude'`, `model`, `input_tokens`, `output_tokens` y `cost` (`store.to_cost`); `attempt_id` y `conversation_id` nulos (research R7)
- [ ] T010 [US1] En `src/umbra/cli/chat.py`, `chat(message: str | None = typer.Argument(None, help=...))`: sin mensaje → `launcher.launch` como hoy; `-` → `sys.stdin.read()`; mensaje tras `strip()` vacío → `fail("el mensaje está vacío", code=2)`; `ValueError` de `chat_limits` → código 2; `FileNotFoundError` → código 2. Con mensaje: imprime `answer` en stdout con `typer.echo` (sin rich ni colores), errores en stderr, código 0 si `status == "ok"` y 1 si no
- [ ] T011 [US1] Pruebas en `tests/acceptance/test_chat_oneshot.py`: (a) `noop` → stdout `hecho`, código 0, la llamada del falso tiene `-p`, `--permission-mode dontAsk`, `--max-budget-usd 0.5`, `--session-id` y `prompt == "¿qué tareas hay?"`; (b) `env.umbra("chat", "-", input="hola")` → igual, con `prompt == "hola"`; (c) mensaje `"   "` → código 2 sin llamar al falso; (d) `error` → código 1 y `boom` en stderr; (e) sin `claude` (`launcher.shutil.which` → `None`) → código 2; (f) una fila nueva en `usage` con `cost` `0.05`; (g) `[chat] max_cost_usd = 0` → código 2; (h) settings y prompt NO se escriben en `.umbra/artifacts/chat/`

**Checkpoint**: MVP: preguntas de consulta desde la terminal, sin cambios de estado posibles.

---

## Fase 3: User Story 2 — Salida JSON (Priority: P2)

**Objetivo**: `--json` devuelve un único objeto con respuesta, sesión, costo y comandos
ejecutados, también en error.
**Prueba independiente**: `umbra chat "hola" --json` → `json.loads(stdout)` tiene las seis
claves; con `error`, `status == "error"` y código 1.

- [ ] T012 [P] [US2] En `record` de `src/umbra/chat/hook.py`, añadir `session_id=payload.get("session_id")` al payload del evento `chat.command` (research R5); el resto igual
- [ ] T013 [US2] En `ask` (`src/umbra/chat/launcher.py`), guardar `started = store.now()` antes de lanzar `claude` y, al terminar, llenar `commands` con `json.loads(payload)["command"]` de los eventos `type = 'chat.command'` con `json_extract(payload, '$.session_id') = session_id` y `created_at >= started`, en orden de `id`
- [ ] T014 [US2] En `src/umbra/cli/chat.py`, opción `--json`: con mensaje, imprime el dict de `ask` con `json.dumps(..., ensure_ascii=False)` y nada más en stdout; los errores propios del chat (mensaje vacío, configuración `[chat]`, `claude` no instalado) salen como el mismo objeto con `status: "error"`, `answer`/`session_id` nulos, `cost_usd: "0"`, `commands: []`; los errores anteriores (fuera de un proyecto) siguen con `context.load(as_json=True)`. Códigos de salida según [contracts/chat-cli.md](contracts/chat-cli.md)
- [ ] T015 [US2] Pruebas en `tests/acceptance/test_chat_oneshot.py`: `--json` con `noop` → objeto con `status: "ok"`, `answer: "hecho"`, `cost_usd: "0.05"` (o su forma decimal), `commands: []`; con `error` → `status: "error"`, `error: "boom"`, código 1; mensaje vacío con `--json` → JSON y código 2; el hook con `session_id` guarda la clave (ampliar `test_hook_records_chat_event` en `tests/acceptance/test_e3.py` o probarlo aquí); `commands` solo incluye eventos insertados con el `session_id` de la llamada, no los de otra sesión

**Checkpoint**: usable desde scripts y desde otra sesión de Claude Code.

---

## Fase 4: User Story 4 — Cambios de estado sin nadie delante (Priority: P2)

**Objetivo**: sin `--allow-changes` Claude no puede cambiar estado; con él sí; lo prohibido nunca.
**Prueba independiente**: el `settings.json` y el prompt que recibe el falso cambian según
`--allow-changes`, y `approve` está en `deny` en los dos casos.

- [ ] T016 [US4] En `src/umbra/cli/chat.py`, opción `--allow-changes` que pasa `allow_changes=True` a `ask`
- [ ] T017 [US4] Pruebas en `tests/acceptance/test_chat_oneshot.py`: capturar el `settings.json` y el prompt que recibe el falso (leer los archivos de `--settings` y `--append-system-prompt-file` desde un `run_bounded` sustituido con `monkeypatch`, antes de que se borre el directorio temporal): sin la opción, `Bash(umbra run *)` en `deny` y el prompt dice que nadie puede confirmar; con ella, en `allow` y el prompt permite ejecutar; `Bash(umbra approve *)` en `deny` en ambos

**Checkpoint**: frontera de seguridad del modo programático cubierta por pruebas.

---

## Fase 5: User Story 3 — Seguir la misma conversación (Priority: P3)

**Objetivo**: `--continue` y `--session <id>` retoman la conversación.
**Prueba independiente**: dos llamadas seguidas, la segunda con `--continue`, y la segunda
llamada al falso lleva `--resume sess-fake`.

- [ ] T018 [US3] En `ask` (`src/umbra/chat/launcher.py`), si `status == "ok"`, escribir el `session_id` en `.umbra/artifacts/chat/last-session` (crear la carpeta si falta); función `last_session(udir) -> str | None` que lo lee
- [ ] T019 [US3] En `src/umbra/cli/chat.py`, opciones `--continue` y `--session ID`: juntas → código 2 («usa --continue o --session, no las dos»); `--continue` → `resume = launcher.last_session(ctx.udir)` y, si no hay, aviso por stderr «no hay conversación anterior; empiezo una nueva»; `--session` → `resume = ID`. `--json`, `--allow-changes`, `--continue` o `--session` sin mensaje → código 2 («estas opciones necesitan un mensaje»)
- [ ] T020 [US3] Pruebas en `tests/acceptance/test_chat_oneshot.py`: llamada y luego `--continue` → la segunda llamada al falso tiene `--resume sess-fake` y no `--session-id`; `--continue` sin anterior → aviso en stderr y `--session-id`; `--session abc` → `--resume abc`; `--continue --session x` → código 2; `--json` sin mensaje → código 2; una llamada con `error` no sobrescribe `last-session`

**Checkpoint**: las cuatro historias funcionan solas.

---

## Fase 6: Documentación y CHANGELOG

- [ ] T021 [P] En `docs/usage.md`, sección de `umbra chat` (apartado 6): añadir el modo programático con tres ejemplos (pregunta en la terminal, `--json` en un script, pedirlo desde otra sesión de Claude Code), qué hace `--allow-changes`, qué sigue prohibido, `--continue`/`--session` y los límites `[chat] max_minutes` / `max_cost_usd` (FR-012)
- [ ] T022 [P] En `CHANGELOG.md`, al final de `## Sin publicar`, una línea en el estilo de las anteriores: `umbra chat "pregunta"` responde y termina, con `--json` para scripts y otros agentes, `--continue` para seguir; solo cambia estado con `--allow-changes`. Sin tocar `__version__` (AGENTS.md)
- [ ] T023 `uv run pytest -q` y `uv run ruff check .` en verde

---

## Fase 7: Smoke test manual (responsable, `claude` real)

- [ ] T024 Recorrer la sección «Manual» de [quickstart.md](quickstart.md) sobre `sandbox/` o este repo, incluido Ctrl+C a mitad de respuesta (sin procesos `claude` vivos) y que `--permission-mode dontAsk` deja leer archivos (`Read`/`Grep`) sin pedir permiso

---

## Dependencies & Execution Order

- Fase 1 → Fase 2 (US1) → Fase 3 (US2) → Fase 4 (US4) → Fase 5 (US3) → Fase 6 → Fase 7.
- US2, US3 y US4 dependen solo de US1 (todas tocan `ask` y `src/umbra/cli/chat.py`, por eso
  van en serie y no en paralelo).
- Dentro de una fase, las pruebas van al final porque prueban el código de esa fase; todas
  viven en `tests/acceptance/test_chat_oneshot.py` salvo T002.

## Parallel Opportunities

- Fase 1: T001+T002 (`process.py`), T003 (`elicit.py`) y T005/T006 (`launcher.py`) tocan
  archivos distintos; T004 espera a T003.
- Fase 3: T012 (`hook.py`) en paralelo con T013/T014.
- Fase 6: T021 y T022 en paralelo.

## Implementation Strategy

- **MVP = Fase 1 + Fase 2**: preguntas de consulta en una línea, ya con las reglas de solo
  lectura por defecto. Se puede publicar sola.
- Luego US2 (JSON, lo que hace el modo realmente programático), US4 (abre los cambios de estado
  con permiso explícito) y US3 (continuar).
