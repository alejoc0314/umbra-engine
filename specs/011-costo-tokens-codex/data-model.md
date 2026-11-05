# Data Model: Costo de una tarea sin «tokens sin precio»

Sin entidades, campos ni migraciones nuevas. El costo sigue saliendo de la tabla `usage`:

- **Dólares conocidos**: suma de `usage.cost` de los intentos de la ejecución.
- **Tokens de Codex** (`unpriced_tokens`): `input_tokens + output_tokens` de las filas con
  `estimated = 1` y `cost = 0` (`store._unpriced`).

Lo único que cambia es cómo se escriben estos dos valores como texto; ver
[contracts/cost-text.md](contracts/cost-text.md).
