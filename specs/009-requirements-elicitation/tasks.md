# Tasks: Levantamiento de requisitos dentro de umbra

**Input**: [spec.md](spec.md), [plan.md](plan.md), [data-model.md](data-model.md),
[contracts/cli.md](contracts/cli.md), [quickstart.md](quickstart.md)

> **Para `umbra plan`**: proponer **una tarea de umbra por fase** (Fase 1 … Fase 6), en este
> orden, cada una dependiente de la anterior. Cada fase es una unidad que se puede mezclar sola:
> deja `uv run pytest -q` y `uv run ruff check .` en verde. La Fase 7 la hace el responsable a
> mano (smoke test real).

Reglas para todas las fases: las pruebas no usan red ni modelos (constitution); los mensajes al
usuario van en español y en lenguaje llano; las operaciones nuevas viven en `src/umbra/service.py`
y la CLI/`watch` solo las llaman; no se añaden dependencias.

## Fase 1: Fundamentos + `umbra spec tasks` (US2, capa determinista)

**Objetivo**: crear tareas en borrador desde una spec de Spec Kit sin conversación.
**Prueba independiente**: con una spec de ejemplo de 3 historias y su `tasks.md`,
`umbra spec tasks` crea 3 tareas encadenadas; repetirlo no duplica nada.

- [ ] T001 Migración V2 en `src/umbra/unified/store.py` según [data-model.md](data-model.md): tabla `conversation`, columnas nuevas en `spec`, `task` y `usage`, índice único `task_story`; añadirla a `MIGRATIONS` sin tocar `_V1`
- [ ] T002 [P] [US2] Parser puro en `src/umbra/management/specfile.py`: `parse_stories(spec_md) -> list[Story]` (encabezados `### User Story N - Título (Priority: Pn)` y `### Historia N - Título (Prioridad: Pn)`, escenarios numerados bajo `**Acceptance Scenarios**`/`**Escenarios de aceptación**`, requisitos de la línea `**Requisitos**:` o los `FR-\d+` citados, `story_hash` = sha256 del texto de la sección) y `parse_steps(tasks_md) -> dict[str, list[str]]` (líneas `- [ ] Tnnn … [USn] …` agrupadas por historia, más las rutas citadas entre comillas invertidas)
- [ ] T003 [US2] Ampliar `insert_proposals` en `src/umbra/management/planning.py` con trazabilidad opcional por tarea (`spec_dir`, `story`, `requirements`, `story_hash`) sin cambiar el comportamiento de `umbra plan`
- [ ] T004 [US2] `service.spec_tasks(ctx, spec_dir, origin)` en `src/umbra/service.py`: guarda la spec (`save_spec` + `dir`), arma una tarea por historia (título «Historia N: …», escenarios → criterios, descripción = texto de la historia + pasos `[USn]` de `tasks.md` + «Plan técnico: <spec_dir>/plan.md», alcance = rutas citadas, prioridad P1–P3, cadena de dependencias por prioridad) e inserta todo o nada; historias ya creadas (`spec_dir`+`story`) no se duplican; sin historias → error que sugiere `umbra plan`
- [ ] T005 [US2] Comando `umbra spec tasks <ruta> [--yes] [--json]` en `src/umbra/cli/spec.py` (nuevo subcomando `spec` registrado en `src/umbra/cli/main.py`)
- [ ] T006 [US2] Copia de la spec al worktree en `src/umbra/routines/engine.py` (`process`, tras `worktree.ensure`): si la tarea tiene `spec_dir`, no existe en el worktree y sí en la carpeta de trabajo, copiarla (FR-015)
- [ ] T007 [US2] Pruebas: `tests/unit/test_specfile.py` (inglés y español, sin `**Requisitos**`, sin historias), `tests/unit/test_store_v2.py` (migración sobre una base V1 con datos), `tests/acceptance/test_spec_tasks.py` (crear, repetir sin duplicar, cadena de dependencias, todo o nada, copia al worktree incluida en el commit de la primera tarea)

## Fase 2: Motor de conversación sin pantalla (US1)

**Objetivo**: hablar con `claude` por stream-json con control de fases, probado con un `claude` falso.
**Prueba independiente**: un stream grabado recorre specify → spec_review y se registran sesión, fase y costo.

- [ ] T008 [P] [US1] `src/umbra/chat/stream.py`: arrancar `claude -p --input-format stream-json --output-format stream-json --include-partial-messages --verbose` (con `--resume`, `--settings`, `--append-system-prompt-file`, `--max-budget-usd`) usando `blocks.process.background_kwargs()` y UTF-8; `send(text)`; iterador de eventos tipados (`Init(session_id, skills)`, `TextDelta`, `ToolUse(name, target)`, `TurnEnd(total_cost, is_error, text)`); cierre limpio
- [ ] T009 [P] [US1] `src/umbra/chat/elicit.py`: fases y transiciones del diagrama de [data-model.md](data-model.md); `phase_settings(phase, script)` con la tabla de permisos de [contracts/cli.md](contracts/cli.md); `phase_message(phase, idea)`; `parse_question(text) -> (texto_sin_bloque, Question | None)`; costo del turno = acumulado − `cost_seen`, guardado en `usage` con `conversation_id`; verificación tras cada turno de que no aparecieron archivos de otra fase (se borran y se avisa)
- [ ] T010 [P] [US1] Instrucciones del asistente en `src/umbra/defaults/elicit.md`: responder en el idioma del usuario, preguntas solo con el bloque `umbra-question`, no invocar skills de otra fase, añadir `**Requisitos**: FR-…` a cada historia
- [ ] T011 [US1] `[spec] max_cost_usd` (por defecto 5) leído de `.umbra/project.toml`; al superarlo la conversación queda en pausa con un aviso
- [ ] T012 [US1] Comprobaciones previas: `claude` disponible, `.specify/` presente (si no, explicar y ofrecer `specify init --here --ai claude --script ps|sh` con confirmación; si `specify` no está instalado, explicar cómo instalarlo)
- [ ] T013 [US1] Pruebas con `tests/fakes/claude_stream.py` (reproduce un `.jsonl` grabado y anota lo recibido): `tests/unit/test_elicit.py` (settings por fase, bloque válido/ inválido, costo por diferencia, archivo de otra fase borrado) y `tests/unit/test_stream.py`

