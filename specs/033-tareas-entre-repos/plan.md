# Implementation Plan: Tareas que cruzan repos

**Branch**: `033-tareas-entre-repos` | **Spec**: [spec.md](spec.md) | **Depende de**: 032

## Summary

Hoy el engine da por hecho **una** ejecución, **un** worktree y **un** par base/head. Hay unas 40
llamadas `git.*(wt, ...)` y `gh.*(wt, ...)` en `engine.py`, y unas pocas en `service.py` y
`explain.py`. La forma de no duplicar el motor es introducir **partes**: una ejecución tiene una o
más partes, y las etapas recorren sus partes. Una ejecución de un repo tiene exactamente una
parte, construida desde la fila `run` como hoy. Así hay un solo camino de código y las pruebas de
un repo ejercitan el mismo bucle.

- **`unified/store.py`**: migración `_V8` con la tabla
  `run_part (run_id, repo, base_sha, head_sha, PRIMARY KEY (run_id, repo))`. Solo la usan las
  ejecuciones entre repos. El worktree de cada parte es `<carpeta de la tarea>/<repo>` y sus PRs
  van en la operación `<run>:pr` (`{"repos": [...]}`), así que no hacen falta más columnas. En
  ellas:
  - `run.worktree` es la carpeta de la tarea.
  - `run.head_sha` es una huella:
    `sha256("api:<sha>\nfront:<sha>")`. Así `approval`, `summary.ready` y las comparaciones de
    "commit nuevo invalida" funcionan sin cambios.
- **`routines/parts.py`** (nuevo, pequeño)
  - `Part(repo, root, wt, base_sha, head_sha, config, pr)`.
  - `parts(engine, run) -> list[Part]`: si la tarea tiene 0 o 1 repos, devuelve una parte desde
    `run`. Si tiene varios, las lee de `run_part` en el orden del espacio.
  - `ensure(engine, run_id)` crea `.umbra/worktrees/<id>/<repo>` por repo con
    `worktree.ensure`, que ya es idempotente, y escribe `run_part`.
  - `fingerprint(parts)` calcula la huella.
  - `prefixed_diff(parts, a, b)` hace `git diff --src-prefix=a/<repo>/ --dst-prefix=b/<repo>/`
    por parte, concatenado.
- **`routines/engine.py`**: las etapas recorren `parts(...)`.
  - **BUILD**: una sola llamada al agente, con `cwd` en la carpeta de la tarea. Luego, por parte:
    commit, `changed_files`, política y alcance. El alcance de la tarea usa rutas con el repo
    delante (`api/src/...`), que se recorta antes de comparar. Lo creado en la carpeta de la
    tarea fuera de las partes se borra y se registra como `out_of_scope`.
  - **Tests y lint**: `commands.run_registered(..., part.config, part.wt)` por parte. Cada
    evidencia lleva `repo`.
  - **Deriva de la base** (`base_drift`) por parte.
  - **REVIEW/ARBITER**: reciben `prefixed_diff`.
  - **VERIFY**: `start_background` por parte con `dev`, en orden, con
    `env={"UMBRA_URL_<REPO>": url}` acumulado. `start_background` gana un parámetro `env`. La URL
    de la app es la de `[workspace] app` o la última. Todos se detienen en un `finally`.
  - Un fallo de merge a mitad deja la ejecución en `WAITING_APPROVAL` (evento
    `approval.partial`): aprobar de nuevo salta lo integrado. Un conflicto antes de integrar
    nada la bloquea como hoy (`base_conflict`).
  - **SCAN**: los secretos se buscan en el diff de cada parte.
  - **SHIP**: por parte con cambios, push y PR (clave `<run>:pr:<repo>`). El cuerpo enlaza los
    otros PRs en su primera línea (`gh pr edit`, antes de registrar `<run>:pr`). A spec, merge
    automático por parte. Sin spec, `WAITING_APPROVAL` cuando todos los PRs existen.
  - **DESIGN**: se salta en una tarea entre repos (`design/` es de un repo).
  - **`approve()`**:
    - Comprueba, por parte, `headRefOid == part.head_sha`. Cualquier diferencia invalida.
    - Recalcula la huella.
    - Hace el merge por parte en orden, con la clave `<run>:merge:<repo>:<head>`. Si uno falla,
      queda `BLOCKED` con `merged=[...]` y `pending`. Reintentar la aprobación salta los que ya
      tienen clave.
  - **`cancel()`**: cierra los PRs y elimina los worktrees de todas las partes.
- **`service.py`**: `report`, `evidence`, `_workspace`/`open_workspace` (abre la carpeta de la
  tarea), `resume_human` (tomar el control: commit por parte) y `run` (base y rama de spec por
  repo) recorren las partes. `spec_tasks` acepta varios repos por historia.
- **`unified/explain.py`** y **`cli/watch_data.py`**:
  - Cambios con el repo delante y lista de PRs.
  - La fila de la tarea muestra `api + front`.
  - Telegram envía un enlace por PR.
- **Perfiles**: `builder` recibe en el sobre la lista de repos con su stack y la instrucción de
  trabajar dentro de `api/` y `front/`.

## Constitution Check

- **VII**: una aprobación humana cubre exactamente los heads que se aprobaron, porque la huella
  cambia con cualquier commit nuevo.
- **VIII**: claves de operación por repo para push, PR, merge y enlaces; la retoma salta lo hecho.
- **IX**: sigue habiendo un worktree por repo y por tarea. La carpeta de la tarea solo los
  agrupa.
- **X**: se justifica la tabla `run_part` y el módulo `parts.py`, porque sin ellos habría que
  duplicar el engine. Una ejecución de un repo no escribe en `run_part`.

## Riesgos

- El refactor toca casi todas las etapas. **Mitigación**: primero se mueve el engine a "recorrer
  partes" con una sola parte y la batería completa en verde (un PR sin cambio visible). Después
  se activan las partes múltiples.
- La integración no es atómica entre repos: es un límite de git y GitHub. Se mitiga con el orden
  del espacio, la retoma idempotente y un mensaje claro de qué quedó integrado.

## Pruebas

`tests/acceptance/test_cross_repo.py`, con el espacio de la 032 y dos remotos locales:

- Tarea `api, front` completa.
- Fallo de tests solo en `front`.
- Ruta protegida en `api`.
- Archivo fuera de las partes.
- Un solo repo con cambios.
- Aprobación invalidada por un commit nuevo.
- Merge que falla a mitad y su retoma.
- VERIFY con dos `dev` falsos que comprueban `UMBRA_URL_API`.
- Cancelar.
- Worker muerto en BUILD y en SHIP.
