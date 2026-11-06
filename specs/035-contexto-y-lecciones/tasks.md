---

description: "Tareas: contexto justo por tarea y lecciones aprendidas"
---

# Tasks: Contexto justo por tarea y lecciones aprendidas

**Input**: `specs/035-contexto-y-lecciones/` (spec, plan, research, data-model, contracts/, quickstart)

**Tests**: incluidos. La constitución exige pruebas automáticas para la lógica no trivial
(máquina de estados, idempotencia, parsers), sin red ni modelos: agentes falsos de
`tests/fakes/`, repos git temporales y `UMBRA_HOME` apuntando a `tmp_path`.

**Organización**: por historia de usuario de `spec.md` (US1–US5).

## Formato: `[ID] [P?] [Story] Descripción`

- **[P]**: se puede hacer en paralelo (otro archivo, sin depender de tareas pendientes)
- **[USn]**: historia de `spec.md` a la que sirve

---

## Phase 1: Setup

**Purpose**: configuración y defaults que usan todas las historias

- [ ] T001 Añadir la lectura de `[context] max_chars` (int, por defecto `12000`) y de `[lessons] enabled` (bool, por defecto `true`) y `writer` (str, por defecto `"lesson-writer"`; `""` = solo borrador determinista) con funciones `context_limit(config)` y `lessons_settings(config)` en src/umbra/unified/config.py. Si un valor no es válido, se usa el defecto sin fallar.
- [ ] T002 [P] Documentar `[context]` y `[lessons]` con comentarios en el `project.toml` que genera `umbra init` (lista de líneas comunes) en src/umbra/unified/project.py.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: piezas que necesitan varias historias: sobre, migración y almacén de lecciones

**⚠️ CRITICAL**: ninguna historia empieza antes de terminar esta fase

- [ ] T003 Añadir `context: str | None = None` a `Envelope` y el modelo `LessonDraft` (`skip: bool = False`, `text: str = ""` "≤ 280 caracteres", `zone: list[str] = []`, `same_as: int | None = None`, `conflicts_with: list[int] = []`) en src/umbra/contracts/envelope.py. `SCHEMA_VERSION` sigue en `"1"`.
- [ ] T004 [P] Presentar `envelope.context` en el prompt, después de `project_notes`, con el encabezado de contracts/agents.md ("Contexto de esta tarea (reunido por umbra antes de empezar: …)"), en src/umbra/adapters/base.py.
- [ ] T005 [P] Migración `_V9` en src/umbra/unified/store.py: `CREATE TABLE run_file (run_id TEXT NOT NULL REFERENCES run(id), repo TEXT NOT NULL DEFAULT '', path TEXT NOT NULL, PRIMARY KEY (run_id, repo, path))`, añadida a `MIGRATIONS`.
- [ ] T006 Crear src/umbra/management/lessons.py con:
  - `open_db()` sobre `cfg.umbra_home() / "lessons.db"` (WAL, `busy_timeout = 5000`). El esquema son las tablas `lesson`, `lesson_origin`, `lesson_history` y `lesson_meta` tal como están en data-model.md:
    - `status` CHECK en (`proposed`, `approved`, `discarded`, `retired`);
    - `kind` CHECK en (`review_rejected`, `run_stopped`, `human_correction`);
    - `UNIQUE (project_key, run_id, event_id)` en `lesson_origin`;
    - PK `(project_key, number)`.
  - `project_key(parts)`:
    - repo: el SHA menor de `git rev-list --max-parents=0 HEAD`;
    - espacio: el sha256 de las claves de sus repos ordenadas;
    - repo sin commits: `path:` + sha256 de la ruta absoluta.
  - Resolución de alias desde `lesson_meta`.
