# Implementation Plan: Levantamiento de requisitos dentro de umbra

**Branch**: `feat/requirements-elicitation` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

## Summary

Dos capas, como pide la constitution (II):

1. **Capa determinista (comando)**: `umbra spec tasks specs/NNN-*` lee `spec.md` y `tasks.md`
   de Spec Kit y crea una tarea en borrador por historia de usuario, con trazabilidad a la
   historia y a sus FR. Funciona sin modelo: sirve también para specs hechas con Spec Kit fuera
   de umbra.
2. **Capa conversacional (opcional)**: `umbra spec new "idea"` / `umbra spec resume` / tecla `s`
   en `watch` abren una pantalla Textual que conversa con `claude -p` en stream-json. umbra lanza
   cada fase de Spec Kit, limita qué puede escribir el asistente en cada una, muestra las
   preguntas como opciones y se detiene en los puntos de control. Al aprobar el plan llama a la
   capa 1.

Además: avance y costo por spec en `status`/`watch`/`explain`, detección de tareas desalineadas
y la copia de la carpeta de la spec al worktree de la primera tarea para que viaje en su PR.

## Technical Context

**Language/Version**: Python ≥ 3.12
**Primary Dependencies**: typer, rich, pydantic v2, textual (ya instaladas); `claude` del usuario
**Storage**: SQLite `.umbra/umbra.db`, migración V2 (ver [data-model.md](data-model.md))
**Testing**: pytest; `claude` falso que reproduce un stream-json grabado (sin red ni modelos)
**Target Platform**: Windows y POSIX
**Project Type**: CLI/TUI de un solo paquete (`src/umbra`)
**Performance Goals**: actividad visible < 2 s tras enviar (SC-003)
**Constraints**: el asistente solo escribe en `specs/` y `.specify/feature.json`; costo acotado
**Scale/Scope**: una conversación activa por spec; specs de 1–10 historias

## Research (decisiones)

