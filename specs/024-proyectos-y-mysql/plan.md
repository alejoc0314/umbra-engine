# Implementation Plan: Tus proyectos y tu MySQL desde Telegram

**Branch**: `024-proyectos-y-mysql` | **Spec**: [spec.md](spec.md)

## Summary

`blocks/mysql.py` (PyMySQL, nueva dependencia): `check_read_only`, `query` (transacción READ
ONLY, sin MULTI_STATEMENTS, 200 filas) y `execute` (transacción, varias sentencias, rollback si
falla). `service`: `adopt` (git init + `.gitignore` básico + `init_project` + primer commit),
`db_query`, `db_propose` (deja `.umbra/artifacts/db/<id>.json`), `db_pending`, `db_apply`,
`db_discard`, con eventos `db.*` y `project.adopted`. `cli/db.py`: `umbra db query|change|list|
apply|discard`. `chat/launcher.py`: `db query/list/change` permitidos, `db apply/discard`
prohibidos; `ask(extra=…)`. Puente: `State.workspace`, `served` también escanea la carpeta del
repo de arranque, `folders`, `/adoptar`, `workspace_prompt` y las directivas `UMBRA>` en
`converse`, botones `dbok:`/`dbno:` en `act`.

## Constitution Check

I y II (cambiar de proyecto, adoptar y la BD pasan por operaciones de `service`, con origen) ·
VII (aplicar un cambio de BD es una decisión explícita de la persona: botón o terminal) · IX
(la contraseña de MySQL vive en una variable de entorno).

## Pruebas

`tests/acceptance/test_workspace_db.py`: descubrir y adoptar, la conversación que cambia de
proyecto y adopta, el cambio de BD con botón (una sola vez), permisos del chat y la terminal, y
la frontera de solo lectura. A mano, contra un MySQL 8.0.30 temporal: consultas, escrituras
frenadas, cambios aplicados y revertidos.
