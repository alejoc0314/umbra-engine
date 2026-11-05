---

description: "Tareas de los cimientos de la nueva umbra watch"
---

# Tasks: Cimientos de la nueva `umbra watch`

**Input**: [spec.md](spec.md), [plan.md](plan.md)

> Esta entrega la construye el responsable en sesión (lo visual se juzga con ojos); cada fase deja
> `uv run pytest -q` y `uv run ruff check .` en verde.

## Fase 1: Datos y hora (US1, US2)

- [ ] T001 Migración V4 en `src/umbra/unified/store.py`: índices `run(task_id, created_at)` y
  `usage(attempt_id)`; función `data_version(conn)`.
- [ ] T002 `src/umbra/unified/clock.py`: `local(ts)`, `hhmm/hhmmss`, `day_label`, `duration`;
  usarlo en `cli/routines.log` y en watch.
- [ ] T003 `src/umbra/cli/watch_data.py`: `Snapshot` y `load(conn, state)` con una sola pasada de
  consultas por tabla (sin consultas por tarea), caché de explicaciones por clave, registro
  incremental, alertas.

## Fase 2: Tema y estilos (US3)

- [ ] T004 `src/umbra/cli/theme.py` (umbra, umbra-claro, variables `state-*`/`stage-*`) y
  `src/umbra/cli/watch.tcss`; `cli/explain.renderable` con colores por variable.

## Fase 3: La app (US1, US3, US4)

- [ ] T005 `src/umbra/cli/watch.py`: hilo lector exclusivo, aplicación incremental del Snapshot,
  evidencia/aprobación en worker, tema por defecto y registro de temas, lease `watch:*`.
- [ ] T006 `src/umbra/cli/spec_screen.py`: `SpecScreen(Screen)` + `SpecApp` envoltorio; watch
  abre la pantalla con `push_screen`; teclas de watch bloqueadas debajo; `escape` cierra.

## Fase 4: Avisos y agentes (US5, US6)

- [ ] T007 `blocks/notify.send(..., conn)` calla con un watch abierto; `[notify] bell`;
  `--setting-sources project` en los tres lanzadores de `claude -p`.

## Fase 5: Pruebas, docs y CHANGELOG

- [ ] T008 `tests/acceptance/test_watch_foundation.py` (guardián de rendimiento con base sembrada,
  hora local, tema por defecto y guardado, aviso único, Screen de spec, setting-sources) y dos
  instantáneas SVG; actualizar `tests/acceptance/test_spec_progress.py` al Screen.
- [ ] T009 `docs/usage.md`, `CHANGELOG.md` («Sin publicar»), `pyproject.toml` (textual>=8, dev deps).
