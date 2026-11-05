# Feature Specification: Decidir desde `umbra watch`

**Feature Branch**: `014-decidir-desde-watch`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Diseño A validado en untitled.pen: el panel Situación se convierte
en Decisión cuando la tarea te necesita, con respuestas de una tecla: autorizar un cambio que la
política frenó, responder al agente, integrar (una o todas las que esperan), decidir hallazgos;
y la copia local de la rama base al día tras integrar."

## Contexto

Hasta ahora `watch` mostraba «el agente tiene preguntas» o «cambió un test existente» y no había
ninguna tecla que lo resolviera: la persona tenía que salir a la CLI, editar archivos a mano o
rendirse (la tarea 16 llevaba días detenida por eso). Cada cosa que necesita a la persona pasa a
ser una decisión con teclas concretas, registrada con quién y cuándo.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Autorizar lo que la política frenó (Priority: P1)

Una tarea se detiene porque el agente cambió un test existente o una ruta protegida, y la spec
de verdad exige ese cambio. En `watch`, el panel «Decisión» dice qué ruta frenó y la persona
pulsa `a`: confirma, queda registrado quién lo autorizó, y la tarea sigue desde Construir con ese
permiso (solo para esa tarea y esas rutas).

**Acceptance Scenarios**:

1. **Given** una ejecución detenida por política sobre `tests/x.py`, **When** se pulsa `a` y se
   confirma, **Then** la ejecución vuelve a Construir, el agente recibe el permiso en su sobre y
   el mismo cambio ya no la detiene.
2. **Given** la autorización, **When** se mira el registro, **Then** hay un evento con la persona,
   la tarea y las rutas autorizadas.
3. **Given** otra tarea, **When** cambia la misma ruta, **Then** la política la sigue frenando.

---

### User Story 2 - Responder al agente (Priority: P1)

Una tarea se detiene porque el agente preguntó algo. La persona pulsa `r`, escribe la respuesta
y la tarea sigue desde la etapa donde se detuvo; el agente recibe la respuesta en su sobre y no
vuelve a preguntar lo mismo.

**Acceptance Scenarios**:

1. **Given** una ejecución detenida con preguntas, **When** se responde, **Then** se reintenta
   desde esa etapa y el sobre del agente contiene la respuesta.
2. **Given** una tarea que no está detenida, **When** se intenta responder, **Then** se rechaza con
   un mensaje claro.

---

### User Story 3 - Integrar lo que espera, una o todas (Priority: P2)

Con varias tareas esperando aprobación, la persona puede integrarlas una a una (`A`) o todas en
orden (`T` / `umbra approve --all`); cada una se integra con su propia aprobación y si una falla
se detiene ahí. Tras integrar, la copia local de la rama base queda al día si estaba limpia.

**Acceptance Scenarios**:

1. **Given** dos tareas en espera, **When** se integran todas, **Then** ambas quedan integradas en
   orden y la rama base local avanza.
2. **Given** la copia local con cambios sin guardar o en otra rama, **When** se integra, **Then**
   no se toca y se avisa.

---

### User Story 4 - Decidir hallazgos aunque no frenen (Priority: P3)

Los hallazgos de severidad media que el revisor dejó abiertos se pueden decidir (`h`) en cualquier
tarea con ejecución, no solo cuando bloquean: «no aplica» o «se hará después» (crea una tarea).

### Edge Cases

- Autorizar sin que la política haya frenado nada: se avisa; no hay nada que autorizar.
- Responder a una tarea detenida por otra causa (tests fallando): la respuesta se guarda y se
  reintenta desde donde quedó.
- `approve --all` sin tareas en espera: mensaje claro, nada que integrar.

## Requirements *(mandatory)*

- **FR-001**: `watch` MUST mostrar un panel «Decisión» con las teclas que resuelven la situación
  cuando la tarea está detenida, fallida o espera aprobación.
- **FR-002**: `a` MUST autorizar, solo para esa tarea, las rutas que la política frenó, con
  confirmación, evento con actor y reanudación desde Construir; el comando sombra es
  `umbra task allow <n> <rutas>`.
- **FR-003**: `r` sobre una tarea detenida por preguntas MUST pedir la respuesta y reanudar; el
  agente MUST recibirla en su sobre; comando sombra `umbra task answer <n> "texto"`.
- **FR-004**: `T` y `umbra approve --all` MUST integrar en orden todas las que esperan, con
  confirmación, deteniéndose en la primera que no se pueda.
- **FR-005**: Tras integrar, umbra MUST poner al día la copia local de la rama base si está en esa
  rama y limpia; si no, no la toca.
- **FR-006**: `h` MUST funcionar con hallazgos abiertos aunque no bloqueen; `umbra finding list`
  los muestra.
- **FR-007**: Las teclas MUST aparecer en el pie solo cuando aplican; las acciones existen como
  comando y muestran el equivalente.
- **FR-008**: El CHANGELOG MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Una tarea detenida por política se reanuda con una tecla y una confirmación, sin
  editar archivos a mano.
- **SC-002**: Una tarea detenida por preguntas se reanuda escribiendo la respuesta en `watch`.
- **SC-003**: Dos tareas en espera se integran con una sola confirmación y la base local avanza.
- **SC-004**: Todas las pruebas anteriores pasan.
