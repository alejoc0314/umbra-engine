# Feature Specification: Espacios de trabajo con varios repos

**Feature Branch**: `032-espacios-multi-repo`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Normalmente las carpetas de cada proyecto tienen aparte su frontend y
su backend. Si necesito trabajo de extremo a extremo tendría que hacer tareas en el front y tareas
en el back, o tener cada uno abierto con umbra watch, y tampoco es la idea." Opción elegida: umbra
en la carpeta padre, con tareas de un solo repo y dependencias entre repos.

## Contexto

Hoy un proyecto de umbra es un repositorio git. La forma de trabajar más común de la persona es
otra: una carpeta padre que no es repo y, dentro, dos repos hermanos, por ejemplo
`landing-manager/{api-landing-manager,front-landing-manager}`, muchas veces con un
`.code-workspace`. Con umbra eso obliga a llevar dos specs, dos colas y dos `watch` para una sola
funcionalidad, sin forma de decir que el front espera al back.

Un **espacio de trabajo** es esa carpeta padre gestionada por umbra como un solo proyecto: una
spec, una cola, un `watch`, un Telegram. Cada tarea sigue viviendo en un solo repo, con su
worktree, su rama y su PR, como hoy. Esta spec no cubre las tareas que tocan varios repos a la
vez, que son la spec 033.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Crear el espacio desde la carpeta padre (Priority: P1)

En una carpeta que no es repo git, `umbra init` busca los repos hijos directos. Si hay dos o más,
propone crear un espacio con ellos (con `-y` lo crea sin preguntar). Así quedan:

- La configuración del espacio en `.umbra/project.toml` de la carpeta padre, con `[workspace]
  repos` en el orden de integración. El orden por defecto es el del `.code-workspace` si existe, y
  si no, el alfabético. La persona lo ajusta: lo normal es el back primero.
- Cada repo inicializado como hoy, con su `.umbra/project.toml` versionado: stack, comandos de
  test, lint y dev, rama base y política.

Desde la carpeta padre o desde dentro de cualquiera de sus repos, `umbra` trabaja con el espacio.

**Acceptance Scenarios**:

1. **Given** una carpeta con los repos `api` y `front` y sin `.umbra/`, **When** la persona
   ejecuta `umbra init -y` en ella, **Then** se crea el espacio con `repos = ["api", "front"]` y
   cada repo queda inicializado con el stack que se le detectó.
2. **Given** un espacio creado, **When** la persona ejecuta `umbra status` dentro de `front/`,
   **Then** ve el estado del espacio completo, no el de `front` solo.
3. **Given** un espacio, **When** la persona abre `umbra watch --all` o `umbra projects`,
   **Then** el espacio aparece una sola vez y sus repos no aparecen como proyectos sueltos.
4. **Given** una carpeta con un solo repo hijo, **When** ejecuta `umbra init`, **Then** umbra
   explica que un espacio necesita al menos dos repos y le sugiere hacer `umbra init` dentro de
   ese repo.

---

### User Story 2 - Una spec que reparte historias entre repos (Priority: P1)

La conversación de la spec (`umbra spec new`, `/spec`) se abre en la carpeta padre y conoce los
repos del espacio y su stack. Cada historia declara en qué repo se hace con una línea
`**Repo**: <nombre>`. `umbra spec tasks` crea una tarea por historia con su repo. Las tareas
mantienen la cadena que ya existe (cada una depende de la anterior), así que si la historia del
back va antes, la del front no arranca hasta que la del back esté integrada.

**Acceptance Scenarios**:

1. **Given** una spec con la US1 en `api` y la US2 en `front`, **When** la persona ejecuta
   `umbra spec tasks`, **Then** se crean dos tareas: la 2, en `front`, depende de la 1, en `api`.
2. **Given** una historia sin `**Repo**` o con un repo que no está en el espacio, **When** se
   piden las tareas, **Then** no se crea ninguna y el error nombra la historia y los repos
   válidos.
3. **Given** la conversación de la spec en un espacio, **Then** sus indicaciones incluyen la lista
   de repos y piden declarar el repo de cada historia, poniendo primero lo que otro repo necesita.

---

### User Story 3 - Ejecutar e integrar cada tarea en su repo (Priority: P1)

Una tarea del espacio corre igual que en un proyecto de un repo, pero sobre el suyo: worktree,
comandos de test, lint y dev, rama de la spec y política salen de ese repo. Cuando todas las
tareas de la spec están integradas en sus ramas, umbra abre **un PR de spec por cada repo que
tuvo tareas** y avisa una sola vez. Al aprobar la spec, los integra en el orden del espacio. Si
uno falla, los que ya entraron se quedan y aprobar de nuevo retoma desde el que falta.

**Acceptance Scenarios**:

1. **Given** las tareas 1 (`api`) y 2 (`front`) aceptadas, **When** la persona ejecuta
   `umbra run 1 2`, **Then** la 1 corre en un worktree de `api` con los tests de `api`, y la 2
   queda esperando hasta que la 1 se integre en `spec/<carpeta>` de `api`. Después la 2 corre en
   `front` con los tests de `front`.
2. **Given** las dos tareas integradas, **Then** existe un PR `spec/<carpeta>` → base en cada
   repo, y `umbra status` y `watch` muestran la spec esperando aprobación con sus dos PRs.
3. **Given** la spec esperando, **When** la persona la aprueba, **Then** se integra primero el PR
   de `api` y después el de `front`, y la copia local de la rama base de cada repo queda al día.
