# Implementation Plan: `umbra chat` programático

**Branch**: `010-chat-programatico` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-chat-programatico/spec.md`

## Summary

`umbra chat "mensaje"` (o `umbra chat -` leyendo la entrada estándar) hace una sola pregunta a
Claude Code con el mismo prompt y las mismas reglas que la sesión interactiva, imprime la
respuesta y termina. Por dentro es `claude -p --output-format json` con límite de tiempo
(`run_bounded`) y de costo (`--max-budget-usd`), `--permission-mode dontAsk` para que nada quede
esperando una confirmación que nadie dará, y una variante de las reglas de permisos: sin
`--allow-changes` lo que pediría confirmación pasa a `deny`; con él, a `allow`. Lo prohibido sigue
en `deny`, que en Claude Code gana sobre `allow`. `--json` devuelve un objeto con respuesta,
sesión, costo y comandos ejecutados; `--continue` / `--session` retoman la conversación con
`--resume`. Sin mensaje, `umbra chat` no cambia.

## Technical Context

**Language/Version**: Python >= 3.12

**Primary Dependencies**: typer (CLI), stdlib (`subprocess`, `tempfile`, `uuid`, `json`); el
`claude` instalado por el usuario. Ninguna dependencia nueva.

**Storage**: SQLite existente: costo en `usage` (como las demás invocaciones de `claude`) y
comandos en `event` (`chat.command`, origen `chat`, ya lo escribe el hook). Última sesión del
chat programático en `.umbra/artifacts/chat/last-session`. Sin migraciones.

**Testing**: pytest con el `claude` falso de `tests/fakes/claude.py` (modo nuevo `chat`); sin
red ni modelos.

**Target Platform**: Windows y POSIX.

**Project Type**: CLI.

**Performance Goals**: umbra añade < 1 s a lo que tarde `claude` en responder.

**Constraints**: límite por mensaje de 2 min y 0,50 USD por defecto (`[chat] max_minutes`,
`[chat] max_cost_usd`); Ctrl+C no deja procesos de `claude` vivos.

**Scale/Scope**: un usuario y un repositorio; mensajes sueltos. Varios mensajes a la vez no
comparten estado salvo `last-session`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Cumple | Cómo |
|-----------|--------|------|
| I. Terminal primero | Sí | Es un comando; `--json` para quien lo lee desde un programa. |
| II. Comandos antes que conversación | Sí | Claude solo ejecuta comandos de umbra; el modo programático tiene **menos** permisos que el interactivo (sin `--allow-changes` no cambia estado, y nunca edita archivos). |
| III. El agente propone, el motor decide | Sí | Los permisos se fijan en código (`build_settings`) y los aplica Claude Code con `deny`/`allow` y `dontAsk`, no el texto del prompt. |
| IV. Agentes intercambiables | Sí | El chat ya es específico de Claude Code por constitution («la capa conversacional usa el `claude` del usuario»); el núcleo no cambia. |
| V. Toda sesión está acotada | Sí | Tiempo (`run_bounded`), costo (`--max-budget-usd`), workspace (raíz del repo) y acciones (`allow`/`deny`). |
| VI. Evidencia o no pasó | N/A | No hace avanzar etapas. |
| VII. Humano antes de integrar | Sí | `approve`, `reject`, push y merge siguen en `deny`, también con `--allow-changes`; además `approve` exige terminal interactiva y `claude -p` no la tiene. |
| VIII. Reanudable e idempotente | Sí | No crea efectos externos propios; los comandos que ejecute ya son idempotentes. |
| IX. Aislamiento | Sí | No edita archivos (sin `allow` para Edit/Write y `dontAsk`); política de `.umbra/` en `deny`. No guarda credenciales. |
| X. Simple hasta que duela | Sí | Sin dependencias; reutiliza `run_bounded`, `parse_stream`, `build_settings`, `build_prompt` y el hook. |

Re-check tras la fase 1: sin cambios, sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/010-chat-programatico/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── chat-cli.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/umbra/
├── chat/
│   ├── launcher.py      # build_settings/build_prompt con modo programático; ask()
│   ├── hook.py          # el evento chat.command guarda también session_id
│   └── elicit.py        # max_cost_usd() acepta la sección ([spec] o [chat])
├── blocks/process.py    # run_bounded: Ctrl+C mata el árbol del proceso
└── cli/chat.py          # argumento mensaje y opciones --json/--allow-changes/--continue/--session

tests/
├── fakes/claude.py      # modo `chat`: imprime un result JSON
├── unit/test_chat_oneshot.py
└── acceptance/test_e3.py  # sin cambios: el interactivo sigue igual

docs/usage.md, README.md (si lista comandos), CHANGELOG.md («Sin publicar»)
```

**Structure Decision**: todo vive en el módulo `chat` existente. `ask()` va en `launcher.py`
junto a `launch()` porque comparte prompt, settings y la búsqueda de `claude`; no hace falta un
módulo nuevo.

## Complexity Tracking

Sin violaciones que justificar.
