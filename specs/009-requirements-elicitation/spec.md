# Feature Specification: Levantamiento de requisitos dentro de umbra

**Feature Branch**: `feat/requirements-elicitation`
**Created**: 2026-10-29
**Status**: Draft
**Input**: "Quiero que umbra sea también levantador de requisitos usando SDD, sin crear tareas a
mano ni salir a Spec Kit por separado." Decisiones previas del usuario: Spec Kit es el motor
(specify → clarify → plan → tasks) y umbra orquesta; una tarea por historia de usuario; puntos de
control humanos tras la spec y tras el plan; chat propio dentro de umbra (no una sesión de
Claude Code); preguntas con opciones; misma pantalla desde `umbra spec new "idea"` y desde
`watch`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Convertir una idea en una spec conversando (Priority: P1)

El usuario escribe `umbra spec new "quiero exportar facturas a PDF"` (o pulsa `s` en `watch`).
Se abre una pantalla de conversación dentro de umbra. El asistente lee el código del proyecto,
redacta la spec con Spec Kit y hace las preguntas que falten como opciones que se eligen con el
teclado (más «otra respuesta» libre). Al terminar, umbra muestra un resumen de la spec y pide
aprobarla, pedir cambios o descartarla.

**Why this priority**: es el hueco actual: hoy umbra solo arranca si ya existe una spec escrita.
Por sí sola ya entrega valor: una spec revisada en `specs/NNN-*`, lista para `umbra plan`.

**Independent Test**: con un repo que tiene Spec Kit, ejecutar `umbra spec new "idea"`,
responder las preguntas y aprobar; queda `specs/NNN-*/spec.md` y nada fuera de `specs/` cambió.

**Acceptance Scenarios**:

1. **Given** un repo con Spec Kit inicializado, **When** el usuario ejecuta
   `umbra spec new "idea"`, **Then** se abre la conversación y en menos de 2 s se ve actividad
   (qué está leyendo o haciendo el asistente), aunque el primer texto tarde más.
2. **Given** que el asistente necesita una decisión, **When** pregunta, **Then** la pregunta se
   muestra con opciones numeradas, la recomendada primero, y una opción de respuesta libre.
3. **Given** la spec redactada y aclarada, **When** termina la fase, **Then** umbra se detiene y
   muestra el punto de control «Aprobar spec / Pedir cambios / Descartar»; el asistente no
   avanza solo al plan.
4. **Given** «Pedir cambios» con un comentario, **When** se envía, **Then** el asistente ajusta
   la spec y vuelve al mismo punto de control.

---

### User Story 2 - Pasar de la spec aprobada a tareas sin escribirlas (Priority: P2)

Tras aprobar la spec, umbra lanza el plan técnico (Spec Kit plan) y se detiene en un segundo
punto de control. Al aprobar el plan, umbra genera el desglose (Spec Kit tasks) y crea una tarea
de umbra en borrador por cada historia de usuario, en orden de prioridad.

**Why this priority**: cierra el ciclo idea → tareas listas para `accept`/`run` sin trabajo
manual; depende de la historia 1.

**Independent Test**: partiendo de una spec aprobada con 3 historias, aprobar el plan y comprobar
que aparecen 3 tareas en borrador con título, criterios de aceptación y contexto técnico.

**Acceptance Scenarios**:

1. **Given** una spec aprobada, **When** el plan termina, **Then** umbra muestra un resumen
   (enfoque, archivos que tocará, riesgos) y el punto de control «Aprobar plan / Pedir cambios».
2. **Given** el plan aprobado, **When** se generan las tareas, **Then** hay una tarea por
   historia (P1, P2…), cada una con: título de la historia, escenarios de aceptación como
   criterios, y como contexto para el agente constructor el detalle del plan y los pasos de
   Spec Kit de esa historia.
3. **Given** que la historia P2 depende de la P1, **When** se crean las tareas, **Then** la
   dependencia queda registrada y se valida que no haya ciclos.
4. **Given** las tareas creadas, **When** el usuario mira `umbra task list` o `watch`, **Then**
   están en borrador y siguen necesitando `accept`, como hoy.

---

### User Story 3 - Ver el avance por requisito (Priority: P3)

El usuario quiere saber cuánto de una spec está hecho, no solo el estado de cada tarea.

**Why this priority**: da la vista de producto («la exportación a PDF va 2 de 3») y el costo por
requisito; útil cuando ya hay varias specs en marcha.

**Independent Test**: con una spec de 3 historias y una tarea hecha, `umbra status` y `watch`
muestran «1 de 3» para esa spec y su costo acumulado (conversación + tareas).

**Acceptance Scenarios**:

1. **Given** tareas nacidas de una spec, **When** se abre `status` o `watch`, **Then** se ven
   agrupadas por spec con «n de m historias hechas».
2. **Given** una tarea, **When** se usa `umbra explain`, **Then** dice de qué historia y qué
   requisitos (FR-xxx) de la spec viene.

---

### User Story 4 - Retomar y cambiar una spec (Priority: P4)

El usuario cierra la conversación a medias o vuelve semanas después a cambiar la spec.

**Why this priority**: evita perder el contexto y avisa cuando las tareas ya no reflejan la spec;
no bloquea el uso básico.

**Independent Test**: cerrar la conversación en la fase de aclaración, ejecutar
`umbra spec resume NNN` y comprobar que sigue en la misma fase con el historial; editar una
historia de una spec con tareas y ver el aviso de tareas desalineadas.

**Acceptance Scenarios**:

1. **Given** una conversación cerrada a medias, **When** el usuario la retoma, **Then** sigue en
   la misma fase con el historial anterior.