- [ ] T007 [P] En src/umbra/management/lessons.py: `redact(text)` cambia por `«oculto»` cada coincidencia de `actions/secrets.PATTERNS`, y `zone_ok(glob)` rechaza las rutas absolutas y las que contienen `..`.
- [ ] T008 [P] Pruebas base en tests/unit/test_lessons.py:
  - clave de proyecto estable al copiar el repo a otra carpeta;
  - clave de un espacio;
  - repo sin commits;
  - `redact` con un token `ghp_…`;
  - `zone_ok`;
  - creación idempotente del esquema con `UMBRA_HOME=tmp_path`.

**Checkpoint**: el sobre acepta contexto, existe `run_file` y hay almacén de lecciones vacío

---

## Phase 3: User Story 1 - Cada tarea arranca con el contexto justo (Priority: P1) 🎯 MVP

**Goal**: la etapa `explore` arma un paquete acotado y Construir (y las demás etapas) lo reciben

**Independent Test**: escenarios 1–5 y 16 de quickstart.md: paquete con archivos, tests, historia
y tareas previas; respeta el tope; repo vacío; fallo no bloqueante; espacio de varios repos.

### Tests for User Story 1

- [ ] T009 [P] [US1] Pruebas unitarias de zona y armado en tests/unit/test_explore.py:
  - semillas desde `scope`, rutas del texto e identificadores (con un máximo de 15 archivos por identificador);
  - tests por convención (`test_x.py`, `x.test.ts`, `x.spec.js`, `XTest.php`);
  - co-cambio (3 por semilla);
  - el tope nunca se supera y `omitted` cuenta por tipo;
  - repo sin tests ni historia → `notes`;
  - en un espacio, rutas con prefijo de repo.
- [ ] T010 [P] [US1] Prueba de aceptación en tests/acceptance/test_task_context.py: ejecutar una tarea con el agente falso y comprobar:
  - `explore.ready`;
  - que el `Envelope` de `plan`, `build` y `review` trae `context`;
  - que una excepción simulada en `explore.explore` emite `explore.failed` y la ejecución sigue hasta `ship`.

### Implementation for User Story 1

- [ ] T011 [US1] Crear src/umbra/management/explore.py con la función `zone(parts, task, inventory)`, que aplica las semillas y la expansión de research §2:
  - devuelve una lista de `{path, repo, why}`;
  - lee el inventario del onboarding si existe;
  - cada llamada a git tiene un timeout, con un presupuesto total de 10 s.
- [ ] T012 [US1] En src/umbra/management/explore.py:
  - `tests_for(files)`: por convención de nombres, más `git grep -l` del nombre del módulo dentro de archivos de test;
  - `history(files)`: hasta 8 commits por zona, con SHA corto, fecha, asunto y archivos.
- [ ] T013 [US1] En src/umbra/management/explore.py: `previous_tasks(conn, files)`. Une `run_file` con `run` y `task` y devuelve número, título, estado final y los hallazgos `high` o más de Revisar (máximo 5 tareas, las más recientes). Antes rellena una sola vez, con `git diff --name-only base head`, las ejecuciones que aún no tengan filas en `run_file`.
- [ ] T014 [US1] En src/umbra/management/explore.py: `build_package(...) -> (markdown, summary)`.
  - Llena por bloques en orden de prioridad (zona, tests, lecciones, historia, tareas) y recorta por líneas completas, garantizando `chars ≤ max_chars`.
  - Rellena `omitted` y `notes`, con el formato de contracts/agents.md y el resumen de data-model.md.
  - Las lecciones vienen de `lessons.applicable(key, files)` (devuelve `[]` hasta US4).
- [ ] T015 [US1] Añadir la etapa `explore` al motor en src/umbra/routines/engine.py:
  - `run_stage` la despacha;
  - si existe el artefacto `kind='context'` con `tested_sha` igual a la huella de los SHA base, lo reutiliza;
  - si no, escribe `.umbra/artifacts/<run_id>-context-<fp8>.md` y `.json`, inserta el `artifact` (checksum sha256, `command='explore'`) y emite `explore.ready` con el resumen;
  - ante cualquier excepción emite `explore.failed` con el motivo y devuelve `Outcome("next")`.
