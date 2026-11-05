# Implementation Plan: La constitución en el ciclo y specs retroactivas

**Branch**: `030-constitucion-en-el-ciclo` | **Spec**: [spec.md](spec.md)

## Summary

- `memory.project_notes`: antepone la constitución (`.specify/memory/constitution.md`, 8000
  caracteres) y añade `specs/000-linea-base/linea-base.md` (3000); `CONTEXT_CHARS` sube a 12000
  (el onboarding amplía el mapa).
- Instrucciones: `reviewer-strict.md` (MUST incumplido = `high`, `rule` = el principio),
  `arbiter.md`, `planner.md`, `builder.md` y `builder-tdd.md`.
- `elicit.phase_message(..., root)`: en `specify`, si existe `specs/000-linea-base/`, añade la
  petición de «## Cómo funciona hoy»; los llamadores pasan la raíz.
- `management/constitution.py`: `show`, `amend` (agente `onboarder` en modo «Enmendar la
  constitución», solo ese archivo; lo demás se restaura), `pending`, `accept` (commit),
  `discard` (checkout). CLI `umbra constitucion ver|enmendar [-y]`; bridge `/constitucion`
  (documento), `/enmendar` (trabajo aparte + botones `ce:approve|discard`).

## Constitution Check

III (el agente redacta la enmienda; la persona decide) · VI (la línea base es evidencia que
llega a los agentes). Sin enmienda de la constitución de umbra.

## Pruebas

`tests/acceptance/test_constitution.py`: sobre con constitución y línea base, mensaje de spec
retroactiva, enmienda por la terminal (aprobar y descartar), redactor que se pasa de la raya, sin
constitución, y por Telegram.
