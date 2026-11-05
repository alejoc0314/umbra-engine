# Feature Specification: E1 — Primera tarea real (BUILD → SHIP)

**Feature Branch**: `002-e1-first-task`
**Created**: 2026-10-29
**Status**: Draft
**Input**: Entrega E1 de `docs/design.md`: adaptador de Claude Code, perfil `builder`, rutina
mínima BUILD → SHIP, worktree, tests del proyecto como evidencia, commit, PR y `umbra approve`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ejecutar una tarea hasta un PR (Priority: P1)

Alejandro registra una tarea pequeña (`umbra task add`) y la ejecuta (`umbra run`). Un agente
trabaja en un workspace aislado, los tests del proyecto se ejecutan como evidencia y, si pasan,
umbra hace commit, publica la rama y abre un PR. La ejecución queda esperando su aprobación.

**Why this priority**: Es el recorrido vertical mínimo que demuestra el motor.

**Independent Test**: Con un agente falso y un remoto local, `umbra run` termina en
`WAITING_APPROVAL` con un PR registrado y evidencia de tests ligada al SHA.

**Acceptance Scenarios**:

1. **Given** una tarea aceptada, **When** ejecuta `umbra run 1`, **Then** el comando vuelve de
   inmediato y el trabajo sigue en segundo plano aunque cierre la terminal.
2. **Given** el agente terminó y los tests pasan, **Then** existe una rama `umbra/1-<slug>`
   publicada, un PR abierto y la ejecución está en `WAITING_APPROVAL`.
3. **Given** los tests fallan tras el máximo de intentos, **Then** la ejecución queda `BLOCKED`
   con el comando, el exit code y la salida guardados, y no se abre PR.
4. **Given** el diff del agente borra o modifica un test existente o toca una ruta protegida,
   **Then** la ejecución queda `BLOCKED` por política aunque los tests pasen.
5. **Given** el agente supera su tiempo máximo, **Then** su proceso se detiene y el intento queda
   registrado como agotado.

---

### User Story 2 - Aprobar e integrar (Priority: P1)

Alejandro revisa el resultado con `umbra approve 1`: ve el diff, la evidencia de tests y el costo,
confirma, y umbra fusiona el PR. La ejecución termina en `SUCCEEDED` solo cuando el merge del SHA
aprobado está confirmado.

**Independent Test**: Con el `gh` falso, aprobar fusiona el PR y la ejecución queda `SUCCEEDED`
con el SHA de merge.

**Acceptance Scenarios**:

1. **Given** una ejecución en `WAITING_APPROVAL`, **When** aprueba en una terminal interactiva,
   **Then** el PR se fusiona con squash y la ejecución queda `SUCCEEDED`.
2. **Given** una terminal no interactiva (script, chat), **When** ejecuta `umbra approve`,
   **Then** el comando se niega.
3. **Given** la rama tiene un commit posterior al SHA evaluado, **When** intenta aprobar,
   **Then** se niega e indica que hay que volver a verificar.
4. **Given** rechaza con `umbra reject 1`, **Then** la ejecución queda `CANCELLED` y el PR se
   cierra.

---

### User Story 3 - Recuperarse de fallos (Priority: P1)

Si el proceso que ejecuta el trabajo muere a mitad de una etapa, al relanzarlo retoma la
ejecución sin perder estado ni duplicar ramas, commits o PRs.

**Acceptance Scenarios**:

1. **Given** el worker murió durante BUILD, **When** se vuelve a lanzar, **Then** la ejecución
   continúa y al final existe exactamente un PR.
2. **Given** la creación del PR terminó con error o sin respuesta, **When** se reintenta,
   **Then** umbra busca el PR existente de la rama y lo reutiliza.
3. **Given** `umbra run 1` se ejecuta dos veces, **Then** solo existe una ejecución activa.

---

### User Story 4 - Consultar evidencia y ejecutar comandos registrados (Priority: P2)

`umbra log 1 [-f]` muestra los eventos; `umbra evidence 1` muestra comandos, exit codes, SHAs y
artefactos; `umbra exec test` ejecuta un comando registrado y guarda su resultado.

### Edge Cases

- El agente no está instalado o no tiene sesión: la ejecución queda `FAILED` con el motivo.
- El agente no cambia nada: `BLOCKED` ("sin cambios"), sin commit ni PR.
- No hay comando `test` registrado: `BLOCKED`; no se publica sin evidencia.
- Dos workers a la vez: solo uno obtiene el lease; el otro termina sin hacer nada.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `umbra task add` MUST registrar una tarea aceptada con título, descripción y
  criterios de aceptación; `umbra task list` MUST listarlas.
- **FR-002**: `umbra run` MUST crear una ejecución idempotente por tarea y rutina, y delegar el
  trabajo a un proceso desacoplado de la terminal.
- **FR-003**: Cada tarea MUST trabajar en su propio workspace aislado del repo principal.
- **FR-004**: Cada etapa de agente MUST ejecutarse con límite de tiempo y costo y quedar
  registrada como intento con su perfil, agente, sesión y uso.
- **FR-005**: Tras BUILD, el motor MUST ejecutar el comando `test` registrado y guardar comando,
  exit code y salida ligados al SHA probado.
- **FR-006**: El motor MUST bloquear diffs que borren o modifiquen tests existentes o toquen
  rutas protegidas.
- **FR-007**: SHIP MUST hacer commit, publicar la rama y abrir un PR, cada efecto con clave de
  operación consultada antes de repetirse.
- **FR-008**: `umbra approve` MUST exigir terminal interactiva, verificar que el SHA vigente es
  el evaluado, registrar la aprobación ligada al SHA y fusionar con squash.
- **FR-009**: Una ejecución MUST llegar a `SUCCEEDED` solo tras confirmar el merge.
- **FR-010**: Si el worker muere, el siguiente MUST retomar desde el último checkpoint.
- **FR-011**: `umbra log`, `umbra evidence` y `umbra exec` MUST existir con `--json`.

### Key Entities

- **Perfil**: nombre, agente, roles, modelo, instrucciones, acciones, contrato, límites.
- **Sobre**: datos que el motor entrega al agente y que el agente devuelve (diseño, sección 5).
- Run, Attempt, Artifact, Approval, Usage, Event, Operation, Lease (data-model de E0).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una tarea pequeña en `sandbox/` termina en un PR real en el repo de umbra-engine.
- **SC-002**: Matar el worker a mitad de BUILD y relanzarlo produce exactamente 1 PR.
- **SC-003**: El 100% de las aprobaciones registradas incluyen el SHA aprobado.
- **SC-004**: Ningún PR se abre sin evidencia de tests con exit code 0 sobre su SHA.

## Assumptions

- La rutina de E1 es `quick` (BUILD → SHIP); PLAN, REVIEW y VERIFY llegan en E2.
- Hasta 2 ciclos de corrección en BUILD si los tests fallan.
- Una sola ejecución activa por repo (lease global del worker).
- Las tareas se crean a mano; `umbra plan` llega en E3.