- [ ] T016 [US1] En `agent_attempt` (src/umbra/routines/engine.py), poner en `envelope.context` el último paquete de la ejecución para las etapas `plan`, `design`, `build`, `review`, `verify` y `arbiter`.
- [ ] T017 [US1] Al terminar `build` en src/umbra/routines/engine.py, reemplazar las filas de `run_file` de la ejecución con los archivos del diff de cada parte (`pt.diff` / `git diff --name-only`).
- [ ] T018 [P] [US1] Añadir `- name: explore` como primera etapa en src/umbra/defaults/routines/feature.yaml y en src/umbra/defaults/routines/quick.yaml.

**Checkpoint**: las tareas arrancan con el paquete; MVP usable

---

## Phase 4: User Story 2 - El contexto se ve como evidencia (Priority: P1)

**Goal**: la persona ve qué contexto recibió el agente, en `explain` y en `watch`

**Independent Test**: escenario 1 + `umbra explain <n>` y `--json` muestran la sección y la clave
`context`; en `watch`, el detalle de la tarea abre el paquete.

### Tests for User Story 2

- [ ] T019 [P] [US2] Ampliar tests/acceptance/test_explain.py:
  - la sección "Contexto" (cuenta de archivos, tests, commits, tareas y lecciones; `chars / max_chars`; omitido; ruta);
  - `--json` con `context`;
  - `context: null` con `reason` cuando hubo `explore.failed` o la rutina no tiene `explore`.
- [ ] T020 [P] [US2] Ampliar tests/acceptance/test_watch_screen.py: el detalle de una tarea en Revisar muestra "Contexto que recibió" y la acción "ver paquete".

### Implementation for User Story 2

- [ ] T021 [US2] En src/umbra/unified/explain.py, leer el último `explore.ready` / `explore.failed` de la ejecución y añadir `context` a `Explanation` y a `as_dict()`.
- [ ] T022 [US2] Imprimir la sección Contexto en src/umbra/cli/explain.py, con números en formato `9 310 / 12 000`.
- [ ] T023 [US2] En src/umbra/cli/watch_data.py y src/umbra/cli/watch.py, añadir al detalle de la tarea el bloque "Contexto que recibió" y la acción "ver paquete", que abre el `.md` con el visor o editor que ya usa `watch`.
- [ ] T024 [P] [US2] Narrar `explore.ready` ("Explorar reunió N archivos, M tests… (9 310 / 12 000)") y `explore.failed` en `narrate()` en src/umbra/unified/explain.py.

**Checkpoint**: el paquete es evidencia visible

---

## Phase 5: User Story 3 - umbra propone lecciones de sus tropiezos (Priority: P1)

**Goal**: los rechazos de Revisar, las ejecuciones detenidas y las correcciones generan propuestas
con origen y fecha, sin duplicados

**Independent Test**: escenarios 6, 7, 10, 11 y 14 de quickstart.md

### Tests for User Story 3

- [ ] T025 [P] [US3] Pruebas unitarias de cosecha en tests/unit/test_lessons.py:
  - borrador determinista (sin `archivo:línea`; zona = carpetas de los archivos);
  - validación de `LessonDraft` (texto vacío, globs fuera, `same_as` inexistente → descartado);
  - duplicado normalizado → suma origen;
  - `same_as` a una descartada → solo suma origen;
  - cosechar dos veces no duplica (`UNIQUE`).
- [ ] T026 [P] [US3] Prueba de aceptación en tests/acceptance/test_task_context.py. Con un revisor falso que devuelve un hallazgo `high` y luego nada, la ejecución termina, aparece `L1` `proposed` con origen `review_rejected` (tarea, etapa, fecha) y una segunda tarea sobre la zona no recibe `L1` en su contexto.

### Implementation for User Story 3

