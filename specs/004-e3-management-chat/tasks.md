# Tasks: E3 — Management y conversación

- [ ] T001 `management/dag.py` (Kahn) + tests unitarios
- [ ] T002 Contrato `PlanOutput`; `AgentRun.output_model` en adaptadores claude-code y codex
- [ ] T003 `management/planning.py`: SpecVersion por hash, llamada al planner, inserción transaccional con validación de DAG
- [ ] T004 CLI: `umbra plan`, `task edit` (revisión), `task accept/drop`, `task deps` (+ `--remove`)
- [ ] T005 `umbra run` rechaza tareas con dependencias pendientes
- [ ] T006 `chat/launcher.py` (prompt, settings, launch) y `chat/hook.py`; CLI `chat` y `_hook`
- [ ] T007 Aceptación: plan feliz, spec repetida, ciclo, preguntas; edit con revisión vieja; deps y run bloqueado; reglas del chat; hook registra evento; chat sin claude
- [ ] T008 Smoke test real: `umbra chat` (manual, interactivo)
- [ ] T009 pytest y ruff en verde
