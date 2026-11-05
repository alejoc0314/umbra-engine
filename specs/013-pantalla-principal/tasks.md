---

description: "Tareas de la pantalla principal de umbra watch"
---

# Tasks: La pantalla principal de `umbra watch`

**Input**: [spec.md](spec.md), [plan.md](plan.md)

> Se construye en sesión (lo visual se juzga con ojos). Cada fase deja `uv run pytest -q` y
> `uv run ruff check .` en verde.

- [ ] T001 `blocks/process.run_bounded`: volcar la salida al archivo mientras corre (hilo lector
  del pipe + stdin en hilo); mismo resultado final. Prueba con un proceso lento.
- [ ] T002 `cli/agent_story.py`: de líneas stream-json (Claude) / JSON Lines (Codex) a frases.
- [ ] T003 `cli/watch_data.py`: cabecera (worker, cola, gasto, atención), orden por atención,
  progreso por etapas y tiempo por fila, `extra` bajo demanda (evidencia + salida de pruebas,
  cambios por archivo + parche), seguimiento incremental del registro del agente.
- [ ] T004 `cli/watch.py` + `watch.tcss`: cabecera, lista nueva, TabbedContent con seis pestañas
  y teclas, evidencia en color, cambios con `Syntax`, agente, apilado en terminal estrecha; `e`
  y `A` sobre la pestaña.
- [ ] T005 Pruebas: orden y selección por atención, cabecera, pestañas, evidencia/cambios,
  agente en vivo, breakpoint; instantáneas regeneradas.
- [ ] T006 `docs/usage.md`, `CHANGELOG.md`.
