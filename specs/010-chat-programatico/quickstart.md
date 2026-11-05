# Quickstart: validar `umbra chat` programático

Contrato: [contracts/chat-cli.md](contracts/chat-cli.md). Datos: [data-model.md](data-model.md).

## Automático (sin modelos)

```bash
uv run pytest tests/unit/test_chat_oneshot.py tests/acceptance/test_e3.py
uv run ruff check .
```

Las pruebas usan `tests/fakes/claude.py` (modo `chat`) y deben cubrir:

1. `umbra chat "hola"` → imprime la respuesta del falso, código 0, se lanzó `claude -p` con el
   mensaje por stdin, `--permission-mode dontAsk` y `--max-budget-usd 0.5`.
2. `echo hola | umbra chat -` → igual que 1.
3. `--json` → stdout es un objeto válido con `status`, `answer`, `session_id`, `cost_usd`,
   `commands`; con el falso en modo error → `status: "error"` y código 1.
4. Settings generados sin `--allow-changes`: `Bash(umbra run *)` en `deny`; con él, en `allow`;
   `Bash(umbra approve *)` en `deny` en ambos.
5. `--continue` tras una llamada → se pasa `--resume <id de la anterior>`; sin anterior → aviso
   por stderr y `--session-id` nuevo.
6. `--json` sin mensaje, `--continue` con `--session`, mensaje vacío → código 2.
7. `[chat] max_cost_usd = 0` → código 2 con mensaje claro.
8. El hook guarda `session_id`; `commands` solo lista los eventos de esa sesión.
9. `umbra chat` sin mensaje sigue lanzando la sesión interactiva (pruebas de `test_e3.py`).
10. Se registra una fila en `usage` con el costo del resultado.

## Manual con `claude` real (sobre `sandbox/` o este repo)

```bash
umbra chat "¿qué tareas hay y en qué estado?"            # responde y termina
umbra chat "¿y cuál fue la última?" --continue            # recuerda la anterior
umbra chat "arranca la tarea 3"                           # NO la arranca; sugiere `umbra run 3`
umbra chat "arranca la tarea 3" --allow-changes --json    # la arranca; commands incluye `umbra run 3`
umbra chat "aprueba la tarea 3" --allow-changes           # bloqueado
umbra chat "edita README.md y añade una línea"            # no edita nada
```

Desde otra sesión de Claude Code: pedirle que ejecute
`umbra chat "¿qué está detenido?" --json` y que lea `answer`.

Ctrl+C durante una respuesta larga: no queda ningún proceso `claude` vivo.
