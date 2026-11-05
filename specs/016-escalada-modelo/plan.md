# Implementation Plan: Escalada automática de modelo

**Branch**: `016-escalada-modelo` | **Spec**: [spec.md](spec.md)

## Summary

`Stage.escalation: list[str]` y `Stage.arbiter: str | None` en `contracts/routine.py`;
`Profile.effort` → `claude --effort`. `Engine.build` recorre los perfiles por tramos (evento
`stage.escalated`, contador `escalation_level` desde el último `run.retried`); `Engine.judge`,
al agotar ciclos, llama a `arbitrate` (intento de etapa `arbiter`, solo lectura, hallazgos en
el sobre) o escala Construir vía `stage.escalated` + `stage.rework`. Perfiles nuevos:
`builder-strong` (Fable 5.1, `xhigh`, 8 USD, 30 min) y `arbiter` (Opus 5.5, solo lectura).
Rutinas por defecto con escalada; `feature` con árbitro. `explain.narrate` cuenta ambos.

## Constitution Check

III (el motor decide cuándo escalar; el árbitro solo propone hallazgos) · V (cada perfil con
sus límites) · VI (nada avanza sin tests) · X (sin dependencias). Sin enmienda.

## Pruebas

`tests/acceptance/test_escalation.py` con los agentes falsos; `test_e1`/`test_e2` ajustados al
nuevo número de intentos; las pruebas de «hallazgos persistentes» usan una rutina de proyecto
sin árbitro ni escalada para conservar su significado.
