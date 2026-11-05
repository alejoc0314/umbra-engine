# Feature Specification: La pantalla principal de `umbra watch`

**Feature Branch**: `013-pantalla-principal`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Pantalla principal de la nueva `umbra watch` (v1.0): lista de
tareas ordenada por atención con progreso por etapas, cabecera viva del proyecto, detalle con
pestañas (situación, línea de tiempo, intentos, evidencia en color, cambios por archivo y
agente en vivo)."

## Contexto

Con los cimientos (spec 012) `watch` es rápido y tiene tema, pero sigue mostrando lo mismo que
antes: una tabla por número, intentos, una línea de specs, situación y registro. Lo que la
persona necesita a diario no está: qué tareas la necesitan primero, cuánto lleva gastado el
proyecto, si el worker está vivo, qué cambió archivo por archivo, qué dijeron las pruebas y qué
está haciendo el agente ahora mismo. Esta entrega convierte `watch` en la consola: todo eso se ve
sin salir, en color y sin perder rendimiento.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lo que me necesita, primero (Priority: P1)

Al abrir `watch`, la lista de tareas está ordenada por atención: arriba las que esperan una
decisión (aprobar, detenidas, fallidas), luego las que trabajan o esperan turno, luego las listas
y en borrador, y al final las hechas y descartadas. Cada fila muestra el progreso por etapas con
una marca por etapa, el costo y el tiempo. La cabecera resume el proyecto: worker vivo o parado,
tareas en cola, gasto acumulado y cuántas necesitan a la persona.

**Why this priority**: es lo que decide qué hacer en los primeros segundos de cada sesión.

**Independent Test**: con tareas en los distintos estados, la primera fila es la que espera
aprobación o está detenida; la cabecera dice «1 te necesita» y el gasto coincide con `umbra
status`.

**Acceptance Scenarios**:

1. **Given** tareas en borrador, trabajando, detenida e integrada, **When** se abre `watch`,
   **Then** el orden es detenida → trabajando → borrador → integrada y la seleccionada por
   defecto es la detenida.
2. **Given** una ejecución en Construir tras Planificar, **When** se mira su fila, **Then** las
   marcas de etapa muestran Planificar hecha y Construir en curso, con su color.
3. **Given** ningún worker vivo y una tarea en cola, **When** se mira la cabecera, **Then** dice
   que el worker está parado (y la situación de la tarea explica cómo arrancarlo).
4. **Given** el gasto del proyecto, **When** se compara con `umbra status`, **Then** coincide.

---

### User Story 2 - Todo el detalle en pestañas, sin salir (Priority: P1)

El panel de detalle de la tarea seleccionada tiene pestañas: **Situación** (como hoy), **Qué ha
pasado** (línea de tiempo), **Intentos**, **Evidencia** (el informe explicado, en color, con la
salida de las pruebas), **Cambios** (archivo por archivo con líneas añadidas y quitadas, y el
parche) y **Agente** (qué está haciendo ahora). Se cambia de pestaña con una tecla y la selección
de tarea se mantiene.

**Why this priority**: evita la ventana modal de evidencia en texto plano y los `git diff` a
mano; aprobar con la evidencia a la vista es el corazón del flujo.

**Independent Test**: con una tarea que espera aprobación, la pestaña Evidencia muestra el
informe con colores y la salida de las pruebas; Cambios lista los archivos con +/− y el parche.

**Acceptance Scenarios**:

1. **Given** una tarea con ejecución, **When** se pulsa la tecla de una pestaña, **Then** la
   pestaña cambia y la tarea seleccionada no.
2. **Given** la pestaña Evidencia, **When** la tarea tiene pruebas registradas, **Then** se ve el
   informe (qué se hizo, cómo se comprobó, qué cambió, costo) y las últimas líneas de la salida
   de las pruebas.
3. **Given** la pestaña Cambios, **When** la ejecución tiene commits, **Then** se listan los
   archivos tocados con líneas añadidas y quitadas y el parche completo (acotado) con colores de
   diff.
4. **Given** la pestaña Evidencia o Cambios, **When** se cambia de tarea, **Then** el contenido se
   recalcula fuera del hilo de la pantalla y mientras tanto se indica que se está preparando.
5. **Given** `e` y `A`, **When** se pulsan, **Then** `e` abre la pestaña Evidencia (ya no una
   ventana) y `A` muestra la confirmación con el mismo informe en color.

---

### User Story 3 - Ver al agente trabajar (Priority: P2)

