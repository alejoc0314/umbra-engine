# Implementation Plan: Crítica, direcciones y gusto

**Branch**: `027-critica-y-gusto` | **Spec**: [spec.md](spec.md)

## Summary

- **Contratos**: `Stage.critic`; `StageOutput.options: list[DesignOption(name, images)]`
  (con descripciones en el esquema JSON que ve el agente).
- **Motor** (`Engine.design`): bucle diseñador → `critique()` (perfil del crítico, intento
  `critic` de solo lectura con las pantallas en `Envelope.design`; si falla, sigue sin crítica)
  → hallazgos del diseñador + del crítico ≥ `block_on` vuelven al diseñador hasta
  `max_fix_cycles`; evento `design.critique`; `design.ready` con `pending`. Con ≥2 `options`,
  `design.options` y `BLOCKED design_choice`. `design_feedback` añade la dirección elegida y,
  si el repo nunca eligió ni aprobó un diseño, pide 2 o 3 direcciones. Los hallazgos de diseño
  viven en eventos, no en la tabla `finding` (no son trabajo para Construir).
- **Gusto** (`management/taste.py`): `~/.umbra/gusto.md`, `record(proyecto, texto)` y
  `load()` (últimos 5000 caracteres); `agent_attempt` lo suma a `project_notes` en las etapas
  `design` y `critic`. `service.design_pick|design_changes|design_approve` lo anotan.
- **Decidir**: `umbra design elegir|gusto`; Telegram: una foto o álbum por dirección, botones
  `dpick:N:i`, responder → cambios, `/gusto`; `watch`: `a` pide el número, `r` otra ronda.
  `explain`: `design_choice` y narración de `design.options|chosen|critique|critic_failed`.
- **Perfil** `design-critic` (Opus 5.5, solo lectura) con la rúbrica; `feature`: `critic`,
  `block_on: medium`, `max_fix_cycles: 2`.

## Constitution Check

III (la persona elige la dirección y aprueba; el gusto es suyo y editable) · IV (crítico y
diseñador son perfiles intercambiables) · V (cada ronda queda registrada como evento). Sin
enmienda.

## Pruebas

`tests/acceptance/test_design_quality.py`; el `claude` falso gana `critique`, `design_lint` y
`design_options`. Las pruebas de la 026 cuentan con el crítico en la rutina.
