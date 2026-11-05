# Feature Specification: Crítica, direcciones y gusto

**Feature Branch**: `027-critica-y-gusto`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Que el agente diseñe mejor: cosas más bonitas y pulidas, de más
vanguardia y profesionales. Ciclo de crítica, revisiones automáticas, direcciones de la pantalla
clave (que lleguen a Telegram) y que el diseñador aprenda cómo me gustan los proyectos."

## Contexto

Con la spec 026 el diseñador diseña y la persona aprueba, pero la calidad depende de un solo
intento: los errores visibles (texto cortado, contraste pobre, inconsistencias) llegan hasta la
persona, y cada proyecto empieza sin saber qué le gusta. Los modelos diseñan mejor cuando
alguien critica su trabajo con criterio, cuando hay referencias y cuando conocen el gusto de
quien decide.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - El diseño llega ya criticado (Priority: P1)

Tras cada intento del diseñador, sus propias revisiones automáticas y un crítico con rúbrica
miran las pantallas. Lo importante vuelve al diseñador hasta `max_fix_cycles`; lo que quede
pendiente llega a la persona junto con la pregunta.

**Acceptance Scenarios**:

1. **Given** un crítico que encuentra «el texto del botón se corta», **Then** el diseñador
   recibe esa corrección y vuelve a exportar antes de preguntar a la persona.
2. **Given** que el problema persiste tras los ciclos, **Then** la persona decide y ve «El
   crítico todavía ve…».
3. Las observaciones del diseño no se mezclan con los hallazgos del código.

---

### User Story 2 - Elegir la dirección visual (Priority: P1)

Si el proyecto aún no tiene una dirección aprobada, el diseñador propone 2 o 3 direcciones. La
persona las ve como fotos (una por dirección) y elige con un botón, con `watch` o con
`umbra design elegir N i`. El diseñador continúa en esa línea.

**Acceptance Scenarios**:

1. **Given** el primer diseño del repo, **Then** el sobre pide direcciones y la tarea se
   detiene con «elige una dirección de diseño», con un botón por dirección en Telegram.
2. **Given** que la persona elige la 2, **Then** el diseñador recibe esa dirección y no vuelve
   a proponer direcciones.

---

### User Story 3 - umbra aprende el gusto de la persona (Priority: P2)

Cada elección (frente a las descartadas), cada cambio pedido y cada aprobación se anotan en
`~/.umbra/gusto.md`, que vale para todos los proyectos. El diseñador y el crítico lo reciben
siempre; la persona puede leerlo (`umbra design gusto`, `/gusto`) y editarlo.

**Acceptance Scenarios**:

1. **Given** una dirección elegida, cambios pedidos y un diseño aprobado, **Then** `gusto.md`
   los registra con fecha y proyecto, y el siguiente diseñador los recibe.

### Edge Cases

- El crítico falla por algo técnico: el diseño sigue sin su crítica (queda en el registro).
- El crítico intenta escribir: la tarea se detiene (solo lectura).
- Elegir una dirección fuera de rango: error claro.
- `gusto.md` muy largo: el sobre lleva lo más reciente.

## Requirements *(mandatory)*

- **FR-001**: La etapa `design` MUST admitir `critic`; los hallazgos del crítico y los del
  propio diseñador ≥ `block_on` MUST devolver el diseño a corregir hasta `max_fix_cycles`.
- **FR-002**: umbra MUST incluir un perfil `design-critic` genérico con rúbrica, y `feature`
  MUST usarlo.
- **FR-003**: Con 2 o más `options`, la tarea MUST detenerse con `design_choice`; elegir MUST
  reanudar el diseño con la dirección elegida.
- **FR-004**: Elegir, pedir cambios y aprobar MUST anotarse en `~/.umbra/gusto.md`, y el
  diseñador y el crítico MUST recibirlo.
- **FR-005**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Con agentes falsos, un crítico con un hallazgo `high` provoca otro intento del
  diseñador con ese texto; tras dos ciclos, la persona decide con lo pendiente.
- **SC-002**: Direcciones → tres fotos y tres botones → elegir → el diseñador sigue esa línea →
  el gusto registra la elección, los cambios y la aprobación.
- **SC-003**: Todas las pruebas anteriores pasan.
