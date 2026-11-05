# Contract: texto de costo

Entrada: `cost` (dólares, decimal o vacío) y `tokens` (tokens de Codex, entero ≥ 0).

| cost | tokens | Texto |
|---|---|---|
| 0 / vacío | 0 | `$0.00` |
| 0.42 | 0 | `$0.42` |
| 0 / vacío | 60 | `60 tokens` |
| 0.42 | 60 | `$0.42 + 60 tokens` |
| 0.42 | 60 000 | `$0.42 + 60k tokens` |
| 1.5 | 1 200 000 | `$1.50 + 1.2M tokens` |

Reglas:

- El texto MUST NOT contener «sin precio».
- Con tokens > 0, el texto MUST NOT ser `$0.00`.
- Los tokens se abrevian igual que hoy: `< 1000` tal cual, `k` sin decimales y `M` con un decimal.
- `--json` no cambia: `cost` / `spend.total` y `unpriced_tokens` como hasta ahora.