Mientras un intento está en curso, la pestaña **Agente** muestra en vivo lo que hace: qué archivo
lee, qué edita, qué comando ejecuta y qué va diciendo, en frases cortas. Cuando termina, queda el
relato completo del último intento.

**Why this priority**: hoy el agente es una caja negra durante 4 minutos; verlo trabajar da
confianza y permite cancelar a tiempo.

**Independent Test**: con un intento en curso cuyo registro crece, la pestaña Agente añade
líneas nuevas en menos de 2 segundos sin que la pantalla se congele.

**Acceptance Scenarios**:

1. **Given** un intento en curso, **When** el agente lee, edita o ejecuta algo, **Then** aparece
   una línea nueva («Lee …», «Edita …», «Ejecuta …») en menos de 2 segundos.
2. **Given** un intento terminado, **When** se abre la pestaña Agente, **Then** se ve el relato
   completo de ese intento.
3. **Given** ningún intento en curso ni terminado, **When** se abre la pestaña, **Then** explica
   que no hay actividad de agente para esta tarea.

---

### Edge Cases

- Diffs enormes: el parche se acota (primeros 60 000 caracteres) y se avisa; la lista de archivos
  es completa.
- Registro del agente muy largo: se muestran las últimas 400 líneas; el archivo completo sigue
  en `.umbra/artifacts/`.
- Ejecución cuya carpeta de trabajo ya se borró (integrada): los cambios se calculan desde el
  repositorio con los SHA guardados.
- Terminal estrecha (80 columnas): la lista y el detalle se apilan en vertical.
- Sin ninguna tarea: la cabecera y las pestañas muestran un estado vacío que dice qué hacer.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: La lista MUST ordenarse por atención: necesitan decisión → en marcha → listas y
  borrador → hechas y descartadas; dentro de cada grupo por número.
- **FR-002**: Cada fila MUST mostrar progreso por etapas (una marca por etapa con el color de su
  estado), costo y tiempo total de la última ejecución.
- **FR-003**: La cabecera MUST mostrar worker (vivo/parado), tareas en cola, gasto acumulado y
  cuántas tareas necesitan a la persona; MUST actualizarse con el mismo refresco.
- **FR-004**: El detalle MUST tener las pestañas Situación, Qué ha pasado, Intentos, Evidencia,
  Cambios y Agente, con una tecla para cada una; `e` abre Evidencia.
- **FR-005**: Evidencia MUST mostrar el informe con color y las últimas 60 líneas de la salida de
  pruebas más reciente de la ejecución.
- **FR-006**: Cambios MUST listar archivos con líneas añadidas/quitadas y el parche con colores de
  diff, acotado y con aviso si se recorta.
- **FR-007**: Agente MUST mostrar en vivo el registro del intento en curso (o el último) como
  frases; las líneas nuevas MUST aparecer en menos de 2 s.
- **FR-008**: Los registros de los agentes MUST escribirse en disco mientras corren, no solo al
  terminar.
- **FR-009**: Evidencia, Cambios y Agente MUST calcularse fuera del hilo de la pantalla y solo
  cuando su pestaña está activa o la tarea cambia.
- **FR-010**: Con menos de 100 columnas, lista y detalle MUST apilarse en vertical.
- **FR-011**: Las acciones y teclas de las entregas anteriores MUST seguir funcionando; las
  pruebas existentes MUST seguir pasando.
- **FR-012**: El CHANGELOG MUST registrar los cambios visibles en «Sin publicar».

## Success Criteria *(mandatory)*

- **SC-001**: La tarea que necesita a la persona es siempre la primera fila y la seleccionada por
  defecto al abrir.
- **SC-002**: Un tick de refresco sin cambios sigue por debajo de 5 ms con 50 tareas; con la
  pestaña Agente abierta y un intento en curso, por debajo de 20 ms.
- **SC-003**: Las líneas nuevas del agente aparecen en menos de 2 s.
- **SC-004**: Aprobar desde `watch` se hace con el informe en color a la vista, sin abrir
  ventanas de texto plano.
- **SC-005**: Todas las pruebas anteriores pasan; las instantáneas SVG reflejan la pantalla nueva.

## Assumptions

- «Tiempo» de una fila = desde que entró en cola hasta su último evento (o ahora si sigue).
- El relato del agente se construye desde el registro en bruto (stream-json de Claude Code,
  JSON Lines de Codex); lo que no se reconoce se muestra como texto corto.
- El worker se considera vivo si su bloqueo en la base está vigente.
