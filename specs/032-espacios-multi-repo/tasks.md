---

description: "Tareas de espacios de trabajo con varios repos"
---

# Tasks: Espacios de trabajo con varios repos

- [x] T001 [US1] `find_workspace`, `members`, `repo_config` y `init_project` para espacios en
  `src/umbra/unified/project.py`. `projects.register`/`overview` agrupan el espacio.
- [x] T002 [US2] Migración `_V7` (`task.repos`), `Story.repos` en `specfile.py`, validación en
  `spec_tasks` e indicaciones de la conversación en `chat/elicit.py`.
- [x] T003 [US3] `repo_of` y `engine(..., run_row)` en `service.py`. El worker construye el
  engine del repo. `run`, `approve`, `cancel`, `report` y `open` pasan a usar el repo de la tarea.
- [x] T004 [US3] PRs de spec por repo en `spec_ready` y `approve_spec` en orden, con claves por
  repo y retoma tras un fallo.
- [x] T005 [US4] El repo visible en `watch_data`, `status`, `explain` y Telegram. `--repo` en
  `exec` y `task add`. `onboard` en un espacio avisa que no está soportado.
- [x] T006 Pruebas `tests/acceptance/test_workspace.py`, enmienda menor de la constitución,
  `docs/usage.md` y `CHANGELOG.md`.
