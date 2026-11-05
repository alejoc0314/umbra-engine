# Feature Specification: Cimientos de la nueva `umbra watch`

**Feature Branch**: `012-cimientos-watch`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Cimientos de la nueva `umbra watch` (v1.0): la vista en vivo pasa a ser
la consola principal de umbra y necesita una base sólida antes de las pantallas nuevas: refresco
rápido y sin bloquear, horas en hora local, tema propio «umbra» con los integrados (dracula) aún
disponibles, pantallas dentro de la misma app en vez de una app anidada, un solo aviso por
transición, y agentes que no hereden los plugins globales del usuario."

## Contexto

`umbra watch` es donde quien usa umbra gestiona casi todo. Hoy es un visor correcto pero con una
base que no aguanta lo que viene (pestañas, diff, agente en vivo, conversación de spec dentro): el
refresco consulta la base entera cada segundo en el hilo de la interfaz, reconstruye la tabla si
cambia una celda, muestra las horas en UTC (5 horas adelantadas para quien usa umbra), avisa tres
veces de lo mismo, no tiene tema ni estilos propios y abre la conversación de spec como otra
aplicación encima (parpadeo, pierde el tema). Además, los agentes que umbra lanza heredan los
plugins y ganchos globales de Claude Code del usuario, lo que altera su comportamiento.

Esta entrega no añade pantallas ni acciones: deja la base para que las siguientes (pantalla
principal, decidir desde watch, spec dentro de watch, pulido 1.0) sean seguras y rápidas.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - La vista responde al instante aunque el proyecto crezca (Priority: P1)

Quien usa umbra abre `watch` en un proyecto con decenas de tareas y cientos de eventos. Mover el
cursor, cambiar de tarea y dejar la pantalla abierta horas no produce lag ni parpadeo: la tabla
conserva el scroll y la selección, y lo que no cambió no se vuelve a pintar.

**Why this priority**: es el cimiento de todo lo demás; sin él cada pantalla nueva empeora la
experiencia y repite las regresiones de v0.1.1 y v0.6.0.

**Independent Test**: con una base sembrada de 50 tareas y 2 000 eventos, un ciclo de refresco
termina en menos de 5 ms cuando nada cambió y en menos de 50 ms cuando cambió una ejecución; ni
git ni lecturas de archivos corren en el hilo de la interfaz.

**Acceptance Scenarios**:

1. **Given** `watch` abierto con 50 tareas, **When** pasa un ciclo de refresco sin cambios en la
   base, **Then** no se ejecuta ninguna consulta de datos de tareas ni se repinta la tabla.
2. **Given** una ejecución en marcha, **When** llega un evento nuevo, **Then** solo se actualizan las
   celdas y líneas que cambiaron y el cursor y el scroll se mantienen.
3. **Given** una tarea detenida por política, **When** se selecciona, **Then** la reevaluación de la
   política (que usa git) no congela la interfaz: ocurre fuera del hilo de la pantalla y la vista
   se completa cuando termina.
4. **Given** `watch` abierto, **When** se abre la evidencia o la aprobación de una tarea, **Then**
   la pantalla no se congela mientras se calcula (muestra un indicador de carga).

---

### User Story 2 - Las horas son las de quien mira (Priority: P1)

Todo tiempo que muestra umbra (registro, intentos, evidencia, avisos) está en la hora local de la
máquina, y cuando una ejecución abarca más de un día se ve también la fecha.

**Why this priority**: hoy el registro va 5 horas adelantado para el usuario; es una mentira
visible en cada pantalla.

**Independent Test**: con la zona horaria de la máquina fijada a −05:00 y un evento guardado a
las 22:17 UTC, el registro muestra 17:17.

**Acceptance Scenarios**:

1. **Given** un evento guardado en UTC, **When** se muestra en `watch` o en `umbra log`, **Then** la
   hora corresponde a la zona horaria local.
2. **Given** una ejecución cuyos eventos cruzan la medianoche local, **When** se muestra su
   registro, **Then** cada cambio de día se indica (fecha en la línea o separador de día).
3. **Given** la salida `--json`, **When** se lee, **Then** las marcas de tiempo siguen siendo las
   guardadas (UTC, ISO 8601): no cambian para no romper scripts.

---

### User Story 3 - Un tema propio sin perder el elegido (Priority: P2)

`watch` trae un tema «umbra» (oscuro y claro) con colores coherentes por estado (detenida, falló,
espera aprobación, trabajando, integrada) y por etapa. Los temas integrados, incluido «dracula»,
siguen en la paleta y el tema elegido se recuerda entre sesiones como hoy. Los estilos viven en
un archivo propio, no mezclados en el código.

**Why this priority**: la pulida visual de las siguientes entregas necesita una paleta con nombre
para cada cosa; sin ella cada pantalla inventa sus colores.

**Independent Test**: abrir `watch` con el tema «dracula» guardado lo respeta; cambiar a «umbra»
desde la paleta aplica los colores propios y queda guardado para la próxima apertura.

