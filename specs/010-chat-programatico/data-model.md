# Data Model: `umbra chat` programático

Sin tablas ni migraciones nuevas.

## Mensaje programático (en memoria)

| Campo | Origen | Regla |
|-------|--------|-------|
| `message` | argumento o stdin (`-`) | sin espacios alrededor; vacío → error de uso (código 2) |
| `as_json` | `--json` | — |
| `allow_changes` | `--allow-changes` | — |
| `resume` | `--session <id>` o `--continue` | no se pueden usar juntos; ninguna opción se acepta sin mensaje |
| `max_minutes` | `[chat] max_minutes` | número > 0; 2 por defecto |
| `max_cost_usd` | `[chat] max_cost_usd` | decimal > 0; 0,50 por defecto |

## Resultado (salida de `ask()` y de `--json`)

| Campo | Tipo | Nota |
|-------|------|------|
| `status` | `"ok"` \| `"error"` | |
| `answer` | texto \| null | respuesta de Claude |
| `session_id` | texto | conversación usada (nueva o retomada) |
| `cost_usd` | texto decimal | `"0"` si `claude` no llegó a responder |
| `commands` | lista de texto | comandos que llegaron a ejecutarse |
| `error` | texto \| null | presente si `status = "error"` |

## Registros existentes que se reutilizan

- **`usage`**: una fila por mensaje: `agent='claude'`, `cost`, `model`, tokens,
  `invocation_id` nuevo; `attempt_id` y `conversation_id` nulos.
- **`event`** `chat.command` (origen `chat`): el payload añade `session_id`. Lo escribe el hook,
  tanto en el modo interactivo como en el programático.
- **`.umbra/artifacts/chat/last-session`**: id de la última conversación programática que
  terminó bien en el proyecto. Lo usa `--continue`.
