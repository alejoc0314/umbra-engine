# Research: Contexto justo por tarea y lecciones aprendidas

## 1. ¿Explorar con modelo o sin modelo?

- **Decision**: Explorar es una etapa **determinista, sin modelo**, como `scan`. Usa `git ls-files`,
  `git grep`, `git log`, el inventario del onboarding y la base de umbra.
- **Rationale**: el pedido es "no inflar el gasto". Un explorador con modelo cuesta en cada tarea
  y lo que devuelve no se puede reproducir. La parte que necesita criterio (qué tocar exactamente)
  ya la hacen Planificar y Construir: Explorar solo les ahorra el descubrimiento. Así también se
  cumplen los principios II (umbra funciona sin modelo) y VI (la misma entrada da el mismo
  paquete).
- **Alternatives considered**:
  - Reutilizar el perfil `explorer` del onboarding (Sonnet, US$1,50). Sumaría hasta US$1,50 por
    tarea y repetiría lo que Construir ya hace.
  - Explorador barato (Haiku) que ordene archivos. Queda como mejora posible si el piloto muestra
    zonas mal elegidas; se activaría desde la rutina sin tocar el núcleo.

## 2. Cómo se deduce la zona de la tarea

- **Decision**: semillas, luego expansión y luego orden de prioridad.
  1. **Semillas**, en este orden:
     - `task.scope`: las rutas de `tasks.md`;
     - rutas que aparecen en el título, la descripción o la aceptación y existen en `git ls-files`;
     - vistas del inventario del onboarding que se nombran (vista → archivo);
     - identificadores del texto (CamelCase, snake_case o kebab-case de 4 caracteres o más) que
       `git grep -l -w` encuentra en pocos archivos (≤ 15; si aparecen en más, no discriminan);
     - palabras del texto que coinciden con nombres de archivo.
  2. **Expansión**, de cada semilla:
     - sus tests, por convención de nombres en todos los lenguajes (`test_x`, `x_test`,
       `x.test.*`, `x.spec.*`, `XTest`, `tests/**/x*`) y por `git grep` del nombre del módulo
       dentro de archivos de test;
     - los 3 archivos que más cambian junto a ella en `git log` (co-cambio).
  3. **Orden de prioridad**: semillas, tests, lecciones, historia y tareas anteriores.
- **Rationale**: es genérico (no depende del lenguaje), barato (unos pocos procesos de git) y
  explicable: cada archivo lleva su motivo ("en scope", "nombrado en la descripción",
  "test de X", "cambia junto a X").
- **Alternatives considered**: índice de símbolos con tree-sitter (añade dependencia y es por
  lenguaje); embeddings (red o modelo; viola X).

## 3. Qué lleva el paquete y cuánto ocupa

- **Decision**: el paquete lleva **referencias y hechos, no el contenido de los archivos**:
  - ruta, motivo y tamaño de cada archivo;
  - tests y el comando registrado que los corre;
  - historia: SHA corto, fecha y asunto, hasta 8 commits por zona;
  - tareas anteriores: número, título, resultado y hallazgos bloqueantes de Revisar;
  - lecciones aprobadas: texto y origen.
  Tope por defecto: `[context] max_chars = 12000` (unos 3 000 tokens), ajustable en
  `.umbra/project.toml`.
- **Rationale**: hoy `project_notes` ya puede llegar a unos 27 000 caracteres (constitución
  8 000, mapa 12 000, línea base 3 000, aprendido 4 000). El agente lee los archivos con sus
  propias herramientas: lo que encarece no es leerlos, sino buscarlos. 12 000 caracteres caben
  de sobra para unos 60 archivos con su motivo, 8 commits por zona, 5 tareas y 10 lecciones. El
  valor se revisa con el piloto (SC-003).
- **Alternatives considered**: incluir extractos de código (dispara el tamaño y se queda viejo en
  cuanto Construir cambia algo).

## 4. Dónde va Explorar en la rutina

- **Decision**: nueva etapa `explore` al inicio de `feature` (antes de `plan`) y de `quick` (antes
  de `build`). Se hace una vez por ejecución y por huella de los SHA base: el retrabajo vuelve a
  `build`, no a `explore`. Una rutina propia puede omitirla.
- **Rationale**: es la decisión de la spec. Al no costar modelo, adelantarla no encarece nada.

## 5. Cómo llega el paquete a los agentes

- **Decision**: un campo opcional nuevo `context` en el `Envelope`, que `adapters/base.py`
  presenta como "Contexto de esta tarea". Lo reciben `plan`, `build`, `review`, `verify`,
  `arbiter` y `design`. `schema_version` sigue en `"1"`, porque es un campo opcional y compatible.
- **Rationale**: `project_notes` es contexto de todo el proyecto; mezclarlo con el de la tarea
  impediría mostrarlos y medirlos por separado.

## 6. Tareas anteriores que tocaron la zona

