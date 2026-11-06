# Feature Specification: Tareas que cruzan repos

**Feature Branch**: `033-tareas-entre-repos`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Si necesito trabajo realizado de extremo a extremo, tendría que hacer
tareas en el front y tareas en el back." Opción elegida: dentro de un espacio de trabajo (spec 032),
una tarea puede tocar varios repos a la vez y el agente ve y cambia los dos lados.

## Contexto

Con la spec 032, una funcionalidad completa se reparte en historias de un solo repo, encadenadas.
Eso basta cuando el trabajo se parte bien: primero el endpoint, después la pantalla. No basta
cuando un cambio solo tiene sentido completo, por ejemplo un campo nuevo que viaja de la base de
datos a la pantalla. Partido, el agente del front trabaja contra una API que solo conoce por la
spec, y nadie prueba los dos lados juntos hasta que ya está todo integrado.

Una **tarea entre repos** declara varios repos. El agente trabaja en una sola carpeta con un
worktree de cada uno, los tests de cada repo deben pasar, VERIFY levanta los repos juntos y el
resultado es un PR por repo. Se aprueban de una vez y se integran en el orden del espacio.

Depende de la spec 032.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Una historia que toca dos repos (Priority: P1)

Una historia declara `**Repo**: api, front` y `umbra spec tasks` crea **una** tarea con los dos
repos. Al ejecutarla, umbra crea un worktree de cada repo dentro de una misma carpeta de la tarea
(`<tarea>/api` y `<tarea>/front`), en la misma rama, y el agente arranca en esa carpeta. Los
tests, el lint y la política de cada repo se aplican a su parte del cambio. La tarea pasa una
etapa solo si pasa en todos sus repos.

**Acceptance Scenarios**:

1. **Given** una historia con `**Repo**: api, front`, **When** se ejecuta su tarea, **Then** el
   agente recibe una carpeta con `api/` y `front/`, y la indicación de cuál es cada uno.
2. **Given** que el cambio rompe un test de `front`, **Then** la tarea falla en las pruebas,
   aunque las de `api` pasen, y la evidencia dice qué repo falló.
3. **Given** que el agente toca una ruta protegida de `api` (por ejemplo `.umbra/`), **Then** la
   etapa se bloquea igual que en un proyecto de un repo, nombrando el repo.
4. **Given** que el agente crea archivos en la carpeta de la tarea fuera de `api/` y `front/`,
   **Then** se descartan y quedan registrados como fuera de alcance.

---

### User Story 2 - Integrar los repos juntos (Priority: P1)

En SHIP, umbra hace commit y abre un PR en cada repo que cambió. Cada PR enlaza a los otros. La
tarea espera **una** aprobación que cubre todos sus PRs. Al aprobar, se integran en el orden del
espacio. Un commit nuevo en cualquiera de los repos invalida la aprobación. Si la tarea es de una
spec, se integra en la rama `spec/<carpeta>` de cada repo, como cualquier tarea de spec.

**Acceptance Scenarios**:

1. **Given** una tarea que cambió `api` y `front`, **When** llega a SHIP, **Then** hay un PR en
   cada repo, cada uno con el enlace al otro, y la tarea queda esperando aprobación.
2. **Given** la tarea esperando, **When** la persona aprueba, **Then** se integra primero `api` y
   después `front`.
3. **Given** que el merge de `front` falla, **Then** `api` queda integrado, la tarea queda
   bloqueada con "integrado en api, falta front: <razón>", y aprobar de nuevo integra solo
   `front`.
4. **Given** una aprobación dada, **When** entra un commit nuevo en el PR de `front`, **Then** la
   aprobación deja de valer para toda la tarea.
5. **Given** una tarea que declaró `api, front` pero solo cambió `front`, **Then** solo hay PR en
   `front`, y el informe dice que `api` no necesitó cambios.

---

### User Story 3 - Verificar de extremo a extremo (Priority: P2)

En VERIFY, umbra levanta el `dev` de cada repo de la tarea en el orden del espacio. A cada uno le
pasa las URLs de los que ya están levantados como variables `UMBRA_URL_<REPO>` (por ejemplo,
`UMBRA_URL_API`), para que el front pueda apuntar al back del worktree y no al de producción. La
verificación en el navegador abre la URL del último repo levantado, o la de `[workspace] app` si
está configurada.

**Acceptance Scenarios**:

1. **Given** `api` y `front` con `dev` declarado, **When** la tarea llega a VERIFY, **Then** se
   levanta `api` primero y `front` recibe `UMBRA_URL_API` con la URL de `api`.
2. **Given** que `api` no arranca, **Then** VERIFY falla nombrando `api` y su registro, sin
   levantar `front`.
