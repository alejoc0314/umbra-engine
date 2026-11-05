# Feature Specification: Conversar con umbra desde Telegram

**Feature Branch**: `022-telegram-chat`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Configurar el puente de Telegram para conversar con umbra de forma
convencional acerca de todo lo que necesite que tenga que ver con los proyectos actuales."

## Contexto

El puente (spec 019) atiende botones y respuestas al agente. Lo que falta es poder preguntarle
a umbra, desde el teléfono y en lenguaje normal, por cualquiera de los repos activos: qué pasa,
por qué se detuvo algo, qué costó, qué sigue. `umbra chat` ya sabe responder eso en la
terminal; el puente lo pone al alcance del teléfono, para todos los repos a la vez.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preguntar en lenguaje normal (Priority: P1)

Cualquier mensaje de texto que no sea un comando ni una respuesta al agente es una pregunta a
umbra sobre el proyecto actual: se responde con la misma conversación de `umbra chat` (solo
lectura), hilada entre mensajes; `/nuevo` la reinicia. `/hacer …` permite que la conversación
cambie estado (encolar, aceptar…), con los mismos límites de `umbra chat --allow-changes`
(nunca aprobar, rechazar, push ni merge: para eso están los botones).

**Acceptance Scenarios**:

1. **Given** un mensaje «cómo va el proyecto», **Then** umbra responde con el estado y el
   siguiente mensaje continúa la misma conversación.
2. **Given** `/hacer acepta la tarea 1`, **Then** la conversación puede ejecutar ese comando y
   el teléfono recibe qué ejecutó.
3. **Given** «1 texto» con la tarea 1 sin preguntas pendientes, **Then** es conversación, no
   respuesta al agente.

---

### User Story 2 - Todos los repos con un solo bot (Priority: P1)

Un solo puente atiende el bot para todos los repos registrados con Telegram. `/proyectos` los
lista con cuántas tareas te necesitan; `/usar <nombre>` cambia el proyecto actual; `/estado`
resume qué te necesita. Cada aviso dice de qué repo viene y sus botones actúan sobre ese repo
aunque el actual sea otro.

**Acceptance Scenarios**:

1. **Given** dos repos con el bot, **When** llega un aviso del segundo, **Then** el texto nombra
   el repo y pulsar su botón actúa en ese repo.
2. **Given** `/usar otro`, **Then** las preguntas siguientes van a ese repo.
3. **Given** un segundo `umbra bridge`, **Then** no arranca: ya hay uno atendiendo el bot.

### Edge Cases

- Respuestas largas se parten en varios mensajes.
- Si el chat de umbra falla o caduca, el siguiente mensaje empieza una conversación nueva.
- Repos que se registran después (`umbra init`, `umbra new`) entran solos al puente.

## Requirements *(mandatory)*

- **FR-001**: El texto libre MUST responderse con `umbra chat` (solo lectura) hilado por repo;
  `/hacer` MUST habilitar cambios de estado con los límites de `--allow-changes`.
- **FR-002**: Un único puente MUST atender todos los repos registrados con el mismo bot;
  `/proyectos`, `/usar`, `/estado`, `/nuevo` y `/ayuda` MUST existir.
- **FR-003**: Avisos y botones MUST llevar el nombre del repo y actuar sobre él.
- **FR-004**: «N texto» MUST ser respuesta al agente solo si la tarea N está detenida por
  preguntas.
- **FR-005**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios.

## Success Criteria *(mandatory)*

- **SC-001**: Con el Telegram falso y el `claude` falso, un mensaje libre llama a `umbra chat`
  en el repo actual y el siguiente continúa la sesión; `/usar` cambia el repo.
- **SC-002**: Todas las pruebas anteriores pasan.