4. **Given** que el PR de `front` no se puede integrar (conflicto), **When** se aprueba la spec,
   **Then** el de `api` queda integrado, umbra dice que falta `front` y por qué, y aprobar de
   nuevo integra solo `front`, sin repetir `api`.
5. **Given** un worker que muere a mitad de una tarea de `front`, **When** se retoma, **Then**
   continúa en el worktree de `front` sin duplicar ramas ni PRs.

---

### User Story 4 - Verlo y decidirlo en un solo lugar (Priority: P2)

`watch`, `status`, `explain`, `open` y Telegram muestran el repo de cada tarea (por ejemplo
`#2 · front · Pantalla de pagos`). El diff, las evidencias y el informe salen del repo de la
tarea. Los avisos llevan el nombre del espacio.

**Acceptance Scenarios**:

1. **Given** un espacio con tareas en dos repos, **When** la persona abre `umbra watch` desde la
   carpeta padre o desde un repo, **Then** ve todas las tareas con su repo y puede aprobar,
   reintentar o abrir cualquiera.
2. **Given** una tarea de `front` esperando, **When** llega el aviso a Telegram, **Then** nombra el
   espacio y el repo, y aprobar desde ahí funciona igual que en la terminal.

### Edge Cases

- **Repo con tareas propias sin terminar**: `umbra init` del espacio no lo une. Avisa qué
  ejecuciones tiene activas y pide terminarlas o cancelarlas antes. Su historial anterior se queda
  en el `.umbra/` de ese repo.
- **Repo que falta o cambió de nombre**: los comandos fallan con un mensaje que nombra el repo y
  la ruta esperada. No se adivina.
- **Carpeta padre que ya es un repo git** (repos anidados o subcarpetas de un mismo repo): es un
  proyecto normal y queda fuera de esta spec.
- **Repo sin remoto o sin `gh`**: falla igual que hoy en un proyecto de un repo, nombrando el
  repo.
- **Un comando que solo tiene sentido por repo** (`umbra exec test`): en un espacio se elige el
  repo con `--repo <nombre>`. Sin ese dato, falla con la lista de repos. `umbra db` usa la
  configuración del espacio (tu MySQL local es uno solo).
- **`umbra onboard` en un espacio**: queda fuera de alcance. Responde que aún no está soportado y
  sugiere hacer el onboarding de cada repo antes de unirlo.

## Requirements *(mandatory)*

- **FR-001**: `umbra init` en una carpeta que no es repo y tiene dos o más repos hijos MUST
  proponer un espacio, guardar `[workspace] repos` en orden e inicializar cada repo.
- **FR-002**: Desde la carpeta padre o desde cualquiera de sus repos, umbra MUST resolver el
  espacio: un solo estado, una cola, un worker y un `watch`.
- **FR-003**: Cada tarea de un espacio MUST pertenecer a un repo del espacio. Las historias lo
  declaran con `**Repo**: <nombre>` y una historia sin repo válido MUST impedir que se creen las
  tareas.
- **FR-004**: Worktree, rama, PR, comandos, política y rama base de una tarea MUST salir de su
  repo. La configuración compartida (avisos, Telegram, paralelo, piloto automático, diseño) sale
  del espacio.
- **FR-005**: Las dependencias entre tareas MUST respetarse aunque estén en repos distintos.
- **FR-006**: Al integrarse todas las tareas de una spec, umbra MUST abrir un PR de spec por cada
  repo con tareas en ella. Aprobar la spec MUST integrarlos en el orden del espacio, cada uno con
  su propia clave de operación, de modo que repetir la aprobación no repita lo ya integrado.
- **FR-007**: Las specs del espacio MUST vivir en `specs/` de la carpeta padre. Al trabajar una
  tarea, la carpeta de su spec MUST copiarse al worktree, de modo que quede versionada en cada
  repo que participa.
- **FR-008**: `watch`, `status`, `explain`, `open`, el informe y Telegram MUST mostrar el repo de
  cada tarea y sacar el diff y las evidencias de ese repo.
- **FR-009**: Los proyectos de un solo repo MUST seguir funcionando exactamente igual.
- **FR-010**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

### Key Entities

- **Espacio de trabajo**: carpeta padre con `.umbra/` y la lista ordenada de repos. Guarda el
  estado, las specs y la configuración compartida.
- **Repo del espacio**: repo git hijo, con nombre igual al de su carpeta y su propio
  `.umbra/project.toml` versionado.
- **Tarea**: además de lo de hoy, el repo al que pertenece.

## Success Criteria *(mandatory)*

- **SC-001**: Con agentes falsos y dos remotos git locales, una spec con una historia en cada
  repo termina con dos PRs de spec integrados en el orden del espacio, sin abrir más de un
  `watch`.
- **SC-002**: Matar el worker a mitad de una tarea de un espacio no pierde estado ni duplica
  ramas ni PRs (mismo criterio que E1).
- **SC-003**: Repetir la aprobación de una spec que falló a mitad solo integra los repos que
  faltaban.
- **SC-004**: Todas las pruebas anteriores pasan sin cambios: los proyectos de un repo no notan
  la diferencia.

## Assumptions

- La carpeta padre no es un repo, así que el `.umbra/project.toml` del espacio y las specs no se
  versionan ahí. Las specs quedan versionadas en cada repo al copiarse a sus worktrees. Compartir
  la configuración del espacio con un equipo queda para más adelante.
- El nombre de cada repo es el de su carpeta. No hay alias.
- Las tareas siguen la cadena de historias que ya existe. No se añade una sintaxis nueva de
  dependencias.
- Si existe un `.code-workspace`, solo se usa para proponer el orden de los repos.