- [ ] T027 [P] [US3] Crear src/umbra/defaults/profiles/lesson-writer.toml (`model = "haiku"`, `actions = []`, `output = "lesson-draft/v1"`, `max_minutes = 3`, `max_cost_usd = 0.10`, `roles = ["lessons"]`) y src/umbra/defaults/profiles/lesson-writer.md. Las instrucciones piden:
  - una regla corta e imperativa (≤ 280 caracteres);
  - una zona mínima;
  - `skip` si el fallo es puntual (red, cuota);
  - `same_as` / `conflicts_with` solo con los `L<n>` recibidos.
- [ ] T028 [US3] En src/umbra/management/lessons.py: `sources(conn, run_ids=None)` devuelve los eventos aún no cosechados:
  - `stage.rework` con `stage=review`;
  - `run.blocked` y `run.failed`;
  - `human.fixed`;
  - `run.rejected` con motivo.
  Los agrupa por ejecución y descarta los que ya tienen `lesson_origin.event_id`.
- [ ] T029 [US3] En src/umbra/management/lessons.py: `harvest(engine, run_ids=None)`. Por cada ejecución con fuentes:
  - comprueba la `operation_key` `lesson:<run_id>:<último event_id>` en la tabla `operation`;
  - llama a `engine.agent_attempt(run, "lesson", profile, wt, feedback=hechos, previous=hallazgos, output_model=LessonDraft)`, con las lecciones existentes de la zona en `project_notes`, o usa el borrador determinista si `writer == ""`, falla o no valida;
  - valida, oculta secretos y crea la propuesta (`number` = máximo + 1 del proyecto) o suma el origen;
  - escribe `lesson_history` con `channel='engine'`;
  - emite `lessons.proposed` con el número de propuestas nuevas.
  No hace nada si `[lessons] enabled = false`.
- [ ] T030 [US3] En src/umbra/routines/engine.py, llamar a `lessons.harvest(self, [run_id])` cuando una ejecución deja `RUNNING` (bloqueada, fallida, esperando aprobación o integrada), y además a `harvest(self)` para las fuentes pendientes del proyecto (p. ej. un `umbra reject`). Va dentro de `try/except`: un error emite `lessons.failed` y no cambia el estado.
- [ ] T031 [US3] En `resume_human` (src/umbra/service.py), emitir `human.fixed` con `message` y los archivos del commit de la persona. Comprobar que `reject` registra `run.rejected` con el motivo (añadir el campo si falta).

**Checkpoint**: las propuestas aparecen solas, sin aplicarse

---

## Phase 6: User Story 4 - La persona decide sobre cada lección (Priority: P1)

**Goal**: aprobar (con edición), descartar, retirar y resolver conflictos desde la CLI, `watch` y
Telegram; solo las aprobadas entran en el contexto

**Independent Test**: escenarios 8, 9 y 15 de quickstart.md, y la misma acción desde los tres
canales

### Tests for User Story 4

- [ ] T032 [P] [US4] Pruebas unitarias de estados en tests/unit/test_lessons.py:
  - transiciones válidas e inválidas (retirar una propuesta da error);
  - editar al aprobar guarda `before`;
  - `applicable` (glob vs zona; `[]` = todo el proyecto; orden: zona específica primero, aprobación más reciente primero; excluye las que tienen `conflicts`);
  - `stale`.
- [ ] T033 [P] [US4] Pruebas CLI en tests/acceptance/test_lessons_cli.py:
  - `umbra lesson list/show/approve/discard/retire/resolve` con y sin `--json`, con salida según contracts/cli.md;
  - errores con código ≠ 0;
  - tras aprobar con `--text`, una nueva tarea recibe el texto editado;
  - tras retirar, no; el `explain` de la tarea anterior sigue mostrando la lección.
- [ ] T034 [P] [US4] Ampliar tests/acceptance/test_telegram.py: `/lecciones` lista las propuestas con los botones Aprobar, Descartar y Ver; un botón de un `chat_id` no autorizado se ignora; llega un único aviso agrupado por cosecha.

### Implementation for User Story 4

