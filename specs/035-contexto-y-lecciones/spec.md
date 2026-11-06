# Feature Specification: Contexto justo por tarea y lecciones aprendidas

**Feature Branch**: `035-contexto-y-lecciones`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "Contexto para trabajar en proyectos existentes, más allá del
onboarding: (1) etapa Explorar antes de Construir que reúne solo el contexto justo para cada
tarea (archivos relevantes, historia git de esa zona, tests que la cubren, tareas anteriores que
la tocaron, lecciones aprobadas que aplican) con un tope de tamaño para no inflar el gasto,
guardado como evidencia visible en Revisar y en umbra explain; (2) lecciones aprendidas de las
ejecuciones (rechazos de Revisar, ejecuciones detenidas, correcciones de la persona) que umbra
propone con origen y fecha, que solo se aplican tras aprobación de la persona, que se pueden
descartar o retirar, y que viven en local en la máquina de la persona, no versionadas en el repo;
solución genérica para cualquier proyecto"

## Contexto

El onboarding (029) le da a umbra un mapa general del proyecto y una constitución. Pero cada
tarea toca una zona concreta, y hoy el agente de Construir la descubre a ciegas: lee de más (y
gasta), o lee de menos y repite errores que ya se corrigieron en esa misma zona. Además, lo que
se aprende en una ejecución (un rechazo de Revisar, una ejecución detenida, una corrección de la
persona) se pierde al terminar: la siguiente tarea vuelve a tropezar con lo mismo.

Esta spec añade dos piezas que se alimentan entre sí:

- **Explorar**: antes de Construir, umbra reúne el contexto justo de la tarea, con un tope de
  tamaño, y lo deja como evidencia.
- **Lecciones**: umbra propone lo que aprendió de cada tropiezo; la persona decide cuáles valen.
  Las aprobadas entran en el contexto de las tareas siguientes que tocan esa zona.

Todo es genérico: funciona igual en cualquier lenguaje, framework o tamaño de repo, y en
espacios de trabajo con varios repos.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cada tarea arranca con el contexto justo (Priority: P1)

Al ejecutar una tarea, umbra pasa por la etapa **Explorar** antes de Construir. Explorar reúne,
solo para la zona que la tarea toca:

- los archivos relevantes (los que hay que cambiar y los que los usan o los definen);
- la historia de git de esa zona (cambios recientes, por qué se hicieron);
- los tests que cubren esa zona;
- las tareas anteriores de umbra que tocaron esos archivos y cómo terminaron;
- las lecciones aprobadas que aplican a esa zona o a todo el proyecto.

El resultado es un **paquete de contexto** con un tope de tamaño. Si lo encontrado no cabe,
umbra prioriza (primero lo que se cambia, luego sus tests, luego lecciones, luego historia y
tareas anteriores) y anota qué dejó fuera. Construir y las etapas siguientes reciben ese paquete
en lugar de descubrir la zona por su cuenta.

**Why this priority**: es la base: sin contexto por tarea, las lecciones no tienen dónde
aplicarse, y el gasto de Construir sigue creciendo con el tamaño del repo.

**Independent Test**: en un repo con historia, tests y tareas anteriores, ejecutar una tarea y
comprobar que el paquete de contexto existe, menciona los archivos, tests y tareas esperados,
respeta el tope y que Construir lo recibió.

**Acceptance Scenarios**:

1. **Given** una tarea sobre un módulo con tests y commits previos, **When** corre Explorar,
   **Then** el paquete lista los archivos del módulo, los tests que lo cubren y los commits
   recientes de esa zona, y Construir lo recibe.
2. **Given** una zona que una tarea anterior de umbra ya tocó, **When** corre Explorar, **Then**
   el paquete nombra esa tarea, su número y cómo terminó (integrada, rechazada, detenida).
3. **Given** un repo grande donde lo relevante excede el tope, **When** corre Explorar, **Then**
   el paquete no supera el tope y dice qué quedó fuera y por qué.
4. **Given** un proyecto sin historia de git ni tests, **When** corre Explorar, **Then** el
   paquete se arma con lo que haya, lo dice, y la tarea sigue sin bloquearse.

---

### User Story 2 - El contexto se ve como evidencia (Priority: P1)

El paquete de contexto queda guardado con la ejecución, ligado al SHA explorado. La persona lo ve
en Revisar (en `umbra watch` y en la revisión de la tarea) y en `umbra explain <n>`: qué se le
dio al agente, cuánto ocupó, qué quedó fuera y qué lecciones se aplicaron.

**Why this priority**: sin verlo, la persona no puede saber por qué el agente hizo lo que hizo
ni si le faltó algo; y la constitución exige evidencia de cada etapa.

