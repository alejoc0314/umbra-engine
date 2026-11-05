# Feature Specification: Decidir desde el teléfono (Telegram)

**Feature Branch**: `019-telegram`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Cada decisión llega al teléfono con botones (Autorizar · Ver
cambios · Responder · Integrar · Rechazar) y responder ahí ejecuta el comando."

## Contexto

Con el modo noche y la aprobación por spec, lo que queda para la persona son pocas decisiones,
pero llegan cuando no está frente a la terminal. Un bot de Telegram propio (sin servidor: long
polling desde el mismo repo) lleva cada decisión al teléfono con botones y ejecuta lo que la
persona pulsa, con los mismos comandos y las mismas garantías que la CLI.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cada decisión llega al teléfono con botones (Priority: P1)

Con `[notify.telegram]` configurado (token en una variable de entorno, `chat_id`), cuando una
tarea se detiene, falla o espera aprobación, llega un mensaje con qué pasó y botones: Autorizar
(política), Reintentar, De cero, No aplica (hallazgos), Integrar, Rechazar, Ver cambios. Cuando
una spec completa queda lista, llega un único mensaje con «Integrar la spec».

**Acceptance Scenarios**:

1. **Given** una tarea frenada por la política, **Then** llega el mensaje con el botón
   «Autorizar <ruta>» y «Reintentar».
2. **Given** una tarea que espera aprobación, **Then** llega con «Integrar», «Rechazar» y «Ver
   cambios».
3. **Given** una spec con todas sus historias integradas, **Then** llega un solo mensaje con
   «Integrar la spec» y ninguno por tarea.

---

### User Story 2 - Pulsar un botón ejecuta el comando (Priority: P1)

`umbra bridge` (lo arranca umbra solo al encolar trabajo, uno por repo) lee lo que la persona
pulsa o escribe, ejecuta el comando equivalente con origen `telegram` y responde con el
resultado. Solo atiende al `chat_id` configurado. Escribir «3 texto» (o responder al mensaje de
la tarea) contesta las preguntas del agente.

**Acceptance Scenarios**:

1. **Given** el botón «Autorizar», **When** se pulsa, **Then** la ruta queda autorizada con
   origen `telegram`, la tarea sigue y el teléfono recibe la confirmación.
2. **Given** «Integrar», **Then** la tarea se integra como con `umbra approve`.
3. **Given** un mensaje desde otro chat, **Then** se ignora sin responder.
4. **Given** una respuesta de texto a la pregunta del agente, **Then** queda registrada y la
   tarea sigue.

### Edge Cases

- Sin token en el entorno o sin `chat_id`, nada cambia (ni avisos ni puente).
- Si Telegram no responde, el aviso se pierde sin frenar la ejecución.
- `umbra bridge --stop` para el puente; los botones de un mensaje atendido se retiran.

## Requirements *(mandatory)*

- **FR-001**: Los avisos de `run.blocked`, `run.failed`, `run.waiting_approval` y `spec.ready`
  MUST enviarse a Telegram con botones cuando esté configurado.
- **FR-002**: El puente MUST ejecutar cada botón mediante las operaciones existentes con origen
  `telegram`, registrar quién lo pidió y responder el resultado.
- **FR-003**: El puente MUST ignorar cualquier chat distinto del configurado.
- **FR-004**: El token MUST leerse del entorno; umbra MUST NOT guardarlo.
- **FR-005**: La constitution (VII) MUST admitir la aprobación desde un canal autenticado.
- **FR-006**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios.

## Success Criteria *(mandatory)*

- **SC-001**: Con un Telegram falso, una tarea frenada por política envía el mensaje con
  botones y pulsar «Autorizar» la reanuda con `policy.allowed` de origen `telegram`.
- **SC-002**: «Integrar» desde el teléfono deja la tarea `SUCCEEDED`; «Integrar la spec»
  integra la spec.
- **SC-003**: Todas las pruebas anteriores pasan.
