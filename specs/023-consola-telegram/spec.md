# Feature Specification: Telegram como consola de umbra

**Feature Branch**: `023-consola-telegram`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Usar umbra desde el celular como si fuera el umbra de terminal:
cuando termine una tarea, fotos de lo que se realizó y la explicación conceptual de cómo se
hizo; crear proyectos, generar specs, construir planes: todo lo que puedo hacer desde `umbra
watch`."

## Contexto

Con el puente (019) y la conversación (022), el teléfono sirve para decidir y preguntar. Lo que
falta es que sea la consola completa: ver cada entrega con sus capturas y su explicación, y
hacer desde ahí todo lo que hace `umbra watch`, incluidas las conversaciones de spec, los
planes y los proyectos nuevos.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cada entrega llega con fotos y explicación (Priority: P1)

Cuando una tarea queda lista (espera tu aprobación, o se integró en la rama de su spec), al
teléfono llega el informe de aprobación (qué se hizo, contado por el agente de resumen; cómo se
comprobó: pruebas, criterios, revisión, seguridad; cambios, costo y PR) y, si la verificación
pasó por el navegador, las capturas como álbum de fotos.

**Acceptance Scenarios**:

1. **Given** una tarea verificada en el navegador, **When** queda lista, **Then** llegan el
   informe y la foto de cada criterio visto, y después los botones de decisión.
2. **Given** una tarea de spec que se integra sola, **Then** llega su informe (sin botones).

---

### User Story 2 - Todo lo de `watch` por comandos (Priority: P1)

Comandos con barra, con menú en el bot: `/tareas`, `/explicar N`, `/registro N`, `/evidencia
N`, `/cambios N`, `/agente N`, `/hallazgos N`, `/tarea título | criterio`, `/aceptar`,
`/ejecutar`, `/reintentar N [etapa]`, `/decero`, `/pausar`, `/retomar`, `/cancelar`,
`/descartar`, `/integrar`, `/rechazar N motivo`, `/noaplica`, `/despues`, `/noche`,
`/integrar_spec`. Cada uno ejecuta la misma operación que la tecla de `watch`, con origen
`telegram`.

---

### User Story 3 - Specs, planes y proyectos desde el teléfono (Priority: P1)

`/spec idea` abre la conversación de requisitos: las preguntas del asistente llegan con sus
opciones como botones (la recomendada primero y «Otra respuesta…»), los puntos de control con
Aprobar / Pedir cambios / Descartar, `/spec_ver` manda el archivo de la spec o el plan, y al
final quedan las tareas en borrador. `/spec_seguir` retoma una conversación; `/spec_salir` la
deja. `/plan ruta/spec.md` propone tareas desde una spec escrita. `/nuevo_proyecto nombre
stack [idea]` crea un repo con playbook junto al actual y pasa a ser el proyecto actual.

### Edge Cases

- Lo que tarda minutos (un turno de spec, planificar, crear un proyecto) corre aparte: el
  puente sigue atendiendo y avisa al terminar; mientras, un segundo pedido igual se rechaza.
- Un repo recién creado desde el teléfono entra solo al puente (configuración de Telegram en
  `~/.umbra/local.toml`, que vale para todos los repos).
- La entrega al teléfono nunca frena la tarea: si Telegram falla, queda en el registro.

## Requirements *(mandatory)*

- **FR-001**: Al quedar lista una tarea, umbra MUST enviar el informe y las capturas.
- **FR-002**: Cada acción de `watch` MUST tener su comando en Telegram, con origen `telegram`.
- **FR-003**: La conversación de spec MUST poder llevarse completa por mensajes y botones.
- **FR-004**: `/plan` y `/nuevo_proyecto` MUST existir y correr sin bloquear el puente.
- **FR-005**: `~/.umbra/local.toml` MUST aplicarse a todos los repos de la persona.
- **FR-006**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios.

## Success Criteria *(mandatory)*

- **SC-001**: Con los falsos, una tarea verificada en el navegador llega al Telegram falso con
  informe y foto; `/spec` recorre pregunta, revisión y tareas en borrador solo con botones.
- **SC-002**: Todas las pruebas anteriores pasan.
