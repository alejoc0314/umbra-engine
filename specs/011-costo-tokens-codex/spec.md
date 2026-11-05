# Feature Specification: Costo de una tarea sin «tokens sin precio»

**Feature Branch**: `011-costo-tokens-codex`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Quiero que cuando aparezca el costo de una tarea, aparezca el costo de
claude mas la cantidad de tokens gastada por codex pero quitandole el \"tokens sin precio\""

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver el costo de una tarea en forma corta (Priority: P1)

Quien usa umbra mira el costo de una tarea (en `status`, `evidence`, `watch`, el avance de una spec,
las rutinas o las métricas) y ve los dólares que gastó Claude más los tokens que gastó Codex, sin la
etiqueta «sin precio». Hoy ve `$0.42 + 60k tokens sin precio`; pasará a ver `$0.42 + 60k tokens`.

**Why this priority**: Es todo lo que pide la funcionalidad: un costo más corto y fácil de leer.

**Independent Test**: Ejecutar una tarea en la que trabajen Claude y Codex y mirar su costo en
cualquiera de las pantallas: aparece `$X.XX + N tokens` y no aparece «sin precio».

**Acceptance Scenarios**:

1. **Given** una tarea en la que Claude gastó $0.42 y Codex 60 000 tokens, **When** se muestra su
   costo, **Then** se lee `$0.42 + 60k tokens`.
2. **Given** una tarea en la que solo trabajó Codex (60 tokens), **When** se muestra su costo,
   **Then** se lee `60 tokens` y nunca `$0.00`.
3. **Given** una tarea en la que solo trabajó Claude ($0.42), **When** se muestra su costo,
   **Then** se lee `$0.42`, igual que hoy.
4. **Given** cualquier pantalla o salida de texto de umbra que muestre un costo, **When** se
   revisa, **Then** el texto «sin precio» no aparece en ninguna.

---

### Edge Cases

- Ni Claude ni Codex gastaron nada: se muestra `$0.00`, igual que hoy.
- Cantidades grandes de tokens siguen abreviándose como hoy (`1.2M tokens`, `60k tokens`).
- Totales que suman varias tareas (gasto acumulado, métricas, avance de una spec) usan el mismo
  formato corto.
- La salida `--json` no cambia: sigue dando los dólares y los tokens de Codex en campos separados,
  para no romper scripts que ya la leen.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Todo costo mostrado como texto MUST tener la forma `$X.XX + N tokens` cuando hay
  dólares de Claude y tokens de Codex.
- **FR-002**: Si solo hay tokens de Codex, el costo MUST mostrarse como `N tokens`, nunca como `$0.00`.
- **FR-003**: Si solo hay dólares, el costo MUST mostrarse como `$X.XX`, sin cambios.
- **FR-004**: El texto «sin precio» MUST NOT aparecer en ninguna salida de texto de costo
  (`status`, `evidence`, `evidence --raw`, `watch`, avance de specs, rutinas, gasto acumulado).
- **FR-005**: La salida `--json` MUST conservar sus campos y valores actuales.
- **FR-006**: El CHANGELOG MUST registrar el cambio en «Sin publicar».

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 apariciones de «sin precio» en las salidas de texto de umbra que muestran costo.
- **SC-002**: En el 100 % de las tareas con trabajo de Codex, su costo muestra la cantidad de tokens
  de Codex; en ninguna se lee `$0.00` cuando Codex gastó tokens.
- **SC-003**: Los scripts que leen el costo desde `--json` siguen funcionando sin cambios.

## Assumptions

- Los tokens «sin precio» de hoy son los de Codex (Codex informa tokens pero no dólares), así que
  mostrar esos tokens es mostrar «los tokens gastados por Codex».
- Se conserva la palabra «tokens» tras la cantidad: sin ella, `$0.42 + 60k` no se entendería.
- No se agrega el nombre de cada agente («Claude», «Codex») al texto: el núcleo no nombra agentes
  concretos (principio IV) y el formato `$… + … tokens` ya los distingue.
- Los dólares se siguen mostrando con dos decimales y los tokens con la misma abreviatura de hoy.
