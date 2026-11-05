# Implementation Plan: E0 — Esqueleto, store y diagnóstico

**Branch**: `001-e0-skeleton` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-e0-skeleton/spec.md`

## Summary

Paquete Python `umbra-engine` con el ejecutable `umbra` (Typer). E0 entrega `doctor` (diagnóstico
de git, gh, claude y codex mediante sus comandos de versión y de estado de sesión), `init`
(detección de stack y escritura de `.umbra/`), `status` y el almacén SQLite con todas las tablas
del diseño, migrable por `PRAGMA user_version`.

## Technical Context

**Language/Version**: Python >= 3.12 (desarrollo en 3.13)
**Primary Dependencies**: typer, rich, pydantic v2, pyyaml
**Storage**: SQLite (WAL) en `<repo>/.umbra/umbra.db`; TOML para configuración
**Testing**: pytest; ruff para lint
**Target Platform**: Windows 11 y POSIX (Linux/macOS)
**Project Type**: CLI de un solo paquete (layout `src/`)
**Performance Goals**: `umbra doctor` < 10 s; cada sonda con timeout de 8 s
**Constraints**: sin red propia, sin servidor; todos los comandos con `--json`
**Scale/Scope**: un usuario, un repo por invocación

## Constitution Check

| Principio | Cumplimiento en E0 |
| --- | --- |
| I. Terminal primero | Todo es CLI; `--json` en doctor y status |
| II. Comandos antes que conversación | Sin chat en E0 |
| III. El agente propone, el motor decide | Sin agentes en E0 |
| IV. Agentes intercambiables | doctor sondea agentes desde una tabla de datos, no lógica por agente |
| V. Sesión acotada | N/A (sin bloques) |
| VI. Evidencia | Tablas `artifact` con `tested_sha` creadas |
| VII. Humano antes de integrar | Tabla `approval` ligada a `head_sha` |
| VIII. Reanudable e idempotente | `init` idempotente; UNIQUE en `operation_key`, `idempotency_key` |
| IX. Aislamiento | `.gitignore` excluye db, artefactos y worktrees |
| X. Simple | stdlib `sqlite3`, `tomllib`, `subprocess`; sin ORM |

Resultado: sin violaciones. Post-diseño: sin cambios.

## Project Structure

### Documentation (this feature)

```text
specs/001-e0-skeleton/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/cli.md
└── tasks.md
```

### Source Code (repository root)

```text
pyproject.toml
src/umbra/
├── __init__.py            # __version__
├── cli/
│   ├── main.py            # app Typer raíz; registra comandos
│   └── unified.py         # init, doctor, status
├── unified/
│   ├── store.py           # conexión, migraciones, esquema
│   ├── project.py         # localizar raíz git, detectar stack, escribir .umbra/
│   ├── doctor.py          # sondas de herramientas
│   └── output.py          # salida rich / --json
tests/
├── conftest.py            # fixture repo git temporal
├── unit/test_store.py
├── unit/test_project.py
└── unit/test_doctor.py
```

**Structure Decision**: un solo paquete en `src/umbra/` organizado por las letras UMBRA, como fija
el diseño. Las carpetas `management/`, `routines/`, `blocks/`, `actions/`, `adapters/`, `chat/` y
`contracts/` se crean en la entrega que las usa (principio X).

## Complexity Tracking

Sin desviaciones.
