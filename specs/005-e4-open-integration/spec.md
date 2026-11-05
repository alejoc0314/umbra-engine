# Feature Specification: E4 — Integración abierta de agentes

**Feature Branch**: `005-e4-open-integration`
**Created**: 2026-10-29
**Status**: Draft
**Input**: Entrega E4 de `docs/design.md`: adaptador `script`, `umbra agent add/list/test`,
`umbra profile new/list/show/test` y guía para escribir adaptadores.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Integrar un agente nuevo sin tocar el núcleo (Priority: P1)

Alejandro tiene un agente propio (cualquier ejecutable). Escribe un manifiesto `agent.toml`, lo
registra con `umbra agent add`, lo verifica con `umbra agent test`, crea un perfil que lo usa y lo
pone en una rutina. umbra lo ejecuta como a Claude Code o Codex.

**Acceptance Scenarios**:

1. **Given** un directorio con `agent.toml` válido, **When** ejecuta `umbra agent add <dir>`,
   **Then** el agente queda registrado (global o del proyecto con `--project`).
2. **Given** un agente registrado, **When** ejecuta `umbra agent test <nombre>`, **Then** umbra
   lo corre contra una tarea de ejemplo, valida su salida contra el contrato y lo marca verificado.
3. **Given** un agente registrado sin verificar o cuyo manifiesto cambió, **When** una rutina lo
   usa, **Then** la ejecución falla con "agente no verificado".
4. **Given** el agente de ejemplo de `examples/agents/`, **Then** se integra y revisa una tarea
   real sin modificar `src/umbra/`.

### User Story 2 - Gestionar perfiles (Priority: P2)

1. `umbra profile list` muestra perfiles y de dónde vienen (paquete, global, proyecto).
2. `umbra profile show <nombre>` muestra configuración e instrucciones.
3. `umbra profile new <nombre> --from <base>` crea un perfil del proyecto a partir de otro.
4. `umbra profile test <nombre>` prueba el perfil contra una tarea de ejemplo.

### Edge Cases

- Manifiesto inválido: error con el campo problemático; no se registra nada.
- El ejecutable del agente no existe: `agent list` lo muestra no disponible; `agent test` falla.
- El agente devuelve salida que no valida: `agent test` falla y no lo marca verificado.

## Requirements *(mandatory)*

- **FR-001**: Un agente `script` MUST recibir por stdin un JSON con sobre, perfil, instrucciones,
  esquema de salida y comandos permitidos, y devolver por stdout un JSON con `output`.
- **FR-002**: Los manifiestos MUST validarse antes de registrarse.
- **FR-003**: Un agente registrado MUST pasar `umbra agent test` antes de usarse en una rutina; la
  verificación se invalida si el manifiesto cambia.
- **FR-004**: El núcleo MUST resolver agentes por nombre desde el registro, sin conocer agentes
  concretos.
- **FR-005**: `umbra profile new/list/show/test` MUST existir con `--json`.

## Success Criteria *(mandatory)*

- **SC-001**: Un tercer agente se integra y participa en una rutina sin cambios en `src/umbra/`.
- **SC-002**: El 100% de los agentes registrados sin verificar son rechazados por el motor.

## Assumptions

- Claude Code y Codex son adaptadores integrados, cubiertos por la suite de pruebas.
- Los límites de tiempo se aplican igual a los agentes `script`; su costo es el que reporten
  (o 0 estimado).