3. **Given** que VERIFY termina, de cualquier forma, **Then** se detienen todos los servidores que
   levantó.

---

### User Story 4 - Ver y retomar una tarea entre repos (Priority: P2)

`watch`, `status` y Telegram muestran los repos de la tarea (`#4 · api + front · Campo de
descuento`). El diff y la revisión llevan cada archivo con su repo delante (`api/src/...`,
`front/src/...`). `umbra open` abre la carpeta de la tarea con los dos worktrees. Reintentar, tomar
el control (spec 017) y cancelar actúan sobre todos los repos de la tarea.

**Acceptance Scenarios**:

1. **Given** una tarea entre repos esperando, **When** la persona abre su detalle en `watch`,
   **Then** ve los archivos cambiados de los dos repos, cada uno con su repo delante, y los
   enlaces a los dos PRs.
2. **Given** una tarea entre repos bloqueada, **When** la persona la cancela, **Then** se cierran
   sus PRs abiertos y se eliminan todos sus worktrees.

### Edge Cases

- **Ningún repo cambió**: igual que una tarea de un repo sin cambios.
- **Un repo declarado sin `dev`**: VERIFY lo salta y lo dice. Si ningún repo tiene `dev`, VERIFY
  se comporta como hoy sin servidor.
- **Puertos**: dos tareas entre repos en paralelo pueden pelear por los mismos puertos de `dev`.
  Es la misma limitación que ya existe en un proyecto de un repo, y no se resuelve aquí.
- **Ramas base distintas** (por ejemplo `main` en `api` y `develop` en `front`): cada repo usa la
  suya.
- **Historia de varios repos fuera de un espacio**: error, porque en un proyecto de un repo solo
  hay un repo.
- **Diseño**: en una tarea entre repos, la etapa de diseño se salta y lo dice. `design/` vive en
  un repo, así que el diseño se hace en una tarea de ese repo (el front) antes de la de extremo a
  extremo.

## Requirements *(mandatory)*

- **FR-001**: Una historia MUST poder declarar varios repos del espacio. Su tarea los guarda todos.
- **FR-002**: Una tarea entre repos MUST trabajar en una carpeta propia, con un worktree por repo
  en la misma rama. El agente arranca en esa carpeta.
- **FR-003**: Política, alcance, tests y lint MUST aplicarse por repo, con la configuración de cada
  uno. Una etapa pasa solo si pasa en todos.
- **FR-004**: SHIP MUST abrir un PR por cada repo con cambios, enlazados entre sí, cada uno con su
  `operation_key` por repo.
- **FR-005**: Una sola aprobación humana MUST cubrir todos los PRs de la tarea y MUST invalidarse
  con un commit nuevo en cualquiera de ellos. La integración MUST seguir el orden del espacio y
  MUST poder retomarse sin repetir lo ya integrado.
- **FR-006**: VERIFY MUST levantar el `dev` de cada repo en orden, pasar `UMBRA_URL_<REPO>` a los
  siguientes y detenerlos todos al terminar.
- **FR-007**: El diff, la revisión, el informe, `watch`, `open` y Telegram MUST mostrar cada cambio
  con su repo.
- **FR-008**: Reintentar, tomar el control y cancelar MUST actuar sobre todos los repos de la
  tarea.
- **FR-009**: Las tareas de un solo repo, en un espacio o fuera de él, MUST seguir funcionando
  exactamente igual.
- **FR-010**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

### Key Entities

- **Tarea entre repos**: tarea con dos o más repos.
- **Parte de la ejecución**: lo que una ejecución tiene en cada repo: rama, base, último commit,
  worktree y PR.

## Success Criteria *(mandatory)*

- **SC-001**: Con agentes falsos y dos remotos locales, una tarea `api, front` termina con dos PRs
  integrados en orden, tras una sola aprobación.
- **SC-002**: Un fallo de tests en un solo repo hace fallar la tarea, y la evidencia nombra el
  repo.
- **SC-003**: Un fallo a mitad de la integración se retoma integrando solo lo que faltaba.
- **SC-004**: Matar el worker en cualquier etapa de una tarea entre repos no pierde estado ni
  duplica ramas ni PRs.
- **SC-005**: Todas las pruebas anteriores, incluidas las de la 032, pasan sin cambios.

## Assumptions

- Una sola sesión de agente trabaja los dos repos. El costo de la tarea es uno, no uno por repo.
- La rama de la tarea se llama igual en todos sus repos.
- El orden de integración es el de `[workspace] repos`. Cambiar el contrato de una API sin romper
  la versión anterior es responsabilidad de la spec y de la revisión, no del motor.
