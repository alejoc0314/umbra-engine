# Feature Specification: `umbra chat` programático

**Feature Branch**: `010-chat-programatico`

**Created**: 2026-10-30

**Status**: Draft

**Input**: User description: "Necesito que ahora umbra chat funcione de manera programática con
claude code, de forma más sencilla."

## User Scenarios & Testing *(mandatory)*

Hoy `umbra chat` solo abre una sesión interactiva de Claude Code: hay que estar delante, escribir
y leer en esa pantalla. No sirve para preguntar algo desde un script, desde otra sesión de Claude
Code o desde un atajo, ni para obtener una respuesta que otro programa pueda leer.

El modo programático es para quien llama `umbra chat "pregunta"` desde la terminal, un script u
otro agente y recibe la respuesta. Que la sesión normal de `claude` conozca umbra sin pasar por
`umbra chat` queda fuera de esta feature.

### User Story 1 - Preguntar en una línea y recibir la respuesta (Priority: P1)

El usuario escribe `umbra chat "¿por qué se detuvo la tarea 3?"`. umbra le hace la pregunta a
Claude con el mismo contexto y las mismas reglas que el chat interactivo, Claude consulta lo que
necesite (`status`, `explain`, `log`…) y la respuesta sale en la terminal. El comando termina solo,
sin abrir ninguna pantalla.

**Why this priority**: es el corazón del pedido: usar el chat sin sentarse en una sesión. Por sí
solo ya entrega valor: preguntas rápidas desde la terminal o un atajo.

**Independent Test**: en un proyecto con tareas, ejecutar `umbra chat "¿qué tareas están
detenidas?"` y comprobar que imprime una respuesta en lenguaje llano y termina con código 0.

**Acceptance Scenarios**:

1. **Given** `claude` instalado y con sesión iniciada, **When** el usuario ejecuta
   `umbra chat "mensaje"`, **Then** se imprime la respuesta y el comando termina sin pedir nada
   más.
2. **Given** el mensaje llega por la entrada estándar (`echo "mensaje" | umbra chat -`), **Then**
   se trata igual que si se hubiera pasado como argumento.
3. **Given** `umbra chat` sin mensaje, **Then** se comporta como hoy: abre la sesión interactiva.
4. **Given** `claude` no está instalado, **Then** falla con el mismo mensaje claro de hoy y un
   código de salida distinto de 0.

---

### User Story 2 - Salida que otro programa puede leer (Priority: P2)

Un script, una automatización u otra sesión de Claude Code ejecuta
`umbra chat "mensaje" --json` y recibe un único objeto con la respuesta, el identificador de la
conversación, el costo, si hubo error y los comandos de umbra que se ejecutaron.

**Why this priority**: la constitution pide `--json` en todo comando que produce datos; sin esto
«programático» se queda en texto que hay que interpretar.

**Independent Test**: ejecutar con `--json`, validar que la salida es un único objeto JSON con
los campos acordados, y que un error (por ejemplo, sin `claude`) también sale como JSON.

**Acceptance Scenarios**:

1. **Given** `--json`, **When** termina la respuesta, **Then** la salida estándar contiene solo
   un objeto JSON con: respuesta, conversación, costo, comandos ejecutados y estado (ok / error).
2. **Given** un error (sin `claude`, límite agotado, `claude` falla), **Then** la salida sigue
   siendo un objeto JSON con estado de error y un mensaje, y el código de salida no es 0.

---

### User Story 3 - Seguir la misma conversación (Priority: P3)

Tras una primera pregunta, el usuario (o el script) continúa:
`umbra chat --continue "¿y qué opciones tengo?"`, o con el identificador de una conversación
concreta. Claude recuerda lo hablado.

**Why this priority**: útil pero no imprescindible; cada pregunta suelta ya tiene valor.

**Independent Test**: hacer una pregunta, luego otra con `--continue` que dependa de la primera
(«¿y la siguiente?») y comprobar que la respuesta usa el contexto anterior.

**Acceptance Scenarios**:

1. **Given** una conversación previa en este proyecto, **When** se usa `--continue`, **Then** el
   mensaje se añade a la última conversación de `umbra chat` de este proyecto.
2. **Given** el identificador de una conversación, **When** se pasa con `--session <id>`,
   **Then** se continúa esa conversación.
3. **Given** `--continue` sin conversación previa, **Then** empieza una nueva y lo dice.

---

### User Story 4 - Comandos que cambian estado sin nadie delante (Priority: P2)

En la sesión interactiva, lo que cambia estado (`run`, `task accept`, `retry`…) pide confirmación
a la persona. En el modo programático no hay nadie a quien preguntar. Por defecto Claude no los
ejecuta: responde con el comando exacto que haría falta. Si quien llama lo permite de forma
explícita (`--allow-changes`), Claude puede ejecutarlos. Lo prohibido (aprobar, rechazar, push,
merge, editar la política de `.umbra/`, abrir pantallas interactivas) sigue prohibido siempre.

**Why this priority**: es la frontera de seguridad del modo programático; sin ella, un mensaje
por stdin podría cambiar el estado del proyecto sin que nadie lo decida.

**Independent Test**: pedir «arranca la tarea 3» sin `--allow-changes` y comprobar que no se
ejecutó y que la respuesta incluye `umbra run 3`; repetir con `--allow-changes` y comprobar que
se ejecutó y quedó un evento con origen `chat`; pedir «aprueba la tarea 3» con `--allow-changes`
y comprobar que se bloquea.

**Acceptance Scenarios**:

1. **Given** sin `--allow-changes`, **When** el mensaje pide un cambio de estado, **Then** el
   comando no se ejecuta y la respuesta muestra el comando exacto para que lo ejecute el usuario.
