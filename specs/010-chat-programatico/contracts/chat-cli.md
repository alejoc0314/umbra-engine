# Contrato: `umbra chat`

```text
umbra chat                                   # sesión interactiva (sin cambios)
umbra chat MENSAJE [--json] [--allow-changes] [--continue | --session ID]
umbra chat - [...]                           # MENSAJE desde la entrada estándar
```

## Comportamiento

- Sin MENSAJE: abre la sesión interactiva actual. Pasar `--json`, `--allow-changes`,
  `--continue` o `--session` sin MENSAJE es un error de uso.
- Con MENSAJE: una pregunta, una respuesta, fin. Nunca abre una pantalla ni pide confirmación.
- `--allow-changes`: permite los comandos de umbra que en la sesión interactiva piden
  confirmación (`plan`, `run`, `pause`, `resume`, `cancel`, `retry`, `task add|edit|accept|drop|deps`,
  `spec tasks`, `exec` de comandos no `safe`). Sin él, Claude no puede ejecutarlos y responde con
  el comando exacto.
- Siempre prohibidos: `approve`, `reject`, `watch`, `finding waive|defer`, `spec new|resume`,
  `git push`, `gh pr merge`, editar `.umbra/project.toml`, `.umbra/routines/**`,
  `.umbra/profiles/**` y `.github/workflows/**`. En modo programático tampoco se edita ningún
  archivo ni se ejecuta otro comando de shell.
- `--continue`: retoma la última conversación programática del proyecto; si no hay ninguna, avisa
  por stderr y empieza una nueva.
- `--session ID`: retoma esa conversación.

## Salida

Texto (por defecto): la respuesta en stdout; avisos y errores en stderr.

`--json`: stdout contiene solo un objeto:

```json
{
  "status": "ok",
  "answer": "La tarea 3 está detenida porque…",
  "session_id": "3f1c…",
  "cost_usd": "0.012345",
  "commands": ["umbra explain 3 --json"],
  "error": null
}
```

En error, `status` es `"error"` y `error` trae el mensaje; los demás campos llevan lo que se
sepa. Los errores anteriores al chat (fuera de un proyecto umbra) salen con el formato común de
umbra: `{"error": "…"}`. Regla para quien lo lee: código de salida distinto de 0 ⇔ hay `error`.

## Códigos de salida

| Código | Cuándo |
|--------|--------|
| 0 | respuesta sin error |
| 1 | `claude` falló, no tiene sesión iniciada, se agotó el tiempo o el costo |
| 2 | error de uso: mensaje vacío, opciones incompatibles, configuración `[chat]` inválida, `claude` no instalado |

## Configuración (`.umbra/project.toml`)

```toml
[chat]
max_minutes = 2       # por mensaje
max_cost_usd = 0.5    # por mensaje
```