**Acceptance Scenarios**:

1. **Given** una preferencia guardada con el tema «dracula», **When** se abre `watch`, **Then** se
   ve con dracula (nada cambia para quien ya lo usa).
2. **Given** `watch` abierto, **When** se elige «umbra» o «umbra-claro» en la paleta, **Then** la
   pantalla cambia al instante y la preferencia se guarda.
3. **Given** cualquier tema, **When** se mira una tarea detenida, una que espera aprobación y una
   integrada, **Then** cada estado tiene un color distinto y consistente en la tabla, el panel de
   situación y el registro.
4. **Given** una instalación nueva sin preferencia, **When** se abre `watch`, **Then** el tema por
   defecto es «umbra».

---

### User Story 4 - La conversación de spec se abre dentro de `watch` (Priority: P2)

Al pulsar `s`, la conversación de spec aparece como una pantalla dentro de `watch` (misma
aplicación, mismo tema), sin parpadeo ni cambio de terminal; al cerrarla se vuelve a la vista
principal, que siguió al día. `umbra spec new` y `umbra spec resume` siguen funcionando igual desde
la terminal.

**Why this priority**: elimina la app anidada, que es frágil (dos apps en un mismo bucle) y rompe
la continuidad visual; es prerrequisito de la entrega «spec dentro de watch».

**Independent Test**: desde `watch`, `s` abre la conversación con el tema activo; cerrarla devuelve
la vista principal con la tabla actualizada; las pruebas actuales de la conversación siguen
pasando.

**Acceptance Scenarios**:

1. **Given** `watch` con el tema «dracula», **When** se pulsa `s` y se escribe una idea, **Then** la
   conversación se muestra con el mismo tema y sin que la pantalla se restaure a la terminal.
2. **Given** la conversación abierta dentro de `watch`, **When** se pulsan teclas de `watch` (q, a,
   r…), **Then** no actúan sobre `watch` ni lo cierran: solo la conversación recibe teclas.
3. **Given** la conversación abierta, **When** una tarea cambia a «espera tu aprobación», **Then**
   el aviso de `watch` se ve igualmente.
4. **Given** la conversación abierta, **When** se cierra, **Then** el bloqueo de la conversación se
   libera y la vista principal está al día.
5. **Given** `umbra spec new "idea"` desde la terminal, **When** se ejecuta, **Then** abre la misma
   conversación (sin `watch` detrás) y se comporta como hoy.

---

### User Story 5 - Un solo aviso por cosa que pasa (Priority: P3)

Cuando una tarea necesita a la persona (espera aprobación, se detuvo, falló), llega un único
aviso según la política configurada: dentro de `watch` cuando está abierto, aviso del sistema
cuando no lo está; la campana es opcional.

**Why this priority**: hoy llegan tres avisos por transición; molesta y hace ruido. Es pequeño
pero visible.

**Independent Test**: con `watch` abierto, una transición a «espera aprobación» produce un aviso
en pantalla y ninguno del sistema; con `watch` cerrado, uno del sistema.

**Acceptance Scenarios**:

1. **Given** `watch` abierto, **When** una tarea pasa a BLOCKED, **Then** aparece un aviso en
   `watch` y no se envía aviso del sistema.
2. **Given** `watch` cerrado, **When** una tarea pasa a WAITING_APPROVAL, **Then** se envía un
   aviso del sistema (como hoy).
3. **Given** `[notify] bell = false` en la configuración, **When** llega un aviso en `watch`,
   **Then** no suena la campana.

---

### User Story 6 - Los agentes no heredan la configuración global del usuario (Priority: P3)

Los agentes que umbra lanza (constructor, planificador, verificador, resumen, conversación de spec
y chat programático) trabajan solo con las instrucciones de umbra y la configuración del proyecto,
no con los plugins ni los ganchos globales de Claude Code de quien usa umbra.

**Why this priority**: hoy el constructor recibe instrucciones ajenas (p. ej. «modo perezoso» y
protocolos de memoria de plugins personales), lo que altera el trabajo y la reproducibilidad.

**Independent Test**: con un plugin global que inyecta un texto reconocible, el registro de un
intento de BUILD no contiene ese texto.

**Acceptance Scenarios**:

1. **Given** plugins y ganchos globales instalados, **When** umbra lanza un agente, **Then** el
   transcript del agente no contiene sus instrucciones.
2. **Given** `.claude/settings.json` del proyecto (con `trust_repo_agent_config`), **When** umbra
   lanza un agente, **Then** la configuración del proyecto sí se aplica, como hoy.

---

### Edge Cases

- La base de datos crece (miles de eventos): el refresco sigue por debajo del objetivo porque solo
  lee lo nuevo y solo recalcula lo que cambió.
- La zona horaria de la máquina cambia mientras `watch` está abierto: se acepta que las horas se
  recalculen en el siguiente ciclo.