**Independent Test**: tras una ejecución, `umbra explain <n>` (y `--json`) muestra el resumen del
paquete y su tamaño; la vista de Revisar permite abrirlo.

**Acceptance Scenarios**:

1. **Given** una tarea que pasó por Explorar, **When** la persona corre `umbra explain <n>`,
   **Then** ve el resumen del contexto (archivos, tests, tareas previas, lecciones aplicadas,
   tamaño frente al tope, lo omitido).
2. **Given** la misma tarea en Revisar, **When** la persona abre su detalle en `umbra watch`,
   **Then** puede ver el contexto que recibió el agente.
3. **Given** un reintento de la tarea sobre un SHA distinto, **Then** Explorar se rehace y cada
   paquete queda ligado a su SHA.

---

### User Story 3 - umbra propone lecciones de sus tropiezos (Priority: P1)

Cuando algo sale mal, umbra redacta una **lección propuesta**: una regla corta y accionable, con
su origen (qué tarea, qué etapa, qué pasó), la fecha y la zona a la que aplica (unos archivos o
carpetas, o todo el proyecto). Los orígenes son:

- un rechazo de Revisar (hallazgos que bloquearon);
- una ejecución detenida (por límite, por política, por fallo repetido);
- una corrección de la persona (cuando arregla a mano y le cuenta a umbra qué arregló, o cuando
  rechaza el resultado con un motivo).

Una lección propuesta **no se aplica** a ninguna tarea hasta que la persona la aprueba.

**Why this priority**: es la segunda mitad del pedido y lo que evita repetir errores; sin
aprobación humana sería ruido o, peor, reglas equivocadas aplicadas en silencio.

**Independent Test**: provocar un rechazo de Revisar en una tarea y comprobar que aparece una
lección propuesta con origen, fecha y zona, y que la siguiente tarea sobre esa zona no la recibe
mientras siga sin aprobar.

**Acceptance Scenarios**:

1. **Given** una tarea rechazada en Revisar por un hallazgo bloqueante, **When** termina la
   etapa, **Then** existe una lección propuesta que cita la tarea, la etapa, el hallazgo y la
   fecha.
2. **Given** una ejecución detenida, **When** la persona la corrige y cuenta qué arregló,
   **Then** umbra propone una lección a partir de esa corrección.
3. **Given** una lección propuesta sin aprobar, **When** otra tarea toca la misma zona, **Then**
   el paquete de contexto no la incluye.
4. **Given** un tropiezo que repite una lección ya propuesta o aprobada, **Then** umbra no crea
   un duplicado: suma el nuevo origen a la existente.

---

### User Story 4 - La persona decide sobre cada lección (Priority: P1)

La persona ve las lecciones (propuestas, aprobadas, descartadas, retiradas) y puede:

- **aprobar** una propuesta (tal cual o editando el texto o la zona);
- **descartar** una propuesta (no se vuelve a proponer igual);
- **retirar** una aprobada que ya no vale (deja de aplicarse, queda en el historial).

Puede hacerlo con comandos (`umbra lesson ...`, todos con `--json`), en `umbra watch` y en
Telegram. Ni el chat ni los agentes pueden aprobar lecciones.

**Why this priority**: es lo que convierte las propuestas en conocimiento útil y mantiene a la
persona al mando.

**Independent Test**: aprobar, descartar y retirar lecciones desde la CLI y comprobar que solo
las aprobadas y vigentes aparecen en el contexto de una tarea nueva sobre su zona.

**Acceptance Scenarios**:

1. **Given** una lección propuesta, **When** la persona la aprueba, **Then** la siguiente tarea
   que toca su zona la recibe en su paquete de contexto y `umbra explain` lo muestra.
2. **Given** una lección aprobada, **When** la persona la retira, **Then** deja de aplicarse en
   tareas nuevas, y las ejecuciones pasadas siguen mostrando que la usaron.
3. **Given** una lección descartada, **When** se repite el mismo tropiezo, **Then** umbra no la
   vuelve a proponer; solo suma el origen al historial de la descartada.
4. **Given** una lección propuesta, **When** la persona la aprueba con el texto editado,
   **Then** se aplica el texto editado y se conserva el original en su historial.

---

### User Story 5 - Las lecciones son de la persona, no del repo (Priority: P2)

Las lecciones viven en la máquina de la persona, fuera del repo: no se versionan, no aparecen en
diffs ni en PRs y no se comparten con nadie salvo que la persona las exporte. Están separadas por
proyecto (o espacio de trabajo), de modo que las de un proyecto no contaminan otro, y sobreviven
a borrar y volver a clonar el repo.

