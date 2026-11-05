# Research: Costo de una tarea sin «tokens sin precio»

No quedaron NEEDS CLARIFICATION en el contexto técnico. Decisiones:

## 1. Dónde cambiar el texto

- **Decision**: Solo en `spend_text` (`src/umbra/unified/explain.py:344`).
- **Rationale**: Es la única fuente del texto «tokens sin precio» (verificado con grep en todo el
  repo). `status`, `evidence`, `watch`, las rutinas, el avance de specs y el gasto acumulado la
  llaman. Si se cambia ahí, cambian todas las pantallas.
- **Alternatives considered**: Formatear en cada pantalla. Se descartó porque son 9 llamadas que
  podrían quedar desalineadas entre sí.

## 2. Formato

- **Decision**: `$X.XX + N tokens`; `N tokens` si no hay dólares; `$X.XX` si no hay tokens.
- **Rationale**: Es lo que pidió el usuario, y conserva la palabra «tokens» para que la cantidad se
  entienda.
- **Alternatives considered**: `$0.42 + 60k` (no se entiende qué es 60k) y `$0.42 (Claude) + 60k
  tokens (Codex)` (nombra agentes en el núcleo, contra el principio IV).

## 3. Salida `--json`

- **Decision**: Sin cambios; el campo se sigue llamando `unpriced_tokens`.
- **Rationale**: Es una interfaz estable que leen scripts y el chat (FR-005, SC-003).
- **Alternatives considered**: Renombrar el campo a `codex_tokens`. Se descartó porque rompe a
  quien ya lo lee y porque nombra a un agente.

## 4. Nombres internos

- **Decision**: Se mantienen `_unpriced` y `unpriced_tokens` en el código; si acaso, solo se
  actualizan los docstrings.
- **Rationale**: Quien usa umbra no los ve, y renombrarlos agranda el diff sin darle nada a nadie.
