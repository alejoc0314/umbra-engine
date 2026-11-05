# Feature Specification: Memoria de decisiones y mapa del repositorio

**Feature Branch**: `015-memoria-contexto`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Memoria de decisiones + CONTEXT.md: cada «no aplica», cada respuesta
al agente y cada autorización valen para siempre; umbra mantiene un mapa del repo que los agentes
leen al arrancar."

## Contexto

Hoy cada decisión de la persona se pierde al terminar la tarea: el revisor vuelve a pedir en la
siguiente tarea lo que ya se marcó como «no aplica», el constructor vuelve a preguntar lo que ya
se respondió, y los agentes arrancan cada tarea sin saber cómo está organizado el repositorio ni
cómo se trabaja en él. Esta entrega convierte esas decisiones en conocimiento del repo y le da a
cada agente un mapa del proyecto en su sobre.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lo que decido una vez vale para siempre (Priority: P1)

Cuando la persona marca un hallazgo como «no aplica», deja uno «para después», responde una
pregunta del agente o autoriza cambiar una ruta protegida, esa decisión queda escrita en
`.umbra/aprendido.md` (versionado con el repo) y los agentes la reciben en su sobre en las
tareas siguientes: el revisor no vuelve a pedirla, el constructor no vuelve a preguntarla.

**Why this priority**: es lo que hace que el sistema mejore con el uso en vez de repetirse.

**Independent Test**: tras marcar «no aplica» un hallazgo en la tarea 1, la tarea 2 del mismo repo
recibe ese hallazgo en su sobre como «ya decidido» y una revisión que lo repite no vuelve a
frenar la tarea.

**Acceptance Scenarios**:

1. **Given** un hallazgo marcado «no aplica» con su motivo, **When** se ejecuta otra tarea,
   **Then** el sobre del revisor contiene ese hallazgo y su motivo bajo «decidido por la persona».
2. **Given** una respuesta dada al agente, **When** otra tarea del mismo repo se ejecuta,
   **Then** el constructor recibe la pregunta y la respuesta en su sobre.
3. **Given** `.umbra/aprendido.md` borrado o desactualizado, **When** se pide reconstruirlo,
   **Then** se regenera a partir del historial de decisiones registradas.
4. **Given** un revisor que repite un hallazgo ya decidido como «no aplica» (mismo texto),
   **When** se juzga la revisión, **Then** ese hallazgo no cuenta como bloqueante.

---

### User Story 2 - Los agentes arrancan sabiendo cómo es el repo (Priority: P1)

umbra mantiene `CONTEXT.md` en la raíz del repositorio: qué es el proyecto, cómo está
organizado, cómo se corre y se prueba, convenciones. Se genera al inicializar (o a petición) y se
actualiza después de cada tarea integrada. Todos los agentes lo reciben en su sobre.

**Why this priority**: el primer intento falla sobre todo por no conocer el proyecto; con mapa,
sube la tasa de «a la primera».

**Independent Test**: con `CONTEXT.md` presente, cualquier intento de cualquier etapa recibe su
contenido en el sobre; tras integrar una tarea, el archivo se actualiza y queda en un commit de
la rama base.

**Acceptance Scenarios**:

1. **Given** un repo sin `CONTEXT.md`, **When** se ejecuta `umbra context build`, **Then** un agente
   de solo lectura lo escribe y no toca ningún otro archivo.
2. **Given** `CONTEXT.md` presente, **When** corre cualquier etapa de agente, **Then** el sobre lo
   incluye (acotado a un tamaño máximo).
3. **Given** una tarea integrada, **When** termina la aprobación, **Then** umbra actualiza
   `CONTEXT.md` si cambió y lo integra en la rama base sin pedir otra aprobación; si falla, no
   frena nada y queda registrado.
4. **Given** la política de rutas protegidas, **When** el cartógrafo escribe `CONTEXT.md`,
   **Then** solo él puede hacerlo: otro agente que lo toque sigue frenado por la política.

---

### User Story 3 - Ver qué ha aprendido umbra (Priority: P3)

Desde `watch` (tecla `m`) y con `umbra memory show` la persona ve lo aprendido: cuántas reglas,
cuáles, y de qué tarea salió cada una.

**Acceptance Scenarios**:

1. **Given** decisiones registradas, **When** se pulsa `m` en `watch`, **Then** el panel derecho
   muestra `aprendido.md`.
2. **Given** ninguna decisión, **When** se consulta, **Then** dice que aún no hay nada aprendido.

### Edge Cases

- Decisiones contradictorias en el tiempo: gana la más reciente y la anterior queda marcada como
  reemplazada.
- `aprendido.md` muy largo: en el sobre entra acotado (las decisiones más recientes primero) y el
  archivo completo sigue en el repo.
- Hallazgos «iguales» con texto ligeramente distinto: se compara el texto normalizado (sin
  números de línea ni espacios dobles).
- `CONTEXT.md` con contenido escrito a mano: el cartógrafo lo conserva y solo actualiza las
  secciones que genera él (marcadas).

## Requirements *(mandatory)*

- **FR-001**: Cada decisión de la persona (hallazgo decidido, respuesta, autorización) MUST
  quedar en `.umbra/aprendido.md`, regenerable desde el historial de eventos.
- **FR-002**: El sobre de todo intento de agente MUST incluir lo aprendido (acotado) y el
  `CONTEXT.md` (acotado) si existen.
- **FR-003**: Un hallazgo cuyo texto normalizado coincide con uno decidido «no aplica» MUST NOT
  contar como bloqueante en ninguna tarea del repo.
- **FR-004**: `umbra context build` MUST generar `CONTEXT.md` con un agente de solo lectura que
  solo puede escribir ese archivo; tras integrar una tarea, umbra MUST intentar actualizarlo sin
  frenar la entrega.
- **FR-005**: `umbra memory show` y la tecla `m` en `watch` MUST mostrar lo aprendido;
  `umbra memory rebuild` MUST regenerarlo.
- **FR-006**: Las pruebas MUST cubrir los escenarios con los agentes falsos; sin red ni modelos.
- **FR-007**: El CHANGELOG MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Un hallazgo decidido «no aplica» no vuelve a frenar ninguna tarea del repo.
- **SC-002**: El 100 % de los intentos de agente reciben `CONTEXT.md` cuando existe.
- **SC-003**: `aprendido.md` se reconstruye idéntico desde los eventos.
- **SC-004**: Todas las pruebas anteriores pasan.

## Assumptions

- `aprendido.md` y `CONTEXT.md` se versionan con git; `aprendido.md` vive en `.umbra/` (ya
  versionado) y lo escribe solo umbra.
- El cartógrafo usa el adaptador de Claude Code con un perfil propio (`cartographer`).
