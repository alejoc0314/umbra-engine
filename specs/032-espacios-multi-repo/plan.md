# Implementation Plan: Espacios de trabajo con varios repos

**Branch**: `032-espacios-multi-repo` | **Spec**: [spec.md](spec.md)

## Summary

La idea central es que **el motor no cambia de forma**. Una ejecución se sigue procesando con un
`Engine(root, udir, conn, project)`. En un espacio, `root` es el repo de la tarea, `udir` es el
`.umbra/` del espacio (una base, un worker, un lease) y `project` es la configuración del repo con
la del espacio encima. Casi todo el código que hoy usa `self.root` ya hace lo correcto con ese
cambio. Lo que hay que tocar es lo que trabaja **por spec** (rama y PR de spec), porque una spec
abarca varios repos.

- **`unified/project.py`**
  - `find_workspace(start)` sube desde `start`, y desde la carpeta padre del repo git, buscando
    `.umbra/project.toml` con `[workspace]`.
  - `umbra_dir()` devuelve el espacio si lo encuentra. Si no, hace lo de hoy.
  - `members(root, config) -> dict[nombre, Path]` lee `[workspace] repos`. Si falta un repo,
    lanza `NotInitialized` con su nombre y su ruta.
  - `repo_config(ws_config, member) = merge(load_project(member), ws_config sin "workspace")`. El
    espacio no escribe `[project]`, `[commands]` ni `[policy]`, así que esas secciones salen del
    repo.
  - `init_project()`: si `start` no es repo git, busca los repos hijos directos (`*/.git`).
    - Con dos o más, escribe el `project.toml` del espacio (`[workspace] repos`, más las
      secciones compartidas de `_render_toml`: notify, blocks, autopilot, editor) y llama a
      `init_project(repo)` en cada uno.
    - Con menos de dos, devuelve un `NotARepo` con la sugerencia.
    - El orden de los repos sale de `folders[].path` del `.code-workspace` (JSON con comentarios:
      se quitan las líneas `//`), o es alfabético.
    - Antes de unir un repo con `.umbra/umbra.db`, comprueba que no tenga ejecuciones activas
      (`ACTIVE_RUN_STATES`).
- **`unified/store.py`**: migración `_V7`, que añade a `task` la columna
  `repos TEXT NOT NULL DEFAULT '[]'` (lista JSON). En esta spec la lista tiene 0 o 1 elementos; la
  033 permite varios sin otra migración. Las operaciones por repo reutilizan `operation_key` con
  el sufijo `:<repo>`, sin tabla nueva.
- **`management/specfile.py`**: `_REPO_LINE = ^\*\*Repos?\*\*\s*:\s*(.*)$` → `Story.repos`
  (nombres separados por coma).
- **`service.py`**
  - `Ctx` añade `members: dict[str, Path]`, vacío en un proyecto de un repo.
  - `repo_of(ctx, task) -> (root, config)`: en un proyecto de un repo devuelve
    `(ctx.root, ctx.config)`.
  - `engine(ctx, origin, run_row=None)` construye el engine del repo de la ejecución.
  - Pasan a usar `repo_of` donde hoy usan `ctx.root` para git o gh: `run` (configuración de
    agentes del repo, `remote_base`, push de `spec/<carpeta>`), `approve` (`fast_forward` y
    `context_build` del repo), `report`/`evidence`, `_workspace`/`open_workspace` y `cancel`.
  - `spec_tasks` valida `Story.repos` contra `ctx.members` antes de insertar nada y guarda
    `repos` en la tarea. `planning.insert_proposals` recibe el campo.
  - `approve_spec`/`spec_pr` recorren los PRs de spec por repo, en el orden de `members`, con la
    clave `spec:<carpeta>:merge:<repo>`. Si uno falla, devuelven `{"merged": [...],
    "pending": repo, "reason": ...}`.
  - `exec` acepta `--repo`; `umbra task add --repo` y `umbra task repo <n> <repo>`.
- **`routines/worker.py`**: `run_one` lee el repo de la tarea de la ejecución y construye el
  `Engine` con `repo_of`. El worker y el lease siguen siendo uno solo, el del espacio.
- **`routines/engine.py`**: `spec_ready` cuenta las tareas pendientes de la spec en todos los
  repos. Cuando no queda ninguna, abre un PR por cada repo con tareas en la spec (clave
  `spec:<carpeta>:pr:<repo>`) y avisa una sola vez (clave `spec:<carpeta>:ready`). En un proyecto
  de un repo, las claves siguen siendo las de hoy.
- **`chat/elicit.py`**: en un espacio, las indicaciones de la conversación incluyen los repos con
  su stack y la regla de `**Repo**` por historia, con lo que otro repo necesita primero.
- **Vista**: `watch_data` añade el repo a la fila de la tarea y saca el diff con
  `git.run(repo_root, ...)`. `projects.register` marca el espacio y `overview()` oculta los repos
  que pertenecen a un espacio registrado. Los avisos de Telegram y de escritorio muestran
  `<espacio> · <repo>`.
- **`umbra onboard`** en un espacio responde que no está soportado.

## Constitution Check

- **I/II**: todo funciona por comandos; el espacio es otro tipo de raíz para los mismos comandos.
- **VII**: la aprobación de la spec sigue siendo humana y explícita, una sola vez para todos sus
  PRs.
- **VIII**: cada PR y cada merge por repo tiene su `operation_key`; repetir no duplica.
- **IX**: un worktree por tarea, en el repo de la tarea.
- **X**: sin tablas ni procesos nuevos; una columna y la misma forma del motor. Se justifica con
  el caso real: 5 de los proyectos en `C:/apps` tienen front y back en repos hermanos.

**Enmienda menor**: en Restricciones técnicas, el estado vive "en `.umbra/umbra.db` por proyecto o
por espacio" y el paralelo es "por proyecto o espacio". Va en el mismo PR.

## Riesgos

- El mayor es que algún sitio siga usando `ctx.root` para git en un espacio. Mitigación: en un
  espacio la raíz no es repo, así que cualquier `git.run(ctx.root, ...)` olvidado falla en voz
  alta en las pruebas en vez de actuar sobre el repo equivocado.

## Pruebas

`tests/acceptance/test_workspace.py`, con dos repos y dos remotos locales:

- `init` del espacio (orden del `.code-workspace`, rechazo con un solo repo, repo con
  ejecuciones activas).
- Resolución desde un repo.
- Historia sin repo.
- Cadena `api` → `front`.
- PRs de spec por repo, aprobación en orden, fallo a mitad y reintento.
- Worker muerto a mitad.
- `watch` y Telegram con el repo.

Se mantiene sin cambios la batería de un repo.
