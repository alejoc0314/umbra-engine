# Research: `umbra chat` programático

Comprobado contra `claude --help` del Claude Code instalado (2026-10-30).

## R1. Cómo invocar a Claude sin sesión interactiva

- **Decision**: `claude -p --output-format json` con el mensaje por stdin, ejecutado con
  `run_bounded` (ya mata el árbol al agotar el tiempo). La salida se lee con
  `adapters.claude_code.parse_stream`, que ya extrae `result`, `session_id`, costo en `Decimal`
  y `is_error` de la línea `{"type": "result", ...}`.
- **Rationale**: un único objeto de resultado basta; no hace falta mostrar la respuesta mientras
  se escribe. Mensaje por stdin = sin problemas de comillas ni de longitud en Windows.
- **Alternatives considered**: `stream.Stream` (stream-json, el de `spec new`): más piezas
  (hilo de lectura, cierre) para algo que no es una conversación larga. Agent SDK: dependencia
  nueva, prohibido por X.

## R2. Permisos sin nadie que confirme

- **Decision**: `--permission-mode dontAsk` y `build_settings(..., headless=True,
  allow_changes=...)`: lo que hoy va a `ask` (STATEFUL y `exec` no `safe`) pasa a `deny` sin
  `--allow-changes` y a `allow` con él. QUERY y `exec` `safe` siguen en `allow`;
  FORBIDDEN_UMBRA, FORBIDDEN_SHELL y POLICY_FILES siguen en `deny`. Se añade `allow` explícito
  para `Read`, `Glob` y `Grep`.
- **Rationale**: `dontAsk` niega todo lo que no esté preaprobado, así que cualquier otro shell o
  edición queda negado sin listarlo. Convertir `ask` en `deny`, sin depender solo del modo,
  deja la frontera escrita en código (III). `deny` gana sobre `allow`, así que
  `--allow-changes` no puede destapar lo prohibido.
- **Alternatives considered**: `--permission-prompts none` (mismo efecto, flag más reciente; se
  puede añadir si `dontAsk` cambia). `--allowedTools`: duplicaría las reglas que ya genera
  `build_settings`.

## R3. Settings y prompt por invocación

- **Decision**: el modo programático escribe settings y prompt en un
  `tempfile.TemporaryDirectory` propio de cada llamada; el interactivo sigue usando
  `.umbra/artifacts/chat/`.
- **Rationale**: dos mensajes a la vez con distinto `--allow-changes` no deben poder leer los
  settings del otro (uno sin permiso acabaría con los permisos del otro).
- **Alternatives considered**: `--settings '<json>'` en línea: frágil si `claude` resuelve a un
  `.cmd` en Windows.

## R4. Identificar la conversación y continuarla

- **Decision**: conversación nueva → umbra genera un UUID y pasa `--session-id`; `--session <id>`
  → `--resume <id>`; `--continue` → `--resume` con el id guardado en
  `.umbra/artifacts/chat/last-session` (se reescribe al terminar con éxito).
- **Rationale**: saber el id antes de lanzar permite filtrar los comandos de esta llamada y
  devolverlo aunque `claude` falle. `claude --continue` no sirve: retomaría la última sesión del
  directorio, que puede ser la de `spec new` o la interactiva.
- **Alternatives considered**: tabla `conversation`: su `CHECK` de fases es de `spec new`; una
  migración para guardar un solo id no se justifica.

## R5. Qué comandos se ejecutaron

- **Decision**: el hook `PostToolUse` existente añade `session_id` (viene en la entrada del
  hook) al evento `chat.command`. Al terminar, `ask()` lee los eventos `chat.command` con ese
  `session_id` creados desde que empezó la llamada.
- **Rationale**: `PostToolUse` solo se dispara si la herramienta llegó a ejecutarse: los negados
  no aparecen, que es lo que «ejecutados» significa. Reutiliza el registro que ya pide FR-010.
- **Alternatives considered**: leer `tool_use` del stream: incluye los intentos negados y obliga
  a stream-json.

## R6. Límites

- **Decision**: `[chat] max_minutes` (2 por defecto) → `run_bounded(timeout_s=...)`;
  `[chat] max_cost_usd` (0,50 por defecto) → `--max-budget-usd`. La validación reutiliza
  `elicit.max_cost_usd` parametrizada por sección y valor por defecto.
- **Rationale**: los mismos mecanismos que usan los agentes de tareas. `--max-budget-usd` corta
  dentro del turno en curso (SC-004).
- **Alternatives considered**: límite de costo acumulado por conversación: el pedido es por
  mensaje; se añade si una conversación larga se vuelve un problema real.

## R7. Costo

- **Decision**: cada llamada inserta una fila en `usage` (`agent='claude'`, sin `attempt_id` ni
  `conversation_id`, `invocation_id` nuevo) con el `total_cost_usd` del resultado.
- **Rationale**: en `-p` cada proceso informa su propio costo, no el acumulado de la sesión, así
  que no hace falta el `cost_seen` de `spec new`. Entra en el costo total de `umbra status`.

## R8. Ctrl+C

- **Decision**: `run_bounded` captura `KeyboardInterrupt`, mata el árbol y vuelve a lanzar la
  excepción.
- **Rationale**: `background_kwargs()` pone al hijo en su propio grupo, así que Ctrl+C no le
  llega; sin esto `claude` seguiría corriendo (y gastando). Arreglarlo en `run_bounded` cubre a
  todos sus llamadores.

## R9. Sin sesión iniciada en `claude`

- **Decision**: no se detecta aparte. Si `claude` devuelve `is_error`, su texto se muestra tal
  cual; si no devuelve resultado, el mensaje dice que se compruebe que `claude` funciona y tiene
  sesión iniciada.
- **Rationale**: umbra no gestiona login (IX); el texto de `claude` ya dice qué hacer.
