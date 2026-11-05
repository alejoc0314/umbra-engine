# Feature Specification: E2 — Rutina completa y Codex

**Feature Branch**: `003-e2-full-routine`
**Created**: 2026-10-29
**Status**: Draft
**Input**: Entrega E2 de `docs/design.md`: PLAN, REVIEW y VERIFY; adaptador de Codex; perfiles
distintos por etapa (Claude construye, Codex revisa); ciclos de corrección; pause, resume, cancel
y retry.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rutina `feature` de cinco etapas (Priority: P1)

Alejandro ejecuta una tarea con la rutina `feature`. Un planificador propone el enfoque, el
constructor implementa, un revisor de otro proveedor revisa el diff, un verificador comprueba cada
criterio de aceptación y SHIP abre el PR.

**Independent Test**: Con agentes falsos, la tarea recorre las cinco etapas y queda en
`WAITING_APPROVAL`, con un intento registrado por etapa y el plan disponible para BUILD.

**Acceptance Scenarios**:

1. **Given** una tarea aceptada, **When** ejecuta `umbra run 1 --routine feature`, **Then** se
   ejecutan PLAN, BUILD, REVIEW, VERIFY y SHIP en ese orden.
2. **Given** el revisor reporta un hallazgo de severidad igual o superior a `block_on`, **Then**
   la tarea vuelve a BUILD con el hallazgo como retroalimentación.
3. **Given** los hallazgos persisten tras el máximo de ciclos, **Then** la ejecución queda
   `BLOCKED` con los hallazgos registrados.
4. **Given** el verificador reporta un criterio no cumplido, **Then** vuelve a BUILD igual que en
   REVIEW.
5. **Given** el planificador detecta una ambigüedad material, **Then** la ejecución queda
   `BLOCKED` con sus preguntas, sin gastar en BUILD.

### User Story 2 - Codex como agente (Priority: P1)

El revisor por defecto usa Codex en modo de solo lectura. umbra lanza Codex de forma no
interactiva, valida su salida contra el contrato y registra tokens y costo estimado.

**Acceptance Scenarios**:

1. **Given** el perfil `reviewer-strict` (Codex, solo lectura), **Then** Codex se ejecuta con
   sandbox de solo lectura y no puede modificar el workspace.
2. **Given** Codex devuelve una salida que no valida contra el contrato, **Then** la etapa
   falla con el motivo y no avanza.

### User Story 3 - Controlar una ejecución (Priority: P2)

1. `umbra pause N` detiene la ejecución en el siguiente punto seguro; `umbra resume N` la retoma.
2. `umbra cancel N` la cancela: cierra el PR si existe y limpia el workspace.
3. `umbra retry N --from build` reintenta una ejecución bloqueada desde una etapa, con un nuevo
   presupuesto de ciclos y conservando el historial.

### Edge Cases

- Un perfil pide una acción que la política del proyecto no permite: se usa la intersección.
- REVIEW sin hallazgos y VERIFY sin criterios: avanzan.
- Cancelar durante un bloque de agente: el bloque termina y luego se respeta la cancelación.

## Requirements *(mandatory)*

- **FR-001**: La rutina `feature` MUST ejecutar PLAN → BUILD → REVIEW → VERIFY → SHIP.
- **FR-002**: El resultado de PLAN MUST llegar a BUILD como contexto.
- **FR-003**: Hallazgos de REVIEW o VERIFY con severidad ≥ `block_on` MUST devolver la tarea a
  BUILD hasta `max_fix_cycles` veces y luego bloquear.
- **FR-004**: Los hallazgos MUST guardarse con severidad, archivo, línea y mensaje.
- **FR-005**: El adaptador de Codex MUST ejecutar sin interfaz, con sandbox derivado de las
  acciones del perfil, y validar la salida contra el contrato.
- **FR-006**: Los permisos efectivos MUST ser la intersección entre perfil y política.
- **FR-007**: `pause`, `resume`, `cancel` y `retry --from` MUST existir con efectos en el
  siguiente punto seguro y quedar registrados como eventos.
- **FR-008**: Los perfiles por defecto MUST asignar un proveedor distinto al revisor que al
  constructor.

## Success Criteria *(mandatory)*

- **SC-001**: En un smoke test real, Claude construye y Codex revisa una tarea de `sandbox/`.
- **SC-002**: Un test que falla de verdad deja la tarea en `BLOCKED` con stderr y exit code.
- **SC-003**: Ninguna etapa de solo lectura modifica el workspace.

## Assumptions

- `feature` pasa a ser la rutina por defecto; `quick` se mantiene.
- El costo de Codex se registra como estimado (tokens, sin tarifa) porque el login de ChatGPT no
  devuelve importes.