2. **Given** `--allow-changes`, **When** el mensaje pide un cambio de estado permitido, **Then**
   se ejecuta y queda registrado como evento con origen `chat`.
3. **Given** cualquier combinación de opciones, **When** el mensaje pide algo prohibido,
   **Then** se bloquea igual que en la sesión interactiva.

---

### Edge Cases

- El mensaje está vacío o solo tiene espacios: error claro, sin llamar a Claude.
- `claude` no tiene sesión iniciada: se informa que hay que iniciarla en `claude` (umbra no
  gestiona el login) y termina con error.
- La respuesta tarda o el gasto crece: hay un límite de tiempo y de costo por mensaje; al
  agotarse se corta, se informa cuál se agotó y lo gastado queda registrado.
- Se interrumpe con Ctrl+C: el proceso de `claude` termina con él y no quedan procesos huérfanos.
- Fuera de un proyecto umbra: el mismo error que el resto de comandos.
- Dos mensajes programáticos a la vez en el mismo proyecto: cada uno es independiente; dos
  `--continue` simultáneos sobre la misma conversación no se garantizan (se documenta).
- Claude intenta ejecutar un comando que no es de umbra ni un comando `safe` registrado: en modo
  programático no se ejecuta (no hay a quién pedir confirmación).
- La salida se redirige a un archivo o tubería: sin colores ni animaciones, solo la respuesta.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `umbra chat` MUST aceptar un mensaje como argumento, o por la entrada estándar con
  `-`, y en ese caso responder sin abrir una sesión interactiva y terminar solo.
- **FR-002**: Sin mensaje, `umbra chat` MUST seguir abriendo la sesión interactiva actual sin
  cambios de comportamiento.
- **FR-003**: El modo programático MUST usar el mismo contexto del proyecto y las mismas reglas
  de permisos que la sesión interactiva; MUST NOT tener más permisos que ella ni que la CLI.
- **FR-004**: Sin `--allow-changes`, los comandos que cambian estado y cualquier otro comando de
  shell que en la sesión interactiva pediría confirmación MUST NOT ejecutarse; la respuesta MUST
  incluir el comando exacto sugerido.
- **FR-005**: Con `--allow-changes`, los comandos de umbra que cambian estado MUST poder
  ejecutarse; los prohibidos (`approve`, `reject`, `watch`, `finding waive/defer`, `spec new`,
  `spec resume`, push, merge, editar la política) MUST seguir bloqueados.
- **FR-006**: Con `--json`, la salida estándar MUST ser un único objeto JSON con respuesta,
  identificador de conversación, costo, comandos ejecutados y estado; los errores también.
- **FR-007**: El código de salida MUST ser 0 solo si hubo respuesta sin error; distinto de 0 en
  cualquier error (sin `claude`, sin sesión, límite agotado, fallo de `claude`).
- **FR-008**: Cada mensaje programático MUST tener límite de tiempo y de costo, configurables en
  el proyecto con valores por defecto; agotarlos MUST cortar la respuesta e informarlo.
- **FR-009**: `--continue` MUST retomar la última conversación de `umbra chat` del proyecto y
  `--session <id>` una concreta.
- **FR-010**: Cada comando que Claude ejecute MUST quedar registrado como evento con origen
  `chat`, igual que hoy; el costo de cada mensaje MUST registrarse en decimales.
- **FR-011**: umbra MUST NOT pedir ni guardar credenciales: usa el login existente de `claude`.
- **FR-012**: La documentación de uso y el CHANGELOG MUST explicar el modo programático con un
  ejemplo de terminal, uno con `--json` y uno desde otra sesión de Claude Code.

### Key Entities

- **Mensaje programático**: el texto que se envía, sus opciones (`--json`, `--allow-changes`,
  continuación) y sus límites.
- **Conversación de chat**: identificador que permite continuar; pertenece al proyecto.
- **Resultado**: respuesta, costo, comandos ejecutados, estado y mensaje de error si lo hubo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una pregunta de consulta se hace y se responde con un solo comando, sin abrir
  ninguna pantalla ni escribir nada más.
- **SC-002**: El 100 % de las ejecuciones con `--json` producen un objeto JSON válido en la
  salida estándar, también cuando hay error.
- **SC-003**: Sin `--allow-changes`, 0 comandos que cambian estado se ejecutan en las pruebas del
  modo programático; con él, 0 comandos prohibidos se ejecutan.
- **SC-004**: Ningún mensaje programático supera su límite de tiempo o de costo por más de un
  turno en curso.
- **SC-005**: Una persona nueva en umbra puede usar el modo programático desde un script
  siguiendo solo el ejemplo de la documentación, en menos de 5 minutos.

## Assumptions

- «Programático» significa usable sin estar delante de una sesión: desde la terminal en una
  línea, desde scripts y desde otras sesiones de Claude Code o agentes.
- «Más sencilla» significa: un solo comando, sin preparar archivos ni configuración, y con
  respuesta lista para leer o para procesar.
- El modo interactivo actual se mantiene igual; esta feature solo añade.
- Límites por defecto: 2 minutos y 0,50 USD por mensaje, configurables en `.umbra/project.toml`.
- Como en el resto de umbra, las pruebas automáticas usan un `claude` falso y no consumen modelos.
- Solo Claude Code: no se añade soporte para otros agentes en el chat.

## Clarifications

### Session 2026-10-30

- Q: ¿Quién usa el modo programático? → A: Quien llama `umbra chat "pregunta"` desde la
  terminal, un script u otro agente y recibe la respuesta (opción A). Preparar la sesión normal
  de `claude` para que conozca umbra queda fuera.