- [ ] T035 [US4] En src/umbra/management/lessons.py:
  - `list_(key, status=None, all=False)` y `show(key, number)`, este con orígenes, historial y tareas en las que se aplicó (buscadas en el `lessons` de `explore.ready`);
  - `approve(key, n, text=None, zone=None, project_wide=False, actor, channel)`, que también vuelve a aprobar una retirada;
  - `discard`, `retire` y `resolve(a, b)`, que quita el conflicto mutuo;
  - `applicable(key, files)` y `stale(lesson, ls_files)`;
  - al proponer con `conflicts_with` válido, marcar el conflicto en ambas y registrar `conflict` en el historial.
- [ ] T036 [US4] Operaciones de servicio `lesson_list`, `lesson_show`, `lesson_approve`, `lesson_discard`, `lesson_retire`, `lesson_resolve` y `lesson_harvest` en src/umbra/service.py: resuelven la clave del proyecto desde `ctx` y registran `actor` y `channel` (`cli`, `watch` o `telegram:<chat_id>`).
- [ ] T037 [US4] Crear src/umbra/cli/lessons.py con el grupo `umbra lesson` de contracts/cli.md: `list`, `show`, `approve`, `discard`, `retire`, `resolve` y `harvest`, todos con `--json` y aceptando `L7` o `7`. Registrarlo con `app.add_typer(lessons_cli.app, name="lesson")` en src/umbra/cli/main.py.
- [ ] T038 [US4] En `umbra watch`, panel Lecciones con la tecla `l` (libre): propuestas primero y acciones `a` (aprobar con un editor de una línea que trae el texto propuesto), `d` (descartar) y `x` (retirar), según el estado. En la cabecera, "N lecciones por decidir". Archivos: src/umbra/cli/watch.py, src/umbra/cli/watch_data.py y src/umbra/cli/modals.py.
- [ ] T039 [US4] En src/umbra/routines/bridge.py:
  - comandos `("lecciones", "lecciones propuestas por decidir")` y `("leccion", "Ln · ver una lección")`, con botones que llaman a las operaciones de T036 y `channel = telegram:<chat_id>` verificado;
  - aviso agrupado al ver `lessons.proposed`: "Hay N lecciones nuevas por decidir: /lecciones".
- [ ] T040 [US4] Asegurar que el chat no puede decidir: en src/umbra/chat/launcher.py añadir solo `"lesson list"` y `"lesson show"` a `QUERY`, y ninguna acción de lecciones.

**Checkpoint**: el ciclo completo de una lección funciona en los tres canales

---

## Phase 7: User Story 5 - Las lecciones son de la persona, no del repo (Priority: P2)

**Goal**: privadas, fuera del repo, separadas por proyecto, a salvo de volver a clonar y
portables

**Independent Test**: escenarios 12, 13 y 17 de quickstart.md

### Tests for User Story 5

- [ ] T041 [P] [US5] Prueba de aceptación en tests/acceptance/test_lessons_cli.py:
  - aprobar lecciones deja `git status --porcelain` vacío;
  - clonar el repo de nuevo en otra carpeta muestra las mismas lecciones;
  - otro repo no las ve;
  - `export` → borrar `lessons.db` → `import` conserva estados, orígenes, fechas e historial;
  - importar dos veces no duplica.
- [ ] T042 [P] [US5] Prueba unitaria en tests/unit/test_lessons.py: un repo sin commits con lecciones (clave `path:`) pasa a la clave del primer commit tras el primer commit (alias en `lesson_meta`) y las lecciones siguen visibles.

### Implementation for User Story 5

- [ ] T043 [US5] En src/umbra/management/lessons.py:
  - `export(key)` devuelve JSON `{schema: 1, project_name, lessons: [...con origins e history]}`;
  - `import_(key, data)` reconoce lo existente por texto normalizado (`memory.normalize`) y zona, y mezcla orígenes por `(run_id, event_id)`;
  - migración automática de claves `path:` al primer commit al abrir.
- [ ] T044 [US5] Añadir `umbra lesson export [ARCHIVO]` e `import ARCHIVO` en src/umbra/cli/lessons.py, con las operaciones de servicio correspondientes en src/umbra/service.py.

