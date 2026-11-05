# Feature Specification: E0 — Esqueleto, store y diagnóstico

**Feature Branch**: `001-e0-skeleton`
**Created**: 2026-10-29
**Status**: Draft
**Input**: Entrega E0 de `docs/design.md` (sección 12): paquete instalable, `umbra init`,
`umbra doctor`, `umbra status` y el almacén de estado del proyecto.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Diagnosticar el entorno (Priority: P1)

Alejandro instala umbra y quiere saber, antes de nada, si su máquina tiene todo lo que umbra
necesita: git, el cliente de GitHub, Claude Code y Codex, con su versión y si hay sesión iniciada.

**Why this priority**: Sin las herramientas externas ningún otro comando funciona. Es el criterio de
salida de E0.

**Independent Test**: Ejecutar `umbra doctor` en una máquina con y sin cada herramienta y comprobar
el reporte y el código de salida.

**Acceptance Scenarios**:

1. **Given** las cuatro herramientas instaladas y con sesión, **When** ejecuta `umbra doctor`,
   **Then** ve cada herramienta con su versión y estado OK, y el comando termina con código 0.
2. **Given** falta una herramienta obligatoria, **When** ejecuta `umbra doctor`, **Then** ve cuál
   falta con una indicación para instalarla y el comando termina con código distinto de 0.
3. **Given** cualquier estado, **When** ejecuta `umbra doctor --json`, **Then** obtiene un JSON
   con una entrada por herramienta (nombre, encontrada, versión, sesión, obligatoria).

---

### User Story 2 - Inicializar un proyecto (Priority: P1)

Dentro de un repositorio git existente, Alejandro ejecuta `umbra init` y obtiene la carpeta de
configuración del proyecto con comandos de test y lint propuestos según el stack detectado.

**Why this priority**: Todas las entregas siguientes leen esta configuración.

**Independent Test**: Ejecutar `umbra init` en repos de prueba con distintos stacks y revisar los
archivos creados.

**Acceptance Scenarios**:

1. **Given** un repo git con `pyproject.toml`, **When** ejecuta `umbra init`, **Then** se crea
   `.umbra/project.toml` con stack `python` y comandos `test` y `lint` propuestos, y se crean
   `.umbra/routines/` y `.umbra/profiles/`.
2. **Given** un repo con `package.json` o `composer.json`, **When** ejecuta `umbra init`, **Then**
   el stack y los comandos propuestos corresponden a Node o PHP.
3. **Given** un repo ya inicializado, **When** ejecuta `umbra init` de nuevo, **Then** no se
   sobrescribe la configuración existente y se informa que ya estaba inicializado.
4. **Given** un directorio que no es un repo git, **When** ejecuta `umbra init`, **Then** recibe un
   error claro y no se crea nada.
5. **Given** cualquier repo inicializado, **Then** el estado local (base de datos, artefactos,
   worktrees) queda excluido del control de versiones.

---

### User Story 3 - Consultar el estado (Priority: P2)

Alejandro ejecuta `umbra status` para ver tareas, ejecuciones activas y gasto del proyecto. En E0
todo estará vacío, pero el comando y su formato quedan definidos.

**Why this priority**: Es la base de consulta que usarán el chat y los scripts.

**Independent Test**: Ejecutar `umbra status` y `umbra status --json` en un proyecto inicializado.

**Acceptance Scenarios**:

1. **Given** un proyecto inicializado, **When** ejecuta `umbra status`, **Then** ve el conteo de
   tareas por estado, las ejecuciones activas y el gasto total (cero).
2. **Given** un proyecto no inicializado, **When** ejecuta `umbra status`, **Then** recibe un
   error que sugiere `umbra init`.

### Edge Cases

- Una herramienta existe pero su comando de versión falla o tarda: se reporta como encontrada con
  versión desconocida, sin bloquear el diagnóstico más de unos segundos por herramienta.
- `umbra init` ejecutado desde un subdirectorio del repo: se inicializa en la raíz del repo.
- Base de datos de una versión anterior de umbra: se migra automáticamente al abrirla.
- Repo sin stack reconocible: stack `generic`, sin comandos propuestos, con comentario para
  completarlos a mano.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El paquete MUST instalarse como herramienta de línea de comandos con un único
  comando de instalación y exponer el ejecutable `umbra`.
- **FR-002**: `umbra doctor` MUST verificar git, gh, claude y codex: presencia, versión y sesión
  iniciada cuando la herramienta lo permita consultar sin efectos secundarios.
- **FR-003**: `umbra doctor` MUST terminar con código distinto de 0 si falta una herramienta
  obligatoria (git, gh y al menos un agente).
- **FR-004**: `umbra init` MUST crear `.umbra/project.toml`, `.umbra/routines/` y
  `.umbra/profiles/` en la raíz del repo, sin sobrescribir configuración existente.
- **FR-005**: `umbra init` MUST detectar el stack (python, node, php, generic) y proponer
  comandos registrados `test` y `lint`, marcados como `safe`.
- **FR-006**: `umbra init` MUST excluir del control de versiones el estado local de umbra.
- **FR-007**: El sistema MUST mantener un almacén de estado por proyecto con las entidades de la
  sección 8 del diseño y sus reglas de unicidad, versionado y migrable.
- **FR-008**: Los importes de costo MUST almacenarse sin pérdida de precisión decimal.
- **FR-009**: `umbra status` MUST mostrar tareas por estado, ejecuciones activas y gasto total.
- **FR-010**: Todos los comandos de E0 que producen datos MUST aceptar `--json`.

### Key Entities

- **Proyecto**: repo raíz, stack, rama base, comandos registrados y política.
- **Spec, Task, Dependency, Run, Attempt, Artifact, Finding, Approval, Usage, Event, Operation**:
  definidas en `docs/design.md` sección 8; en E0 solo se crea su almacenamiento.
- **Herramienta**: nombre, obligatoria, encontrada, versión, sesión.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: En la máquina de Alejandro, `umbra doctor` reporta correctamente las cuatro
  herramientas en menos de 10 segundos.
- **SC-002**: De instalar umbra a tener un repo inicializado toma menos de 2 minutos.
- **SC-003**: El 100% de las reglas de unicidad del almacén rechazan duplicados en pruebas.
- **SC-004**: Repetir `umbra init` 2 veces deja la configuración idéntica a la primera.

## Assumptions

- Un único usuario local; sin autenticación propia de umbra.
- "Al menos un agente" basta para el diagnóstico: Claude Code o Codex.
- La sesión de gh se consulta con su comando de estado; la de claude y codex se reporta como
  "no verificable" si no existe un comando de consulta sin efectos.
- Las tablas para tareas, ejecuciones, etc. se crean en E0 aunque se usen desde E1.
