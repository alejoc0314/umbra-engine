# Tasks: E0 — Esqueleto, store y diagnóstico

**Input**: plan.md, data-model.md, contracts/cli.md

## Phase 1: Setup

- [x] T001 Crear `pyproject.toml` (hatchling, deps, script `umbra`, ruff, pytest) y `.gitattributes`
- [x] T002 Crear `src/umbra/__init__.py` y `src/umbra/cli/main.py` con app Typer y `--version`

## Phase 2: Foundational

- [x] T003 [P] `src/umbra/unified/store.py`: `open_store(root)`, WAL, FK, migración v1 (data-model.md)
- [x] T004 [P] `src/umbra/unified/output.py`: `emit(data, as_json, render)` y helper de error con exit code
- [x] T005 `tests/conftest.py`: fixture `git_repo(tmp_path)` con `git init`

## Phase 3: User Story 1 — doctor (P1)

- [x] T006 [US1] `tests/unit/test_doctor.py`: herramienta ausente, versión, sesión true/false/None, regla "≥1 agente"
- [x] T007 [US1] `src/umbra/unified/doctor.py`: tabla `PROBES`, `run_probe`, `diagnose() -> dict`
- [x] T008 [US1] Comando `umbra doctor [--json]` en `src/umbra/cli/unified.py`

## Phase 4: User Story 2 — init (P1)

- [x] T009 [US2] `tests/unit/test_project.py`: detección de stack, idempotencia, no-git, subdirectorio, gitignore
- [x] T010 [US2] `src/umbra/unified/project.py`: `find_root`, `detect_stack`, `init_project`, `load_project`
- [x] T011 [US2] Comando `umbra init [--json]`

## Phase 5: User Story 3 — status (P2)

- [x] T012 [US3] `tests/unit/test_store.py`: migración, UNIQUE de task/run/attempt/operation/usage, costo decimal
- [x] T013 [US3] `status_summary(conn)` en store y comando `umbra status [--json]`

## Phase 6: Polish

- [x] T014 `uv run pytest` y `uv run ruff check .` en verde
- [x] T015 Validar quickstart.md en esta máquina (criterio de salida: doctor OK con las 4 herramientas)