| Tema | Decisión | Alternativa descartada |
| --- | --- | --- |
| Proceso del asistente | `claude -p --input-format stream-json --output-format stream-json --include-partial-messages --verbose` en la raíz del repo; un proceso por fase, todos con `--resume <session_id>` salvo el primero | Un único proceso para todo: no permite cambiar permisos entre fases |
| Control de fases | Cada fase arranca un proceso con `--settings` propios: solo puede escribir los archivos de esa fase (tabla en [contracts/cli.md](contracts/cli.md)). Aunque el modelo intente encadenar `/speckit-plan`, no puede escribir `plan.md` fuera de la fase plan. Tras cada turno umbra verifica que no aparecieron archivos de otra fase (si aparecen, los borra y avisa) | Confiar en instrucciones: el spike mostró que el modelo encadena fases solo |
| Mensaje de fase | umbra envía el texto exacto `/speckit-specify <idea>`, `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks` (el spike confirmó que las skills se invocan así) | Que el modelo decida qué skill usar |
| Instrucciones | `--append-system-prompt-file` con `defaults/elicit.md`: idioma del usuario, preguntas como bloque `umbra-question`, nunca avanzar de fase, añadir a cada historia una línea `**Requisitos**: FR-…` | Plantillas propias de spec (lo descarta la decisión 1) |
| Preguntas | Bloque ```` ```umbra-question {"question","options","recommended"} ```` al final del mensaje; umbra lo quita del texto y lo pinta como opciones + «otra respuesta». JSON inválido → se muestra como texto normal | Parsear preguntas en prosa |
| Scripts de Spec Kit | Se permite `Bash`/`PowerShell` solo sobre `.specify/scripts/**` según `script` de `.specify/init-options.json` (el spike falló por esto) | Bash libre |
| Costo | `total_cost_usd` es acumulado por sesión: costo del turno = diferencia; se guarda en `usage` con `conversation_id`. Límite `[spec] max_cost_usd` (por defecto 5) en `project.toml`; se pasa el restante como `--max-budget-usd` y al superarlo se pausa y se pregunta | Sin límite (viola V) |
| Lectura del stream | Hilo lector (`run_worker(thread=True)`) que publica mensajes Textual; UTF-8 explícito; proceso con `blocks.process.background_kwargs()` (sin ventanas en Windows) | asyncio subprocess: Windows + Textual da problemas con el bucle |
| Actividad | Eventos `tool_use` → línea «leyendo X», «escribiendo spec.md»; `stream_event` parcial → texto en vivo; fase y costo en la barra inferior | Solo texto (primer turno tarda hasta 40 s) |
| Historias | Parser de `spec.md`: encabezados `### User Story N - Título (Priority: Pn)` y `### Historia N - … (Prioridad: Pn)`; escenarios = lista numerada bajo `**Acceptance Scenarios**`/`**Escenarios de aceptación**`; FR = línea `**Requisitos**:` o, si falta, los `FR-\d+` citados en la historia | Pedírselo a un agente (no determinista) |
| Contexto del constructor | Descripción de la tarea = texto de la historia + la fase de `tasks.md` de esa historia (`[USn]`) + «Plan técnico: specs/NNN/plan.md». Alcance = rutas citadas en esa fase | Copiar el plan entero en cada tarea |
| Dependencias | Cadena por prioridad (P1 ← P2 ← P3…): umbra ejecuta una tarea a la vez por repo y así la spec ya está en `main` cuando arranca la segunda. Editable con `umbra task deps` | Leer «Dependencies» de `tasks.md` (texto libre, poco fiable) |
| Spec en el PR (FR-015) | Tarea guarda `spec_dir`. Al crear el worktree, si `spec_dir` no existe en la base y sí en la carpeta de trabajo, umbra lo copia; `commit_all` lo incluye en el primer commit | PR solo de spec (descartado por el usuario) |
| Desalineación | Cada tarea guarda el hash del texto de su historia; `status`/`watch`/`spec tasks` lo recalculan desde el archivo. Distinto → «desalineada». `umbra spec tasks` de nuevo muestra qué cambiaría y pide confirmación; solo toca tareas en borrador o aceptadas sin ejecución activa | Vigilar archivos en segundo plano |
| Una conversación por spec | Lease existente con nombre `spec:<dir>` y renovación mientras la pantalla está abierta | Archivo lock propio |
| Spec Kit ausente | Sin `.specify/` → explicar y ofrecer `specify init --here --ai claude --script ps\|sh`; sin `specify` instalado → explicar cómo instalarlo; nada sin confirmación | Instalarlo solo |
| `umbra chat` | `spec tasks` pasa a la lista con confirmación; `spec new`/`spec resume` prohibidos (son pantallas interactivas) | — |

## Constitution Check

| Principio | Cumplimiento |
| --- | --- |
| I. Terminal primero | Todo es CLI/TUI; `spec list` y `spec tasks` aceptan `--json` |
| II. Comandos antes que conversación | La creación de tareas es un comando determinista (`spec tasks`) que funciona sin modelo. **Excepción**: la conversación de requisitos consume IA fuera de una tarea (ver Complexity Tracking) |
| III. El agente propone, el motor decide | umbra lanza las fases, decide las transiciones y los puntos de control son humanos; el asistente no crea tareas: lo hace el parser |
| IV. Agentes intercambiables | La conversación usa `claude` directamente (no un adaptador). Aceptado: es la capa conversacional, igual que `umbra chat`; no entra en rutinas |
| V. Sesión acotada | Límite de costo, workspace = repo, escritura limitada por fase, lease por spec |
| VI. Evidencia | No aplica a la conversación; las tareas creadas siguen la rutina normal |
| VII. Humano antes de integrar | Sin cambios: la spec llega a `main` dentro del PR de la primera tarea, aprobado con `umbra approve` |
| VIII. Reanudable | `session_id` y fase guardados; `spec resume` retoma; `spec tasks` es todo o nada e idempotente por historia |
| IX. Aislamiento | El asistente escribe en la carpeta de trabajo, no en worktrees; solo `specs/` y `.specify/feature.json`. Las tareas siguen en su worktree |
| X. Simple | Sin dependencias nuevas; se reutilizan lease, `insert_proposals`, `process`, Textual |

**Enmienda (MINOR → 1.1.0, incluida en el PR de arranque)**: la constitution dice que la capa conversacional usa el
`claude` *interactivo* y que Textual es *solo para la vista en vivo*. Se propone añadir: «La
conversación de requisitos puede usar `claude -p` en stream-json con el login del usuario y
Textual para su pantalla; consume IA fuera de una tarea pero es opcional: todo su resultado se
puede producir con Spec Kit y `umbra spec tasks`». Va en el PR de arranque (ver abajo), no en
una tarea de umbra: `.specify/` es ruta protegida.

## Project Structure

```text
specs/009-requirements-elicitation/
├── spec.md · plan.md · data-model.md · quickstart.md
├── contracts/cli.md
└── tasks.md

src/umbra/
├── management/specfile.py        NUEVO  parser de spec.md/tasks.md → historias (puro)
├── management/planning.py        insert_proposals acepta trazabilidad (historia, FR, hash, spec_dir)
├── chat/stream.py                NUEVO  proceso claude stream-json: enviar, leer, eventos tipados
├── chat/elicit.py                NUEVO  fases, settings por fase, bloque umbra-question, costo
├── chat/launcher.py              reglas de `umbra chat` para los comandos nuevos
├── defaults/elicit.md            NUEVO  instrucciones del asistente de requisitos
├── cli/spec.py                   NUEVO  `umbra spec new|resume|tasks|list`
├── cli/spec_screen.py            NUEVO  pantalla Textual de la conversación
├── cli/watch.py                  tecla `s`, avance por spec
├── service.py                    spec_tasks(), spec_progress()
├── routines/engine.py            copiar spec_dir al worktree si falta
├── unified/store.py              migración V2
└── unified/explain.py            «viene de la historia N (FR-…)», desalineada

tests/unit/        test_specfile, test_elicit (settings, preguntas, costo), test_store_v2
tests/acceptance/  spec tasks end-to-end; conversación con claude falso; watch `s`; copia al worktree
tests/fakes/       claude_stream (reproduce un .jsonl grabado)
```

## Orden de construcción (para el desglose)

1. Migración V2 + parser + `umbra spec tasks`/`spec list` (historia 2 sin conversación, 3 parcial).
2. Copia de `spec_dir` al worktree (FR-015).
3. `chat/stream.py` + `chat/elicit.py` con claude falso.
4. Pantalla Textual + `spec new` (historia 1) + puntos de control → `spec tasks` (historia 2).
5. `spec resume`, lease, desalineación (historia 4).
6. `status`/`watch`/`explain` por spec (historia 3) y tecla `s`.
7. Reglas de `umbra chat`, `docs/usage.md`, smoke test real sobre `sandbox/`.

## Arranque (cómo construimos esto con umbra)

La umbra de hoy no copia la spec al worktree (eso es justo lo que se construye), así que los
agentes no verían `specs/009-*` si no está en `main`. Por eso primero va un **PR de arranque**
solo con `specs/009-requirements-elicitation/` y la enmienda de la constitution; tras
mezclarlo, `umbra plan specs/009-requirements-elicitation/tasks.md` propone las tareas.

## Complexity Tracking

| Excepción | Por qué | Alternativa más simple descartada |
| --- | --- | --- |
| IA fuera de una tarea (II) | Es la funcionalidad pedida: levantar requisitos conversando | Solo `spec tasks` sin conversación: obliga a salir a Claude Code, que es lo que el usuario no quiere |
| Textual fuera de la vista en vivo | La conversación necesita opciones por teclado y actividad en vivo | Prompt de Rich línea a línea: sin actividad concurrente mientras el modelo trabaja |
| `claude` directo sin adaptador (IV) | Capa conversacional, no etapa de rutina; mismo criterio que `umbra chat` | Ampliar el contrato de adaptadores a conversaciones multi-turno: complejidad sin segundo caso real |
