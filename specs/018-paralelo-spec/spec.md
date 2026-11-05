# Feature Specification: Paralelismo, aprobación por spec y modo noche

**Feature Branch**: `018-paralelo-spec`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Varias tareas a la vez (worktree propio cada una); las tareas de
una spec se integran solas en la rama de la spec cuando pasan tests, revisión y política; una
sola aprobación humana al final (PR único a `main`). `umbra night` deja todo encolado y a la
mañana espera la bandeja."

## Contexto

Hoy umbra trabaja una tarea a la vez por repositorio y pide aprobación por cada una: la persona
es el cuello de botella del bucle. Con 3 a 5 repos activos y specs de 3 a 6 historias, lo que
hace falta es poder dejar correr: que las tareas de una spec avancen solas (en paralelo cuando no
dependen entre sí), se integren en la rama de la spec al pasar todas las comprobaciones, y la
persona decida una sola vez sobre la spec completa, con toda la evidencia.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Varias tareas a la vez (Priority: P1)

Con `[blocks] parallel = 2` en `project.toml`, el worker atiende hasta dos ejecuciones a la vez,
cada una en su worktree, respetando las dependencias entre tareas.

**Acceptance Scenarios**:

1. **Given** dos tareas aceptadas e independientes y `parallel = 2`, **When** se encolan,
   **Then** sus intentos de Construir se solapan en el tiempo y ambas terminan como siempre.
2. **Given** `parallel = 1` (o sin configurar), **Then** todo se comporta como hoy.

---

### User Story 2 - Las tareas de una spec se integran solas en su rama (Priority: P1)

Una tarea que pertenece a una spec trabaja sobre la rama `spec/<carpeta>` (creada desde la base
si no existe). Al pasar tests, revisión, verificación y política, umbra abre el PR contra esa
rama y lo integra sin pedir aprobación; la tarea queda hecha y el piloto automático arranca las
siguientes que ya pueden ir.

**Acceptance Scenarios**:

1. **Given** una spec con dos historias encadenadas, **When** se ejecutan, **Then** cada una se
   integra sola en `spec/<carpeta>` y la segunda parte de lo que integró la primera.
2. **Given** una tarea sin spec, **Then** sigue pidiendo aprobación como hoy.

---

### User Story 3 - Una sola aprobación por spec (Priority: P1)

Cuando todas las historias de la spec están integradas en su rama, umbra abre el PR
`spec/<carpeta> → base`, avisa una vez y la spec queda «espera tu aprobación».
`umbra approve --spec <carpeta>` (o la tecla `I` en `watch` sobre cualquier tarea de la spec)
integra la spec completa en la base.

**Acceptance Scenarios**:

1. **Given** la última historia integrada en la rama de la spec, **Then** existe el PR de la spec
   y la lista de specs lo muestra como «espera tu aprobación».
2. **Given** ese PR, **When** la persona aprueba la spec, **Then** la base contiene todos los
   cambios y la spec aparece integrada.

---

### User Story 4 - Modo noche (Priority: P2)

`umbra night [--spec <carpeta>]` acepta todos los borradores (de esa spec o de todas), encola
las que ya pueden ir y deja que el piloto automático encadene el resto. A la mañana, la persona
encuentra specs listas para aprobar o tareas detenidas con su motivo.

**Acceptance Scenarios**:

1. **Given** una spec con sus tareas en borrador, **When** `umbra night --spec`, **Then** todas
   quedan aceptadas, las que pueden arrancan y, al integrarse, arrancan las siguientes.

### Edge Cases

- Una tarea de spec que se detiene (tests, política, hallazgos) sigue necesitando a la persona:
  avisa como hoy. Lo que no avisa es cada integración en la rama de la spec.
- Si la rama de la spec recibe cambios mientras una tarea trabaja, la tarea los trae antes de
  construir (como hoy con la base) y el agente resuelve conflictos.
- `umbra approve --spec` exige terminal interactiva y que el PR no tenga conflictos.

## Requirements *(mandatory)*

- **FR-001**: El worker MUST atender hasta `[blocks] parallel` ejecuciones a la vez (1 por
  defecto), cada una con su propio lease y conexión.
- **FR-002**: Cada ejecución MUST recordar su rama base; las tareas con spec usan
  `spec/<carpeta>`, creada desde la base si no existe.
- **FR-003**: Publicar sobre una rama de spec MUST integrar el PR sin aprobación humana una vez
  pasadas todas las etapas; la ejecución termina `SUCCEEDED` y la tarea `done`.
- **FR-004**: Al integrarse la última historia de una spec, umbra MUST abrir el PR de la spec a
  la base y dejarla «espera tu aprobación», con un solo aviso.
- **FR-005**: `umbra approve --spec` y la tecla `I` en `watch` MUST integrar la spec completa.
- **FR-006**: `umbra night [--spec]` MUST aceptar los borradores y encolar lo que pueda ir.
- **FR-007**: El piloto automático MUST arrancar tantas tareas como quepan en `parallel`.
- **FR-008**: La constitution MUST enmendarse (1.2.0): paralelismo dentro del alcance y la
  aprobación humana sobre la spec completa.

## Success Criteria *(mandatory)*

- **SC-001**: Dos tareas independientes con `parallel = 2` solapan sus intentos de Construir.
- **SC-002**: Una spec de dos historias llega, sin intervención, a «espera tu aprobación» con
  ambas integradas en `spec/<carpeta>`; `umbra approve --spec` deja todo en la base.
- **SC-003**: Todas las pruebas anteriores pasan.