**Why this priority**: lo pidió la persona explícitamente; protege su criterio privado y evita
que el repo cambie por algo que no es código.

**Independent Test**: aprobar lecciones en un proyecto, comprobar que `git status` no cambia,
clonar el repo de nuevo en otra carpeta y ver que umbra reconoce las mismas lecciones; abrir otro
proyecto y ver que no aparecen.

**Acceptance Scenarios**:

1. **Given** lecciones aprobadas, **When** la persona corre `git status`, **Then** no hay
   cambios atribuibles a lecciones.
2. **Given** el mismo repo clonado en otra carpeta de la misma máquina, **Then** umbra muestra
   sus lecciones.
3. **Given** otro proyecto, **Then** sus lecciones no incluyen las del primero.
4. **Given** la persona quiere llevarlas a otra máquina, **When** exporta e importa, **Then**
   llegan con su estado, origen y fechas.

---

### Edge Cases

- Una tarea sin zona clara (p. ej. "actualiza dependencias"): Explorar arma un paquete general
  (archivos de configuración, CI, lecciones de todo el proyecto) y lo dice.
- La zona de una lección ya no existe (archivos borrados o movidos): la lección se sigue
  mostrando, marcada como posiblemente obsoleta, y umbra sugiere retirarla; no se aplica sola a
  otra zona.
- Dos lecciones aprobadas se contradicen: ambas se muestran a la persona como conflicto; mientras
  no se resuelva, ninguna de las dos entra en el contexto.
- Muchas lecciones para una zona: entran por orden de relevancia y más reciente aprobación, dentro
  del tope; las que no caben quedan listadas como omitidas.
- Explorar falla o se pasa de su límite: la tarea sigue a Construir sin paquete (como hoy), lo
  deja como evidencia y avisa; no bloquea la ejecución.
- Espacio de trabajo con varios repos: el paquete puede incluir archivos de los repos hermanos que
  la tarea toca; las lecciones son del espacio.
- La persona corrige y no cuenta qué arregló: umbra no inventa la lección; propone solo si tiene
  el motivo o el diff de la corrección.
- Una lección propuesta contiene datos sensibles copiados de la salida (tokens, contraseñas):
  umbra los oculta antes de guardarla.
- Proyecto adoptado antes de esta spec: Explorar y lecciones funcionan sin volver a hacer el
  onboarding.

## Requirements *(mandatory)*

### Functional Requirements

**Explorar**

- **FR-001**: Las rutinas por defecto MUST incluir una etapa Explorar que corre antes de
  Construir en cada tarea; una rutina MAY omitirla.
- **FR-002**: Explorar MUST ser de solo lectura: no cambia archivos del repo ni su estado de git.
- **FR-003**: Explorar MUST reunir, para la zona de la tarea: archivos relevantes, historia de
  git de esa zona, tests que la cubren, tareas anteriores de umbra que la tocaron (con su número
  y resultado) y lecciones aprobadas vigentes que aplican.
- **FR-004**: El paquete de contexto MUST respetar un tope de tamaño configurable por proyecto,
  con un valor por defecto prudente; cuando lo encontrado lo excede, MUST priorizar según un
  orden fijo y documentado y listar lo omitido.
- **FR-005**: Explorar MUST tener sus propios límites de tiempo y costo, que cuentan en el gasto
  de la tarea.
- **FR-006**: Construir y las etapas siguientes MUST recibir el paquete de contexto.
- **FR-007**: Si Explorar falla o agota su límite, la tarea MUST continuar sin paquete, dejando
  evidencia del fallo y un aviso.
- **FR-008**: El paquete MUST guardarse como evidencia de la ejecución, ligado al SHA explorado,
  con su tamaño, el tope, lo omitido y las lecciones aplicadas.
- **FR-009**: `umbra explain <n>` (y su `--json`) MUST mostrar el resumen del paquete; la vista
  de Revisar en `umbra watch` MUST permitir verlo.
- **FR-010**: Un reintento sobre otro SHA MUST rehacer Explorar; uno sobre el mismo SHA MAY
  reutilizar el paquete.

**Lecciones**

- **FR-011**: umbra MUST proponer una lección tras: un rechazo de Revisar con hallazgos
  bloqueantes, una ejecución detenida y una corrección de la persona que incluye su motivo.
- **FR-012**: Cada lección MUST registrar: texto, zona de aplicación (rutas o todo el proyecto),
  estado (propuesta, aprobada, descartada, retirada), origen(es) (tarea, etapa, motivo, fecha) y
  su historial de cambios de estado con fecha y quién lo hizo.
