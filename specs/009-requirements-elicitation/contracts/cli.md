# Contrato: comandos y protocolo de la conversación

## Comandos

| Comando | Qué hace | Notas |
| --- | --- | --- |
| `umbra spec new "idea"` | Abre la pantalla de conversación y empieza en `specify` | Exige terminal interactiva |
| `umbra spec resume [NNN\|ruta]` | Reabre la conversación en su fase; sin argumento, la última abierta | Falla si otra pantalla tiene el lease |
| `umbra spec tasks <ruta> [--yes] [--json]` | Crea/actualiza una tarea en borrador por historia | Determinista; sin `--yes` muestra el cambio y pide confirmación si hay tareas existentes |
| `umbra spec list [--json]` | Specs con fase, «n de m historias hechas», costo y desalineadas | — |

`umbra chat`: `spec tasks` → con confirmación; `spec list` → libre; `spec new`/`spec resume` →
prohibidos.

`watch`: `s` abre la conversación (pide la idea; si hay una abierta, ofrece retomarla).

## Mensajes que envía umbra al asistente

| Fase | Mensaje |
| --- | --- |
| specify | `/speckit-specify <idea>` |
| clarify | `/speckit-clarify` |
| plan | `/speckit-plan` |
| tasks | `/speckit-tasks` |
| cualquiera | respuesta del usuario o «Cambios pedidos: <comentario>» |

## Permisos por fase (`--settings`)

Comunes: `Read`, `Glob`, `Grep`, `Skill`, `Bash`/`PowerShell` sobre `.specify/scripts/**`,
`Write`/`Edit` de `.specify/feature.json`. Todo lo demás denegado (en `-p` no hay a quién
preguntar).

| Fase | Escritura permitida además |
| --- | --- |
| specify, clarify | `specs/*/spec.md`, `specs/*/checklists/**` |
| plan | `specs/*/plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/**` |
| tasks | `specs/*/tasks.md` |
| spec_review, plan_review | ninguna (solo se procesa el comentario en la fase anterior) |

## Bloque de pregunta

Último bloque de código del mensaje del asistente:

````text
```umbra-question
{"question": "¿…?", "options": ["A", "B", "C"], "recommended": 0}
```
````

- `options`: 2–5 textos; `recommended`: índice o `null`.
- umbra añade siempre «Otra respuesta…». La respuesta enviada es el texto de la opción.
- JSON inválido o fuera de contrato → se muestra como texto y el usuario responde libre.

## Eventos del stream que usa umbra

| Evento | Uso |
| --- | --- |
| `system`/`init` | `session_id`; comprobar que existen las skills `speckit-*` |
| `stream_event` (deltas de texto) | texto en vivo |
| `assistant` con `tool_use` | línea de actividad («leyendo src/…», «escribiendo spec.md») |
| `result` | fin de turno; `total_cost_usd` acumulado → costo del turno; `is_error` |
