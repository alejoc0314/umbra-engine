# Feature Specification: Estados de tareas comprensibles

**Feature Branch**: `feat/clear-task-states`
**Created**: 2026-10-29
**Status**: Draft
**Input**: "Entiendo lo que me explican los logs, pero es demasiado técnico. Quiero entender por
qué una tarea está en BLOCKED y qué hacer." Caso real: tarea 3 detenida con
`política: test existente modificado: sandbox/tests/test_calc.py`, cuando el agente solo había
añadido tests nuevos a ese archivo.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Entender por qué una tarea está detenida (Priority: P1)

Alejandro ve una tarea detenida y ejecuta `umbra explain 3`. umbra le dice, en lenguaje llano:
qué pasó, por qué existe esa regla, qué hizo exactamente el agente y qué opciones tiene, cada
una con el comando listo para copiar.

**Acceptance Scenarios**:

1. **Given** una tarea detenida por cualquier motivo conocido (tests que fallan, test
   debilitado, ruta protegida, preguntas del agente, sin cambios, tiempo agotado, hallazgos de
   revisión o verificación, secretos, SHA desactualizado), **Then** `umbra explain` muestra un
   titular, el porqué conceptual, los detalles concretos y al menos una acción con su comando.
2. **Given** una tarea fallida por un problema técnico, **Then** la explicación lo distingue de
   un bloqueo ("no es un problema de tu código") y sugiere reintentar.
3. **Given** una tarea en cualquier otro estado (borrador, lista, en cola, trabajando, en
   pausa, esperando aprobación, integrada, cancelada), **Then** `umbra explain` dice dónde
   está y cuál es el siguiente paso.
4. **Given** ejecuciones antiguas sin código de motivo, **Then** la explicación se deduce del
   texto del motivo.

### User Story 2 - Ver la situación sin leer logs (Priority: P1)

1. `umbra task list` y `umbra status` muestran por tarea una situación en una línea
   ("Detenida: el agente cambió un test existente").
2. `umbra watch` muestra un panel "Situación" con la explicación de la tarea seleccionada y una
   línea de tiempo narrada; `t` alterna al registro técnico.
3. `umbra log` narra los eventos en frases; `--raw` muestra el registro técnico.

### User Story 3 - No bloquear lo legítimo (Priority: P1)

Añadir tests nuevos a un archivo de tests existente está permitido. Se bloquea solo lo que
debilita: borrar el archivo, quitar o cambiar líneas existentes, o añadir saltos (`skip`,
`xfail`, `.only`).

## Requirements *(mandatory)*

- **FR-001**: Cada bloqueo o fallo MUST registrarse con un código estable y detalles
  estructurados, además del texto.
- **FR-002**: `umbra explain <n>` MUST existir con `--json`.
- **FR-003**: Estados y etapas MUST mostrarse con nombres en lenguaje llano.
- **FR-004**: La política MUST permitir solo-añadidos en tests existentes y bloquear borrados,
  modificaciones y saltos añadidos.
- **FR-005**: El chat MUST usar `umbra explain` para responder "¿por qué?".

## Success Criteria *(mandatory)*

- **SC-001**: Para el 100% de los códigos de bloqueo existe una explicación con acción.
- **SC-002**: La tarea del caso real (tests añadidos a un archivo existente) ya no se bloquea.
