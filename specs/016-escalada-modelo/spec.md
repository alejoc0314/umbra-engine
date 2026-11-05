# Feature Specification: Escalada automática de modelo

**Feature Branch**: `016-escalada-modelo`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Escalada automática de modelo: cuando Construir agota sus ciclos,
umbra reintenta sola con un modelo más fuerte; cuando constructor y revisor se enredan, un
tercer agente arbitra. Menos `retry` a mano, más «a la primera»."

## Contexto

Hoy, cuando los tests siguen fallando tras tres intentos o el revisor insiste tres rondas, la
tarea se detiene y la persona tiene que decidir y reintentar a mano. Casi siempre lo que hace es
volver a lanzar: la escalada automatiza exactamente eso, con un perfil más capaz y, en los
desacuerdos, con un tercer criterio.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Si el constructor no puede, lo intenta uno más fuerte (Priority: P1)

Construir agota sus ciclos con los tests fallando. En vez de detenerse, umbra sigue con el
siguiente perfil de la escalada (por defecto `builder-strong`: Fable 5.1 con esfuerzo alto),
que recibe el último error y otra ronda completa de intentos. Solo si también falla, la tarea
se detiene.

**Acceptance Scenarios**:

1. **Given** una rutina con `escalation: [builder-strong]`, **When** el constructor agota sus
   ciclos, **Then** se registra el paso al perfil fuerte y este intenta de nuevo con el error.
2. **Given** que el perfil fuerte acierta, **When** pasan los tests, **Then** la tarea sigue a
   Revisar sin ninguna intervención.
3. **Given** que el fuerte también agota sus ciclos, **Then** la tarea se detiene con el motivo
   de siempre y el registro muestra ambos tramos.

---

### User Story 2 - Un árbitro cuando constructor y revisor no se ponen de acuerdo (Priority: P2)

Tras los ciclos de revisión, un agente de solo lectura (`arbiter`, Opus 5.5) recibe el cambio y
los hallazgos y decide cuáles son reales. Si descarta todos, la tarea sigue; si mantiene alguno,
vuelve a Construir con esos (y, si la escalada queda disponible, con el perfil fuerte).

**Acceptance Scenarios**:

1. **Given** tres rondas de revisión con el mismo hallazgo, **When** el árbitro no lo sostiene,
   **Then** la tarea sigue a Verificar y el registro lo cuenta.
2. **Given** que el árbitro mantiene hallazgos, **Then** vuelven a Construir como retrabajo.
3. **Given** una rutina sin árbitro pero con escalada, **When** se agotan las revisiones,
   **Then** Construir sube de perfil y se revisa otra vez.

### Edge Cases

- Sin `escalation` ni `arbiter` en la rutina, todo se comporta como hoy.
- El árbitro solo actúa una vez por ejecución (hasta el siguiente reintento humano).
- `umbra retry` reinicia los tramos: vuelve a empezar con el perfil base.

## Requirements *(mandatory)*

- **FR-001**: La etapa Construir MUST aceptar `escalation` (lista de perfiles) y pasar al
  siguiente al agotar `max_fix_cycles`, registrando el evento y entregando el último error.
- **FR-002**: Las etapas de revisión MUST aceptar `arbiter`; al agotar ciclos, el árbitro
  (solo lectura) decide los hallazgos vigentes una vez por ejecución.
- **FR-003**: Sin árbitro, al agotar las revisiones Construir MUST escalar si puede.
- **FR-004**: Los perfiles MUST aceptar `effort` (Claude Code `--effort`).
- **FR-005**: Las rutinas por defecto `feature` y `quick` MUST traer la escalada y, `feature`,
  el árbitro.
- **FR-006**: El registro MUST narrar escaladas y arbitrajes en lenguaje llano.
- **FR-007**: El CHANGELOG MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Con el constructor falso fallando tres veces y el fuerte acertando, la tarea llega
  a «Espera tu aprobación» sin `retry`.
- **SC-002**: Con el revisor falso insistiendo tres rondas y el árbitro descartando, la tarea
  sigue.
- **SC-003**: Todas las pruebas anteriores pasan (ajustadas al nuevo número de intentos).
