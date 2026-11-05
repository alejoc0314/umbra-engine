# Feature Specification: E3 — Management y conversación

**Feature Branch**: `004-e3-management-chat`
**Created**: 2026-10-29
**Status**: Draft
**Input**: Entrega E3 de `docs/design.md`: `umbra plan` desde una spec, edición de tareas,
dependencias y `umbra chat`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - De una spec a tareas (Priority: P1)

Alejandro escribe una spec en Markdown y ejecuta `umbra plan spec.md`. Un agente planificador
propone tareas con criterios de aceptación, alcance, prioridad y dependencias. Quedan en
borrador para que él las revise antes de ejecutar nada.

**Acceptance Scenarios**:

1. **Given** una spec, **When** ejecuta `umbra plan spec.md`, **Then** se guarda una versión
   inmutable de la spec y se crean tareas en borrador ligadas a ella.
2. **Given** la misma spec sin cambios, **When** se planifica de nuevo, **Then** se reutiliza la
   versión existente.
3. **Given** el planificador propone dependencias con un ciclo, **Then** no se crea ninguna tarea
   y se informa el ciclo.
4. **Given** el planificador tiene preguntas materiales, **Then** se muestran y no se crean
   tareas.

### User Story 2 - Ajustar tareas y dependencias (Priority: P1)

1. `umbra task edit N` cambia título, descripción, criterios, alcance o prioridad, e incrementa
   la revisión; con `--expect-revision` rechaza la edición si alguien la cambió antes.
2. `umbra task accept N...` y `umbra task drop N...` cambian el estado.
3. `umbra task deps N --on M` añade una dependencia y rechaza ciclos y referencias inexistentes.
4. `umbra run` rechaza una tarea cuyas dependencias no están hechas.

### User Story 3 - Conversar con umbra (Priority: P1)

`umbra chat` abre Claude Code interactivo con el contexto del proyecto. Claude ejecuta comandos
de umbra y comandos registrados del proyecto según tres niveles: sin confirmación (consultas y
comandos `safe`), con confirmación (lo que cambia estado y cualquier otro shell) y prohibidos
(`approve`, `reject`, `git push`, `gh pr merge`, editar la política).

**Acceptance Scenarios**:

1. **Given** `claude` instalado, **When** ejecuta `umbra chat`, **Then** se abre la sesión con el
   prompt de umbra y las reglas de permisos.
2. **Given** el chat intenta `umbra approve`, **Then** la regla `deny` lo bloquea y, además,
   `approve` exige una terminal interactiva propia.
3. **Given** el chat ejecuta un comando, **Then** queda un evento con origen `chat`.
4. **Given** `claude` no está instalado, **Then** `umbra chat` falla con un mensaje claro y el
   resto de umbra funciona.

## Requirements *(mandatory)*

- **FR-001**: `umbra plan` MUST guardar la spec como versión inmutable con hash.
- **FR-002**: Las propuestas MUST validarse contra un contrato antes de crear tareas, en una sola
  transacción.
- **FR-003**: Las dependencias MUST formar un grafo acíclico dentro del proyecto.
- **FR-004**: La edición de tareas MUST usar control optimista por revisión.
- **FR-005**: `umbra run` MUST negarse a ejecutar tareas con dependencias pendientes.
- **FR-006**: `umbra chat` MUST usar el `claude` del usuario con su login y no gestionar
  credenciales.
- **FR-007**: Las reglas del chat MUST denegar `approve`, `reject`, push, merge y edición de la
  política.
- **FR-008**: Cada comando ejecutado desde el chat MUST registrarse con origen `chat`.

## Success Criteria *(mandatory)*

- **SC-001**: Desde el chat se planifica y se lanza una tarea con confirmación.
- **SC-002**: El 100% de los intentos de aprobar desde el chat se deniegan.
- **SC-003**: Ninguna planificación con ciclos deja tareas creadas.

## Assumptions

- El planificador corre en la raíz del repo con permisos de solo lectura.
- La sesión del chat es la de Claude Code interactivo; su historial lo guarda Claude Code.
