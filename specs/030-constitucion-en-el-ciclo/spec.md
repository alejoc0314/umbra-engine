# Feature Specification: La constitución en el ciclo y specs retroactivas

**Feature Branch**: `030-constitucion-en-el-ciclo`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Que la constitución que construye el onboarding se use de verdad
al trabajar, y que el proyecto entre a SDD por las zonas donde se trabaja."

## Contexto

El onboarding (spec 029) deja una constitución del proyecto y una línea base de tests. Sin más,
serían documentos que nadie lee. Deben guiar a cada agente, ser la vara del revisor, poder
cambiar con la aprobación de la persona, y hacer que cada spec nueva en un proyecto heredado
parta de cómo funciona hoy lo que toca.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Todos los agentes trabajan con la constitución (Priority: P1)

Planificador, diseñador, constructor, revisor, verificador y árbitro reciben la constitución
del proyecto y la línea base de tests. El revisor marca como importante (`high`) incumplir un
MUST en lo que el cambio añade; el constructor y el planificador se detienen y preguntan si una
tarea obliga a romper un principio.

**Acceptance Scenarios**:

1. **Given** un proyecto con constitución y línea base, **When** corre una tarea, **Then** el
   sobre del agente trae ambos.

---

### User Story 2 - Specs retroactivas justo a tiempo (Priority: P1)

En un proyecto que pasó por el onboarding, la conversación de spec documenta primero, en
«## Cómo funciona hoy», el comportamiento, las reglas y los tests del área que toca la idea, y
especifica el cambio sobre esa base.

**Acceptance Scenarios**:

1. **Given** `specs/000-linea-base/`, **Then** el mensaje de la fase de especificar lo pide; sin
   onboarding, el mensaje es el de siempre.

---

### User Story 3 - Enmendar la constitución (Priority: P2)

`umbra constitucion enmendar "…"` (o `/enmendar …`) pide a un agente que redacte la enmienda y
suba la versión; la persona ve el diff y la aprueba (commit) o la descarta (se restaura).
`umbra constitucion ver` y `/constitucion` la muestran.

**Acceptance Scenarios**:

1. **Given** una enmienda aprobada, **Then** queda en un commit «umbra: enmienda de la
   constitución»; descartada, la constitución no cambia.
2. **Given** que el redactor toca otro archivo, **Then** se restaura y la enmienda falla.

### Edge Cases

- Sin constitución: `ver` y `enmendar` dicen que `umbra onboard` la redacta.
- Lo marcado «así queremos que se haga» se exige al código nuevo, no obliga a rehacer lo viejo.

## Requirements *(mandatory)*

- **FR-001**: `project_notes` MUST incluir la constitución y la línea base si existen.
- **FR-002**: Las instrucciones del revisor, árbitro, planificador y constructores MUST usarla.
- **FR-003**: La fase de especificar MUST pedir «Cómo funciona hoy» en proyectos con onboarding.
- **FR-004**: Las enmiendas MUST requerir la aprobación explícita de la persona.
- **FR-005**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Con agentes falsos, el sobre de una tarea trae la constitución y la línea base.
- **SC-002**: Enmendar por la terminal y por Telegram aprueba o descarta como se pide.
- **SC-003**: Todas las pruebas anteriores pasan.