**Checkpoint**: todas las historias funcionan por separado

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T045 [P] Documentar Explorar, `[context]`, `[lessons]`, `umbra lesson`, la tecla `l` y `/lecciones` en docs/usage.md.
- [ ] T046 [P] Añadir al final de `## Sin publicar` en CHANGELOG.md dos líneas en español llano: (1) "Cada tarea arranca con el contexto justo de su zona (archivos, tests, historia, tareas anteriores) y lo ves en `umbra explain` y en Revisar."; (2) "umbra propone lecciones de sus tropiezos; tú las apruebas, descartas o retiras (`umbra lesson`, tecla `l` en watch, `/lecciones` en Telegram), y viven solo en tu máquina."
- [ ] T047 Medir el tiempo de Explorar sobre este mismo repo (umbra-engine) y sobre un repo de unos 10 000 archivos. Si pasa de 10 s, ajustar los límites de `git grep` y de co-cambio en src/umbra/management/explore.py.
- [ ] T048 Ejecutar `uv run pytest` y `uv run ruff check .` (deben pasar) y el smoke manual en `sandbox/` de quickstart.md.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (1)**: sin dependencias.
- **Foundational (2)**: depende de Setup y bloquea todas las historias.
- **US1 (3)**: tras Foundational. Es el MVP.
- **US2 (4)**: depende de US1, porque muestra su paquete.
- **US3 (5)**: tras Foundational; no depende de US1 para proponer. La prueba T026, "no recibe L1 en su contexto", usa la etapa de US1.
- **US4 (6)**: depende de US3 (hay algo que decidir), y de US1 para que lo aprobado llegue al contexto.
- **US5 (7)**: tras Foundational. Export/import necesita las lecciones de US3 y US4 para probarse de punta a punta.
- **Polish (8)**: al final.

### Within Each User Story

- Primero las pruebas, que deben fallar; luego la lógica en `management/`, después el motor o el servicio, y por último la CLI, `watch` y Telegram.
- Varias tareas tocan el mismo archivo, src/umbra/routines/engine.py (T015–T017, T030), y van en secuencia.

### Parallel Opportunities

- T002 junto con T001.
- T004, T005, T007 y T008 junto con T006.
- En US1: T009, T010 y T018 a la vez.
- En US2: T019, T020 y T024.
- En US3: T025, T026 y T027.
- En US4: T032, T033 y T034.
- En US5: T041 y T042.
- En Polish: T045 y T046.

---

## Parallel Example: User Story 1

```bash
Task: "Pruebas unitarias de zona y armado en tests/unit/test_explore.py"
Task: "Prueba de aceptación en tests/acceptance/test_task_context.py"
Task: "Añadir `- name: explore` en src/umbra/defaults/routines/feature.yaml y quick.yaml"
```

## Parallel Example: User Story 4

```bash
Task: "Pruebas unitarias de estados en tests/unit/test_lessons.py"
Task: "Pruebas CLI en tests/acceptance/test_lessons_cli.py"
Task: "Ampliar tests/acceptance/test_telegram.py con /lecciones"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Setup y Foundational (T001–T008).
2. US1 (T009–T018): las tareas ya arrancan con contexto acotado.
3. **Validar**: escenarios 1–5 y 16 de quickstart.md.

### Incremental Delivery

1. US1 + US2: contexto y evidencia visible. Se puede publicar.
2. US3 + US4: lecciones propuestas y decididas por la persona. Se publican juntas: US3 sola
   produce propuestas que nadie puede aprobar.
3. US5: portabilidad (export/import y migración de claves).
4. Polish, CHANGELOG y piloto en `landing-manager` (SC-003, SC-004).

---

## Notes

- `umbra context build` (CONTEXT.md) ya existe. No se toca: el paquete por tarea es otra cosa y
  vive en `explore.py`.
- Las pruebas nunca escriben en el `~/.umbra` real: `UMBRA_HOME=tmp_path` en conftest.
- No cambiar `__version__` ni crear secciones de versión (AGENTS.md).