- **FR-013**: Solo las lecciones aprobadas y no retiradas MUST entrar en el contexto de una
  tarea; las propuestas, descartadas y retiradas MUST NOT entrar.
- **FR-014**: La persona MUST poder listar, ver, aprobar (con o sin edición), descartar y
  retirar lecciones desde la CLI (con `--json`), desde `umbra watch` y desde Telegram.
- **FR-015**: El chat y los agentes MUST NOT aprobar, editar ni retirar lecciones; solo pueden
  proponerlas a través de umbra.
- **FR-016**: umbra MUST evitar duplicados: un tropiezo equivalente a una lección existente suma
  su origen a esa lección en lugar de crear otra; una descartada no se vuelve a proponer.
- **FR-017**: Las lecciones MUST guardarse en la máquina de la persona, fuera del repo, separadas
  por proyecto o espacio, y MUST NOT aparecer en el repo, sus diffs ni sus PRs.
- **FR-018**: La identidad del proyecto para las lecciones MUST sobrevivir a mover o volver a
  clonar el repo en la misma máquina.
- **FR-019**: La persona MUST poder exportar e importar las lecciones de un proyecto, conservando
  estado, origen, fechas e historial.
- **FR-020**: Antes de guardar una lección, umbra MUST ocultar secretos evidentes (tokens,
  contraseñas, claves).
- **FR-021**: umbra MUST avisar a la persona (en `umbra watch` y, si está configurado, en
  Telegram) cuando haya lecciones nuevas por decidir, sin interrumpir las ejecuciones.
- **FR-022**: Las lecciones aprobadas cuyas rutas ya no existen MUST marcarse como posiblemente
  obsoletas; dos lecciones en conflicto MUST quedar fuera del contexto hasta que la persona lo
  resuelva.

### Key Entities

- **Paquete de contexto**: lo que Explorar reúne para una tarea en un SHA. Contiene archivos
  relevantes, historia de la zona, tests, tareas previas, lecciones aplicadas, tamaño, tope y lo
  omitido. Pertenece a una ejecución y es evidencia.
- **Lección**: regla corta aprendida de un tropiezo. Tiene texto, zona, estado, orígenes e
  historial. Pertenece a un proyecto o espacio y vive en la máquina de la persona.
- **Origen de lección**: el hecho que la motivó: tarea, etapa, tipo (rechazo de Revisar,
  ejecución detenida, corrección de la persona), motivo y fecha.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las tareas ejecutadas con la rutina por defecto tiene un paquete de
  contexto visible en `umbra explain`, o un aviso de por qué no.
- **SC-002**: Ningún paquete de contexto supera el tope configurado.
- **SC-003**: En un piloto sobre un proyecto existente, el gasto medio de Construir por tarea no
  sube respecto a antes de esta spec (Explorar incluido), y baja en repos medianos o grandes.
- **SC-004**: En el piloto, los rechazos de Revisar repetidos por la misma causa en la misma zona
  bajan al menos a la mitad tras aprobar la lección correspondiente.
- **SC-005**: El 100 % de las lecciones aplicadas a una tarea fueron aprobadas por la persona
  antes de esa tarea.
- **SC-006**: Aprobar, descartar o retirar una lección toma una sola acción desde la CLI,
  `umbra watch` o Telegram.
- **SC-007**: Aprobar lecciones no produce ningún cambio en `git status` del repo.

## Assumptions

- "Antes de Construir" se resuelve poniendo Explorar al inicio de la tarea, antes de Planificar,
  para que también el plan aproveche el contexto; si la tarea no pasa por Planificar, Explorar
  sigue yendo justo antes de Construir.
- La zona de la tarea se deduce de su descripción, del plan de la spec y del mapa del onboarding
  si existe; no se exige que la persona la indique.
- El tope por defecto es del orden de unas decenas de miles de caracteres (ajustable en la
  configuración del proyecto); el valor exacto se fija en el plan con una medición real.
- Las lecciones son por proyecto o espacio; compartir lecciones entre proyectos distintos, o con
  otras personas, queda fuera de esta spec (salvo exportar e importar a mano).
- La aprobación desde Telegram usa el mismo canal autenticado que ya usa umbra para aprobar
  (verificando el `chat_id`).
- Una lección no cambia permisos, políticas, comandos de test ni límites: solo es contexto para
  los agentes. Las reglas que deben cumplirse siempre siguen yendo en la constitución.
- La constitución del proyecto (029/030) sigue siendo el lugar de las reglas versionadas y
  compartidas por el equipo; las lecciones son el complemento privado y local de la persona.
