---

description: "Tareas del costo sin «tokens sin precio»"
---

# Tasks: Costo de una tarea sin «tokens sin precio»

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/cost-text.md](contracts/cost-text.md),
[quickstart.md](quickstart.md)

> **Para `umbra plan`**: es **una sola tarea de umbra** (T001–T005). Deja `uv run pytest -q` y
> `uv run ruff check .` en verde. T006 lo hace el responsable a mano.

Reglas: las pruebas no usan red ni modelos (constitution). `--json` no cambia, y los nombres
internos `_unpriced` y `unpriced_tokens` tampoco (research §3–4). Sin dependencias nuevas.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (otro archivo, sin depender de tareas pendientes)
- **[Story]**: US1 = ver el costo en forma corta ([spec.md](spec.md))

Sin fases de Setup ni Fundamentos: el proyecto ya existe y no hay nada que bloquee la historia.

---

## Fase 1: User Story 1 — Ver el costo de una tarea en forma corta (P1) 🎯 MVP

**Objetivo**: todo costo se lee `$X.XX + N tokens`, `N tokens` o `$X.XX`, y nunca contiene
«sin precio».

**Prueba independiente**: `uv run pytest tests/acceptance/test_autopilot_findings_cost.py
tests/unit/test_spend_text.py` en verde.

- [ ] T001 [US1] En `spend_text` de `src/umbra/unified/explain.py` (línea ~349), cambiar
  `f"{tokens_text(tokens)} tokens sin precio"` por `f"{tokens_text(tokens)} tokens"` y renombrar
  la variable local `unpriced` a `codex`. Actualizar el docstring a «Dólares conocidos y, aparte,
  los tokens que el agente informa sin precio (Codex).» No tocar las ramas `if not tokens` (sigue
  `$X.XX`) ni `cost == 0` (sigue solo `N tokens`, nunca `$0.00`).
- [ ] T002 [P] [US1] Crear `tests/unit/test_spend_text.py` con un test parametrizado sobre
  `umbra.unified.explain.spend_text` que cubra la tabla de
  [contracts/cost-text.md](contracts/cost-text.md): `(0, 0) → "$0.00"`, `(None, 0) → "$0.00"`,
  `("0.42", 0) → "$0.42"`, `(0, 60) → "60 tokens"`, `("0.42", 60) → "$0.42 + 60 tokens"`,
  `("0.42", 60_000) → "$0.42 + 60k tokens"`, `("1.5", 1_200_000) → "$1.50 + 1.2M tokens"`. Añadir
  en cada caso `assert "sin precio" not in text`.
- [ ] T003 [P] [US1] En `tests/acceptance/test_autopilot_findings_cost.py`,
  `test_codex_shows_unpriced_tokens_instead_of_zero_dollars` (líneas 28–31): cambiar cada
  `"60 tokens sin precio" in …` por `"60 tokens" in … and "sin precio" not in …` para `status`,
  `evidence 1 --raw` (conservar `"$0.00" not in raw`) y `evidence 1`. Actualizar el comentario de
  la línea 28 a `# $… + 60 tokens`. No quitar ninguna aserción existente: la de
  `metrics --json` (`unpriced_tokens == 60`) se queda igual.

**Checkpoint**: la historia está completa y verificable por sí sola.

---

## Fase 2: Pulido

- [ ] T004 [P] En `CHANGELOG.md`, añadir al final de `## Sin publicar` (hoy está vacía, justo antes
  de `## v0.9.1`) la línea: `- El costo de una tarea se lee más corto: «$0.42 + 60k tokens» (los
  tokens son los de Codex), sin la etiqueta «sin precio».` No tocar `__version__` ni crear
  secciones de versión.
- [ ] T005 Ejecutar `uv run pytest -q` y `uv run ruff check .`; ambos en verde. Comprobar con grep
  que «sin precio» ya solo aparece en `CHANGELOG.md` (entrada histórica de v0.8.0), en los
  docstrings de `src/umbra/unified/store.py`, en las aserciones `not in` de los tests y en
  `specs/`.
- [ ] T006 (manual, responsable) Smoke test de [quickstart.md](quickstart.md) en `sandbox/` con
  agentes reales: `umbra status`, `umbra evidence <n>` y `umbra watch` muestran `$X.XX + N tokens`;
  `umbra status --json` no cambia.

---

## Dependencies & Execution Order

- T001 primero (el código que prueban T002 y T003).
- T002, T003 y T004 en paralelo tras T001 (archivos distintos).
- T005 después de T001–T004. T006 después de mezclar.

### Parallel Example: User Story 1

```text
Tras T001:
  T002 tests/unit/test_spend_text.py
  T003 tests/acceptance/test_autopilot_findings_cost.py
  T004 CHANGELOG.md
```

## Implementation Strategy

MVP = la Fase 1 completa (es toda la funcionalidad). Se entrega en un solo PR con T001–T005; T006
valida con agentes reales después de mezclar.
