---

description: "Tareas de tareas que cruzan repos"
---

# Tasks: Tareas que cruzan repos

- [x] T001 Refactor sin cambio visible: `routines/parts.py` con una sola parte desde `run`, y las
  etapas del engine recorren las partes. La batería completa queda en verde.
- [x] T002 [US1] Migración `_V8` (`run_part`), historias con varios repos en `spec_tasks`,
  `parts.ensure` con un worktree por repo y BUILD, política, alcance, tests y lint por parte.
- [x] T003 [US2] SHIP con un PR por repo enlazados, huella de heads, `approve()` por parte en orden
  y con retoma, y `cancel()` de todas las partes.
- [x] T004 [US3] VERIFY con `dev` por parte, `UMBRA_URL_<REPO>` (parámetro `env` en
  `start_background`) y `[workspace] app`.
- [x] T005 [US4] Diff con el repo delante en revisión, `explain`, `watch` y Telegram. `open` abre
  la carpeta de la tarea. Tomar el control y reintentar por parte.
- [x] T006 Pruebas `tests/acceptance/test_cross_repo.py`, `docs/usage.md` y `CHANGELOG.md`.