2. **Given** una spec con tareas ya creadas, **When** cambia una historia, **Then** umbra marca
   esas tareas como «desalineadas» y propone actualizarlas; no las cambia sin confirmación.

---

### Edge Cases

- `claude` no instalado o sin sesión iniciada: explicar qué pasa y qué hacer, sin abrir la
  pantalla.
- El repo no tiene Spec Kit inicializado: umbra explica qué falta y ofrece inicializarlo; solo
  lo hace si el usuario confirma, nunca en silencio.
- El asistente intenta escribir fuera de `specs/` o encadenar fases solo: umbra lo impide; cada
  fase termina en su punto de control.
- La spec no tiene historias de usuario reconocibles: umbra lo dice y ofrece el camino actual
  (`umbra plan`, que propone tareas con un agente).
- Se supera el límite de costo de la conversación: se pausa y se pregunta si continuar.
- Dos conversaciones sobre la misma spec a la vez: la segunda se niega y explica por qué.
- Se cierra la terminal en mitad de una respuesta: lo ya escrito en `specs/` se conserva y la
  conversación se puede retomar.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `umbra spec new "idea"` y la tecla `s` en `watch` MUST abrir la misma pantalla de
  conversación dentro de umbra, sin lanzar una sesión interactiva de Claude Code.
- **FR-002**: La conversación MUST usar el `claude` y el login del propio usuario; umbra no
  gestiona credenciales.
- **FR-003**: El asistente MUST poder leer el proyecto y MUST NOT poder escribir fuera de
  `specs/` (salvo el marcador `.specify/feature.json` que usa Spec Kit), ejecutar comandos de
  estado de umbra, hacer push ni merge.
- **FR-004**: Las fases MUST ser las de Spec Kit (specify, clarify, plan, tasks) y umbra MUST
  controlar el paso entre ellas: cada fase la lanza umbra, no el asistente.
- **FR-005**: MUST haber puntos de control humanos obligatorios tras la spec y tras el plan, con
  «Aprobar / Pedir cambios / Descartar».
- **FR-006**: Las preguntas del asistente MUST mostrarse como opciones elegibles con el teclado,
  con la recomendada primero y respuesta libre siempre disponible.
- **FR-007**: La pantalla MUST mostrar actividad (herramientas en uso, fase actual, costo
  acumulado) mientras el asistente trabaja.
- **FR-008**: Al aprobar el plan, umbra MUST crear una tarea en borrador por historia de usuario,
  en orden de prioridad, con criterios de aceptación tomados de los escenarios y el contexto
  técnico del plan y de los pasos de Spec Kit de esa historia.
- **FR-009**: La creación de tareas MUST validar dependencias (sin ciclos) y ser todo o nada,
  como `umbra plan` hoy.
- **FR-010**: Cada tarea MUST guardar de qué spec, versión e historia viene y qué FR cubre.
- **FR-011**: `status`, `watch` y `explain` MUST mostrar el avance por spec («n de m») y el costo
  por spec (conversación + tareas).
- **FR-012**: Una conversación MUST poder retomarse (`umbra spec resume`) en la fase donde quedó.
- **FR-013**: Si una spec cambia después de crear tareas, umbra MUST marcar las tareas afectadas
  como desalineadas y MUST NOT modificarlas sin confirmación.
- **FR-014**: Cada fase, punto de control y decisión MUST registrarse como evento con origen
  (`cli` o `watch`).
- **FR-015**: Los archivos de la spec MUST viajar en el trabajo de la primera tarea creada a
  partir de ella, de modo que la spec y el código que la cumple se revisen en el mismo PR; umbra
  MUST NOT abrir PRs solo de spec.
- **FR-016**: `umbra plan spec.md` MUST seguir funcionando igual para specs escritas a mano.

### Key Entities

- **Conversación de requisitos**: idea inicial, carpeta de la spec, fase actual, sesión del
  asistente (para retomar), costo acumulado, estado (abierta, en punto de control, terminada,
  descartada).
- **Spec**: ya existe (versión inmutable por contenido); se añade la carpeta `specs/NNN-*` de la
  que viene.
- **Historia**: identificador y prioridad dentro de la spec, escenarios, FR que cubre; enlaza con
  la tarea de umbra que la implementa.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: De una idea de una línea a tareas en borrador sin salir de umbra ni escribir
  tareas a mano, con exactamente dos puntos de control antes de las tareas.
- **SC-002**: El 100 % de las tareas creadas así se pueden rastrear a su historia y a sus FR.
- **SC-003**: Tras pulsar enviar, se ve actividad en menos de 2 s en el 95 % de los turnos.
- **SC-004**: Retomar una conversación cerrada a medias no pierde ninguna respuesta ya dada.
- **SC-005**: Ningún archivo fuera de `specs/` y `.specify/feature.json` cambia durante una
  conversación de requisitos.

## Assumptions

- El proyecto destino usa Spec Kit con su integración de Claude (skills `speckit-*`); umbra no
  reimplementa sus plantillas.
- La conversación usa `claude -p` con entrada y salida en streaming JSON, un proceso por
  conversación (validado en el spike del 2026-10-29).
- Un usuario a la vez; el modo equipo queda para después.
- Que esta pantalla reemplace a `umbra chat` queda fuera de alcance.
- Las cuatro historias se entregan juntas en un solo PR contra `main`.

## Clarifications

### Session 2026-10-29

- Q: ¿Cómo llegan los archivos de la spec al repo? → A: En el PR de la primera tarea.
- Q: ¿Qué hace umbra si falta Spec Kit? → A: Ofrece inicializarlo y pide confirmación.
- Q: ¿Alcance del primer PR? → A: Las cuatro historias en un solo PR.
- El límite de costo por conversación sale de la configuración del proyecto, con un valor por
  defecto razonable.
