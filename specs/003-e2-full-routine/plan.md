# Implementation Plan: E2 — Rutina completa y Codex

**Branch**: `003-e2-full-routine` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

## Summary

Adaptador `codex` (`codex exec --json -s <sandbox> --output-schema F -o F -`), perfiles por
defecto `planner`, `builder-tdd`, `reviewer-strict` (Codex) y `verifier`, rutina `feature`, motor
con retrabajo (REVIEW/VERIFY → BUILD), hallazgos persistidos y control `pause/resume/cancel/retry`.

## Research (decisiones)

| Tema | Decisión |
| --- | --- |
| Codex sin interfaz | Verificado en `codex exec --help` 0.163: `--json`, `-s read-only\|workspace-write`, `--output-schema`, `-o`, `-m`, prompt por stdin con `-` |
| Esquema para Codex | Estricto: todo campo requerido, `additionalProperties: false`, sin `default`/`title` |
| Costo de Codex | Tokens de `turn.completed`; costo `0` marcado `estimated` (el login de ChatGPT no informa importes) |
| Contexto entre etapas | El sobre gana `plan` (salida de PLAN) y `diff` (base..head, máx. 60 000 caracteres). El revisor recibe el diff y los requisitos, no el resumen del constructor |
| Retrabajo | Hallazgo con severidad ≥ `block_on` → evento `stage.rework` con la retroalimentación → vuelve a BUILD. Ciclos contados por intentos de la etapa desde el último `run.retried` |
| Orden de intentos | `now()` pasa a microsegundos para ordenar intentos y eventos del mismo segundo |
| Intersección de permisos | `[policy] actions` opcional en `project.toml`; acciones efectivas = perfil ∩ política |
| Transiciones seguras | Cambios de estado del motor con `UPDATE ... WHERE status = 'RUNNING'`; si el humano canceló o pausó, el motor no lo sobrescribe |
| Rutina por defecto | `[project] default_routine` (por defecto `feature`) |

## Constitution Check

| Principio | Cumplimiento |
| --- | --- |
| III | El motor decide el retrabajo por severidad; el agente solo reporta |
| IV | `codex` entra por el registro de adaptadores; el motor no cambia |
| V | Revisor y planificador sin `edit` → Claude sin Edit/Write, Codex `read-only` |
| VI | Hallazgos con archivo/línea en la tabla `finding` |
| VIII | `retry` crea intentos nuevos sin borrar historial |

Sin violaciones.

## Project Structure

```text
src/umbra/adapters/codex.py          nuevo
src/umbra/defaults/profiles/         planner, builder-tdd, reviewer-strict, verifier (.toml + .md)
src/umbra/defaults/routines/feature.yaml
src/umbra/routines/engine.py         plan(), check_stage(), retrabajo, transiciones seguras, cancel
src/umbra/cli/routines.py            pause, resume, cancel, retry
tests/fakes/codex.py                 nuevo
tests/acceptance/test_e2.py          nuevo
```