## Fase 3: Pantalla de conversación y puntos de control (US1 + US2)

**Objetivo**: `umbra spec new "idea"` de punta a punta hasta las tareas en borrador.
**Prueba independiente**: con el `claude` falso, Textual pilot recorre idea → pregunta → aprobar spec → aprobar plan → tareas creadas.

- [ ] T014 [US1] `src/umbra/cli/spec_screen.py`: pantalla Textual con historial, texto en vivo, línea de actividad («leyendo …», «escribiendo spec.md»), barra con fase y costo, entrada de texto; lectura del stream en `run_worker(thread=True)`
- [ ] T015 [US1] Preguntas como opciones (números/flechas, la recomendada primero y marcada, «Otra respuesta…» abre texto libre)
- [ ] T016 [US1] Puntos de control `spec_review` y `plan_review`: «Aprobar / Pedir cambios / Descartar» con confirmación (por defecto «No», como en `watch`); mostrar resumen de la spec o del plan; pedir cambios vuelve a la fase anterior con el comentario
- [ ] T017 [US2] Al aprobar el plan: fase `tasks` (`/speckit-tasks`) y luego `service.spec_tasks`; mostrar las tareas creadas y recordar `accept`
- [ ] T018 [US1] `umbra spec new "idea"` en `src/umbra/cli/spec.py` (exige terminal interactiva); eventos `spec.*` con origen
- [ ] T019 [US1] Pruebas `tests/acceptance/test_spec_conversation.py` con Textual pilot y `claude` falso: flujo completo, pedir cambios, descartar, error del asistente mostrado sin cerrar la pantalla

## Fase 4: Retomar y desalineación (US4)

**Objetivo**: no perder conversaciones y avisar cuando la spec cambia.
**Prueba independiente**: cerrar en `clarify`, `umbra spec resume` sigue ahí; editar una historia marca su tarea desalineada.

- [ ] T020 [US4] `umbra spec resume [NNN|ruta]`: reabre en su fase con `--resume <session_id>` y el historial guardado en `.umbra/artifacts/<conversation>.jsonl`; sin argumento, la última abierta
- [ ] T021 [US4] Una conversación por spec con el lease existente (`spec:<dir>`), renovado mientras la pantalla está abierta; la segunda pantalla explica por qué no puede abrirse
- [ ] T022 [US4] `service.misaligned(ctx, spec_dir)`: compara `story_hash` con el texto actual; `umbra spec tasks` sobre una spec con tareas muestra qué cambiaría y solo actualiza (con confirmación o `--yes`) tareas en borrador o aceptadas sin ejecución activa
- [ ] T023 [US4] Pruebas `tests/acceptance/test_spec_resume.py`: retomar, lease ocupado, desalineada, actualización confirmada y rechazada, tarea en ejecución intacta

## Fase 5: Avance por spec (US3) y acceso desde `watch` (US1)

**Objetivo**: ver «n de m historias hechas» y el costo por spec.
**Prueba independiente**: con 3 historias y una hecha, `status`, `spec list` y `watch` muestran «1 de 3» y el costo.

- [ ] T024 [US3] `service.spec_progress(ctx)`: por spec, fase de la conversación, historias hechas / total, desalineadas y costo (conversación + intentos de sus tareas, en `Decimal`)
- [ ] T025 [US3] `umbra spec list [--json]` y sección de specs en `umbra status` (`--json` incluido)
- [ ] T026 [US3] `src/umbra/unified/explain.py`: «Viene de la historia N de <spec> (FR-…)» y aviso de desalineada en lenguaje llano
- [ ] T027 [US3] `src/umbra/cli/watch.py`: avance por spec visible y tecla `s` (pide la idea; si hay una conversación abierta, ofrece retomarla) que abre `spec_screen` con origen `watch`
- [ ] T028 [US3] Pruebas `tests/acceptance/test_spec_progress.py` y ampliación de las pruebas de `watch`

## Fase 6: Integración con `umbra chat` y documentación

- [ ] T029 `src/umbra/chat/launcher.py`: `spec tasks` en `STATEFUL`, `spec list` en `QUERY`, `spec new`/`spec resume` en `FORBIDDEN_UMBRA`; pruebas de las reglas
- [ ] T030 [P] `docs/usage.md` y README: sección «De la idea a las tareas» con `spec new`, puntos de control, `spec tasks` sin conversación, `spec resume`, `spec list`
- [ ] T031 `uv run pytest -q` y `uv run ruff check .` en verde

## Fase 7: Smoke test real (manual, responsable)

- [ ] T032 Recorrer [quickstart.md](quickstart.md) sección «Manual» sobre `sandbox/` con `claude` real

## Dependencias

Fase 1 → 2 → 3 → 4 → 5 → 6 → 7. Dentro de cada fase, las tareas `[P]` tocan archivos distintos.
MVP: Fases 1–3 (idea → spec → plan → tareas).
