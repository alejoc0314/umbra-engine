# Feature Specification: Onboarding de proyectos ya iniciados

**Feature Branch**: `029-onboarding`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Necesito que umbra se pueda usar con proyectos ya iniciados y de
forma muy funcional. Un proceso de onboarding para que umbra se ponga en contexto en profundidad
sobre el proyecto en el que comenzará a trabajar; que construya una constitution. Dentro del
onboarding, el sistema de diseño y el inventario de vistas para poder referenciar «en la vista X
haz este cambio»."

## Contexto

Al adoptar una carpeta, umbra deja su configuración y un mapa corto (`CONTEXT.md`). Eso orienta,
pero no basta para trabajar bien en un proyecto con historia: faltan las reglas del negocio, el
porqué de la arquitectura, lo que no se toca, lo que ya estaba roto y lo que espera el equipo. En
un proyecto sin SDD, umbra debe ganarse ese contexto antes de la primera tarea, con la persona
validando lo que entendió.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - umbra estudia el proyecto (Priority: P1)

`umbra onboard` (o `/onboarding` en Telegram) recorre el proyecto sin cambiarlo:

1. **Reconocimiento** sin modelo: stack, comandos que declara (scripts, Makefile, artisan), CI,
   documentación e instrucciones para IA que ya existan, variables de entorno de ejemplo,
   migraciones, tamaño por lenguaje e historia de git (antigüedad, autores, archivos que más
   cambian).
2. **Línea base**: corre los comandos de tests y lint registrados y anota qué pasa y qué ya
   fallaba antes de que umbra tocara nada.
3. **Exploración**: cinco exploradores de solo lectura, en paralelo, cada uno con un foco:
   arquitectura, dominio, convenciones, interfaz (inventario de vistas con su ruta y su archivo,
   y el sistema visual que usan) y riesgos.

**Acceptance Scenarios**:

1. **Given** un repo con `package.json`, tests y docs, **When** corre el onboarding, **Then**
   `.umbra/artifacts/onboarding/` tiene el reconocimiento, la línea base y una nota por explorador, y el
   repo no cambió.
2. **Given** tests que ya fallan, **Then** la línea base lo dice antes de cualquier tarea.

---

### User Story 2 - umbra pregunta lo que el código no dice (Priority: P1)

Tras explorar, umbra hace unas pocas preguntas (máximo 8) con opciones y una recomendada: para
qué es el producto, qué no se toca, qué deuda se conoce, ambientes, usuario de prueba… La
persona responde con botones o con texto, en la terminal o en Telegram.

**Acceptance Scenarios**:

1. **Given** el onboarding explorado, **Then** llegan las preguntas una a una con sus opciones.
2. **Given** respuestas a todas, **Then** umbra redacta los artefactos.

---

### User Story 3 - Lo aprendido queda en el repo y lo aprueba la persona (Priority: P1)

umbra redacta y la persona revisa antes de que nada quede confirmado:

- `CONTEXT.md` ampliado: qué es, arquitectura, dominio y glosario, convenciones, cómo se corre,
  dónde mirar.
- `.specify/memory/constitution.md` del proyecto: de 8 a 15 principios MUST/SHOULD, cada uno con
  su evidencia (archivo de ejemplo) y marcado como «así se hace hoy» o «así queremos que se
  haga», más lo que dijo la persona.
- `specs/000-linea-base/`: el inventario de capacidades (qué hace el sistema y dónde vive), el
  inventario de vistas (ruta, archivo, propósito) y la línea base de tests.

Aprobar confirma esos archivos en la rama actual (sin push).
Pedir cambios vuelve a redactar con el comentario.

**Acceptance Scenarios**:

1. **Given** los artefactos redactados, **When** la persona aprueba, **Then** quedan en un
   commit «umbra: onboarding» y el onboarding queda hecho.
2. **Given** «la regla 3 no aplica», **Then** umbra vuelve a redactar con ese comentario.
3. **Given** que el redactor toca otro archivo, **Then** se restaura y el onboarding se detiene.

### Edge Cases

- Sin comandos de tests registrados: la línea base lo dice y el reconocimiento propone los que
  detectó.
- Onboarding a medias: `umbra onboard` y `/onboarding` retoman donde quedó (`--de-cero` empieza
  otra vez).
- Un explorador falla: el onboarding sigue con los demás y lo anota.
- Telegram: `/adoptar` ofrece el onboarding al terminar.

## Requirements *(mandatory)*

- **FR-001**: `umbra onboard` MUST recorrer reconocimiento, línea base, exploración, preguntas,
  redacción y revisión, guardando su estado para retomarlo.
- **FR-002**: El reconocimiento y la línea base MUST hacerse sin modelo.
- **FR-003**: Los exploradores MUST ser de solo lectura y correr en paralelo con límites de
  tiempo y costo.
- **FR-004**: Las preguntas MUST llegar con opciones (una recomendada) y admitir texto libre.
- **FR-005**: El redactor MUST poder escribir solo `CONTEXT.md`,
  `.specify/memory/constitution.md` y `specs/000-linea-base/`; lo demás se restaura.
- **FR-006**: Nada MUST confirmarse sin la aprobación explícita de la persona.
- **FR-007**: `/onboarding` en Telegram MUST hacer lo mismo, con botones.
- **FR-008**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Con agentes falsos, `umbra onboard` en un repo de prueba deja reconocimiento,
  línea base y cinco notas, hace las preguntas, redacta los tres artefactos y, al aprobar, los
  confirma en un commit sin tocar nada más.
- **SC-002**: El mismo recorrido funciona por Telegram con botones.
- **SC-003**: Todas las pruebas anteriores pasan.