- **Decision**: una tabla nueva `run_file(run_id, repo, path)`, migración V9 de `.umbra/umbra.db`.
  Se llena al terminar Construir con los nombres de `pt.diff`. Para ejecuciones anteriores a esta
  spec se rellena una sola vez con `git diff --name-only base head`, si los SHA siguen existiendo.
- **Rationale**: los merges por PR pueden borrar ramas o hacer squash, y entonces git ya no da la
  respuesta.

## 7. Dónde viven las lecciones

- **Decision**: una base SQLite global en `~/.umbra/lessons.db` (modo WAL), con las lecciones de
  todos los proyectos separadas por **clave de proyecto**:
  - **Repo**: el SHA del primer commit (`git rev-list --max-parents=0 HEAD`; si hay varios, el
    menor). Sobrevive a mover o volver a clonar.
  - **Espacio**: el hash de las claves ordenadas de sus repos.
  - **Repo sin commits**: el hash de la ruta absoluta. Pasa a la clave definitiva con el primer
    commit (`umbra lesson` lo migra solo).
- **Rationale**: la spec exige que las lecciones queden fuera del repo (FR-017) y que sobrevivan a
  volver a clonar (FR-018). `.umbra/umbra.db` está fuera de git, pero se pierde al clonar de
  nuevo. Se usa SQLite y no JSON porque varias tareas en paralelo pueden proponer a la vez, y
  SQLite ya resuelve esa concurrencia.
- **Alternatives considered**:
  - `~/.umbra/lessons/<clave>.json`: necesita un lock propio entre procesos.
  - `.umbra/lessons.toml` ignorado por git: se pierde al volver a clonar.

## 8. Cómo se redacta una lección

- **Decision**: un perfil nuevo `lesson-writer` (Haiku, sin acciones, 3 minutos, US$0,10) recibe
  los hechos del tropiezo y las lecciones existentes de esa zona. Devuelve un `LessonDraft`:
  `text`, `zone`, `same_as`, `conflicts_with` y `skip`.
  - Si falla, no hay agente disponible o no valida el contrato, umbra usa un **borrador
    determinista**: el mensaje del hallazgo, el motivo de la detención o el texto de la persona,
    sin la referencia `archivo:línea`. La zona son las carpetas de los archivos implicados.
  - El motor decide (principio III): `same_as` y `conflicts_with` solo cuentan si ese id existe en
    el mismo proyecto; si no, hay dos borradores casi iguales (texto normalizado con
    `memory.normalize`) y la misma zona, cuenta como duplicado.
- **Rationale**: un hallazgo tal cual ("falta validar null en a.py:12") no sirve como regla. Un
  modelo pequeño lo generaliza por céntimos y la persona lo aprueba o lo edita. Con el borrador
  determinista, umbra sigue funcionando sin modelo.
- **Alternatives considered**: solo plantillas (reglas pobres, la persona reescribiría casi
  todas); el `summarizer` actual (otro contrato y otro propósito).

## 9. Cuándo se cosechan las lecciones

- **Decision**: las fuentes son eventos que ya existen o se añaden:
  - `stage.rework` con `stage=review`: rechazo de Revisar;
  - `run.blocked` y `run.failed`: ejecución detenida;
  - `human.fixed`: nuevo, lo emite `umbra done -m`, con el mensaje y los archivos del commit de la
    persona;
  - `run.rejected`: con el motivo.
  `lessons.harvest(project)` procesa las fuentes aún sin cosechar, una llamada al redactor por
  ejecución y tramo, con `operation_key = lesson:<run_id>:<último event_id>` (principio VIII).
  - **Cuándo corre**: lo llama el motor cuando una ejecución deja `RUNNING` (en el worker, sin
    frenar a la persona) y también `umbra lesson harvest`.
  - **Rechazos de la persona**: `umbra reject` termina la ejecución sin pasar por el motor, así
    que esa fuente se cosecha en el siguiente cierre de cualquier ejecución del proyecto o con
    `harvest`.
- **Rationale**: nunca bloquea un comando interactivo, nunca cuesta dos veces lo mismo y agrupa
  los rechazos de una ejecución en una sola llamada.

## 10. Secretos

- **Decision**: antes de guardar un texto o un origen, se le aplican los patrones de
  `actions/secrets.PATTERNS` y cada coincidencia se cambia por `«oculto»`.
- **Rationale**: se reutiliza lo que ya detecta Escanear; sin dependencias nuevas.

## 11. Relación con `aprendido.md` y la constitución

- **Decision**: no cambian. `aprendido.md` (en `.umbra/`, versionado) sigue registrando las
  **decisiones del equipo** sobre hallazgos y permisos. La constitución sigue siendo la norma
  compartida. Las lecciones son el **criterio privado** de la persona.
  - `umbra lesson show` sugiere "llévala a la constitución" cuando una lección aprobada aplica a
    todo el proyecto. Es solo una sugerencia, nada automático.
- **Rationale**: la persona pidió explícitamente que las lecciones no se versionen.
