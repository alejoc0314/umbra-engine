# Implementation Plan: Costo de una tarea sin «tokens sin precio»

**Branch**: `011-costo-tokens-codex` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-costo-tokens-codex/spec.md`

## Summary

El costo se muestra hoy como `$0.42 + 60k tokens sin precio`; pasará a `$0.42 + 60k tokens`. Todo el
texto de costo sale de una sola función, `spend_text` (`src/umbra/unified/explain.py:344`), así que
el cambio es quitar « sin precio» de esa función. La rama «solo dólares» y la regla «nunca $0.00
si hubo tokens» no cambian, y `--json` tampoco.

## Technical Context

**Language/Version**: Python >= 3.12

**Primary Dependencies**: typer, rich, textual (sin dependencias nuevas)

**Storage**: SQLite `.umbra/umbra.db`; sin cambios de esquema ni de datos

**Testing**: pytest (`uv run pytest`), ruff (`uv run ruff check .`)

**Target Platform**: Windows y POSIX (CLI)

**Project Type**: cli

**Performance Goals**: N/A (cambio de texto)

**Constraints**: `--json` sin cambios (FR-005); nunca `$0.00` con tokens de Codex (FR-002)

**Scale/Scope**: 1 línea de código, 1 test de aceptación, 1 línea de CHANGELOG

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Cumple | Nota |
|---|---|---|
| I. Terminal primero | ✅ | Solo cambia el texto; `--json` sigue igual. |
| II. Comandos antes que conversación | ✅ | El chat lee las mismas salidas; no cambian sus permisos. |
| III. El agente propone, el motor decide | ✅ | Sin relación. |
| IV. Agentes intercambiables | ✅ | El texto no nombra a «Claude» ni a «Codex». |
| V. Toda sesión está acotada | ✅ | No toca límites de costo: solo cambia cómo se muestran. |
| VI. Evidencia o no pasó | ✅ | `evidence --raw` sigue mostrando los mismos datos con otra etiqueta. |
| VII. Humano antes de integrar | ✅ | Sin relación. |
| VIII. Reanudable e idempotente | ✅ | Sin estado nuevo. |
| IX. Aislamiento del trabajo | ✅ | Ajusta un test existente sin debilitarlo: sigue pidiendo los tokens y la ausencia de `$0.00`, y además exige que no aparezca «sin precio». |
| X. Simple hasta que duela | ✅ | Una línea en la función que ya comparten todas las pantallas. |

Re-check tras la fase 1: sin cambios, todos cumplen.

## Project Structure

### Documentation (this feature)

```text
specs/011-costo-tokens-codex/
├── plan.md              # este archivo
├── research.md          # fase 0
├── data-model.md        # fase 1 (sin entidades nuevas)
├── quickstart.md        # fase 1
├── contracts/
│   └── cost-text.md     # formato del texto de costo
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/umbra/unified/explain.py                    # spend_text: quitar « sin precio»
src/umbra/unified/store.py                      # solo docstrings (_unpriced, run_spend); opcional
tests/acceptance/test_autopilot_findings_cost.py  # aserciones al formato nuevo
CHANGELOG.md                                    # línea en «## Sin publicar»
```

Pantallas que heredan el cambio sin tocarlas (todas llaman a `spend_text`): `status`
(`explain.py:614`, `cli/unified.py:138`), avance de specs (`explain.py:360`), `evidence`/`--raw`
(`explain.py:365`), rutinas (`cli/routines.py:182,194,198`) y `watch` (`cli/watch.py:549,668`).

**Structure Decision**: Proyecto único existente; no se crean archivos de código.

## Complexity Tracking

Sin violaciones; no aplica.
