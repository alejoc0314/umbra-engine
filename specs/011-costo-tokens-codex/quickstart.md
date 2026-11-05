# Quickstart: validar el costo sin «tokens sin precio»

## Automático

```bash
uv run pytest tests/acceptance/test_autopilot_findings_cost.py -k unpriced
uv run pytest && uv run ruff check .
```

Resultado esperado: el test de costo encuentra `60 tokens` en `status`, `evidence` y
`evidence --raw`. En ninguna de esas salidas aparece «sin precio», `--raw` no contiene `$0.00` y
`metrics --json` sigue dando `unpriced_tokens == 60`.

## Manual (sandbox con agentes reales)

1. En `sandbox/`, ejecuta una tarea con la rutina `feature` (Claude implementa y Codex revisa).
2. `umbra status`: el costo se lee `$X.XX + N tokens`.
3. `umbra evidence <n>` y `umbra watch`: mismo formato, sin «sin precio».
4. `umbra status --json`: los campos `spend` y `unpriced_tokens` siguen como antes.

Formatos esperados por caso: [contracts/cost-text.md](contracts/cost-text.md).
