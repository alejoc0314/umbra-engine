# Tasks: E2 — Rutina completa y Codex

- [x] T001 `adapters/codex.py` + registro + tests unitarios (comando, esquema estricto, parseo)
- [x] T002 Perfiles por defecto: planner, builder-tdd, reviewer-strict (codex), verifier; rutina `feature.yaml`
- [x] T003 Sobre: campos `plan` y `diff`; `now()` con microsegundos
- [x] T004 Motor: PLAN, REVIEW, VERIFY, hallazgos, retrabajo, ciclos desde el último retry
- [x] T005 Motor: transiciones seguras y limpieza al cancelar
- [x] T006 Intersección perfil ∩ política (`[policy] actions`)
- [x] T007 CLI: `pause`, `resume`, `cancel`, `retry --from`; `default_routine`
- [x] T008 Fake `codex` y modos nuevos del fake `claude`
- [x] T009 Aceptación: feliz feature; retrabajo por hallazgo; bloqueo por hallazgos persistentes; plan bloqueado; salida inválida de Codex; pause/resume; cancel; retry
- [ ] T010 Smoke test real: Claude construye y Codex revisa una tarea de `sandbox/`
- [x] T011 pytest y ruff en verde