- El tema guardado ya no existe (p. ej. se eliminó de Textual): se usa «umbra» y se avisa una vez.
- Se pulsa `s` cuando ya hay una conversación abierta dentro de `watch`: no se abre otra; se
  enfoca la existente.
- `watch` abierto en dos terminales a la vez: cada una avisa en pantalla; el aviso del sistema no
  se envía mientras haya alguna abierta.
- Terminal sin color verdadero: el tema «umbra» sigue siendo legible en 256 colores.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `watch` MUST detectar si la base cambió antes de recalcular nada; sin cambios no
  consulta datos de tareas ni repinta.
- **FR-002**: Las lecturas de datos, git y archivos para la vista MUST ocurrir fuera del hilo de
  la interfaz; la interfaz muestra un indicador mientras espera.
- **FR-003**: La tabla de tareas MUST actualizar solo las celdas que cambian; añadir o quitar
  filas no pierde el cursor ni el scroll.
- **FR-004**: Un ciclo de refresco sin cambios con 50 tareas y 2 000 eventos MUST terminar en
  menos de 5 ms; con cambios, en menos de 50 ms (medido en la prueba automática).
- **FR-005**: Toda hora mostrada a la persona MUST estar en hora local; el registro MUST indicar
  el cambio de día. La salida `--json` MUST conservar las marcas guardadas.
- **FR-006**: `watch` MUST ofrecer los temas «umbra» (oscuro) y «umbra-claro» además de los
  integrados; el elegido se guarda y se respeta al abrir; por defecto «umbra».
- **FR-007**: Cada estado de tarea/ejecución y cada etapa MUST tener un color con nombre, usado de
  forma consistente en tabla, situación, registro y modales.
- **FR-008**: Los estilos de `watch` MUST vivir en un archivo de estilos propio, no en cadenas
  dentro del código.
- **FR-009**: La conversación de spec MUST abrirse como pantalla dentro de `watch`, con el mismo
  tema y sin suspender la terminal; `umbra spec new/resume` MUST seguir abriéndola por sí solos.
- **FR-010**: Mientras una pantalla está encima, las teclas de la vista principal MUST NOT
  actuar; el refresco de fondo MUST seguir para que los avisos lleguen.
- **FR-011**: Por cada transición que necesita a la persona MUST llegar un solo aviso: en pantalla
  si hay un `watch` abierto, del sistema si no; `[notify] desktop` y `[notify] bell` lo controlan.
- **FR-012**: Los agentes lanzados por umbra MUST NOT cargar la configuración global del usuario
  de Claude Code (plugins, ganchos); la del proyecto se mantiene según la política actual.
- **FR-013**: Ninguna acción ni tecla existente cambia; las pruebas actuales de `watch` y de la
  conversación de spec MUST seguir pasando.
- **FR-014**: No se añade ninguna dependencia de ejecución; para instantáneas de pantalla se
  permiten dependencias solo de desarrollo.
- **FR-015**: El CHANGELOG MUST registrar los cambios visibles en «Sin publicar».

### Key Entities

- **Vista (estado de pantalla)**: lo que `watch` muestra, derivado de la base; se recalcula solo
  cuando cambia la versión de datos.
- **Tema**: conjunto de colores con nombre (por estado y por etapa) que toda pantalla consume.
- **Preferencia de la persona**: tema elegido (y en adelante otras), fuera del repositorio.
- **Política de avisos**: configuración del proyecto que decide dónde avisar.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un ciclo de refresco sin cambios con 50 tareas y 2 000 eventos termina en menos de
  5 ms; con cambios, en menos de 50 ms.
- **SC-002**: Al navegar con el cursor por 50 tareas durante 10 s no se pierde ni el scroll ni la
  selección y no se ejecuta ninguna consulta por tarea no seleccionada.
- **SC-003**: El 100 % de las horas visibles coincide con la hora local de la máquina.
- **SC-004**: Quien tenía «dracula» lo sigue viendo; quien no eligió nada ve «umbra».
- **SC-005**: Abrir y cerrar la conversación de spec desde `watch` no produce ningún restablecimiento
  de terminal (cero parpadeos) y conserva el tema.
- **SC-006**: Por transición a BLOCKED, FAILED o WAITING_APPROVAL llega exactamente un aviso.
- **SC-007**: El transcript de cualquier agente lanzado por umbra no contiene instrucciones de
  plugins globales del usuario.
- **SC-008**: Todas las pruebas existentes pasan sin cambios en sus aserciones.

## Assumptions

- La hora local es la de la máquina donde corre `watch`; no se configura por proyecto.
- «umbra-claro» existe para terminales con fondo claro; el gusto final de los colores se ajusta
  con capturas en la revisión de la entrega.
- Los temas integrados de Textual se mantienen tal cual los entrega la librería.
- Detectar «hay un `watch` abierto» se hace con un bloqueo renovado por `watch` en la base; si
  `watch` muere sin liberarlo, caduca solo.
- La conversación de spec conserva su lógica actual (fases, permisos, costo); solo cambia dónde
  se muestra.
