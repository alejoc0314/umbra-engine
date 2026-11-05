# Feature Specification: Takeover — abrir en el editor y que umbra retome

**Feature Branch**: `017-takeover`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "En un bloqueo, abrir el worktree de la tarea en mi editor,
arreglar a mano, y que umbra retome desde Revisar con mi commit como un intento más."

## Contexto

Cuando una tarea se detiene (tests que no pasan, hallazgos que el agente no resuelve, un
conflicto), hoy la persona solo puede reintentar, responder o empezar de cero. Muchas veces lo
más rápido es arreglarlo a mano: dos líneas en el editor. Falta un camino para hacerlo sin salir
del flujo: abrir el espacio de trabajo de la tarea, corregir, y que umbra siga con revisión,
verificación y publicación como si el arreglo fuera un intento más, dejando evidencia.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Abrir la tarea en mi editor (Priority: P1)

Desde `watch` (tecla `o`) o con `umbra open <n>`, el espacio de trabajo de la tarea detenida (o
esperando aprobación) se abre en el editor de la persona (`[editor] command` del proyecto,
`$VISUAL`, `$EDITOR` o `code`). Queda registrado que la persona tomó el control.

**Acceptance Scenarios**:

1. **Given** una tarea detenida, **When** la persona pulsa `o`, **Then** su editor se abre sobre
   el worktree de la tarea y el registro cuenta «Lo abriste en tu editor».
2. **Given** una tarea sin ejecución o con el worktree ya retirado, **Then** umbra lo dice y no
   abre nada.

---

### User Story 2 - Umbra retoma con mi arreglo (Priority: P1)

Tras corregir a mano, `umbra done <n> -m "qué arreglé"` (o `o` de nuevo en `watch`) confirma los
cambios como un commit de la persona, corre los tests del proyecto como evidencia, los registra
como un intento «humano» y encola la ejecución desde la etapa siguiente a Construir (Revisar en
`feature`; Publicar en `quick`). Si los tests fallan, la tarea sigue detenida con la salida.

**Acceptance Scenarios**:

1. **Given** una tarea detenida por tests y un arreglo a mano en el worktree, **When** la
   persona ejecuta `umbra done 1 -m "arreglo"`, **Then** aparece un intento de la persona con los
   tests en verde y la tarea llega a «Espera tu aprobación» sin ningún agente constructor.
2. **Given** que el arreglo deja los tests en rojo, **Then** `umbra done` termina con error,
   muestra la salida y la tarea no se encola.
3. **Given** que no hay cambios en el worktree respecto a lo evaluado, **Then** `umbra done` lo
   dice y no hace nada.

### Edge Cases

- El cambio de la persona no pasa por la política de rutas protegidas (la persona es la
  autoridad), pero sí por el escaneo de secretos de la rutina, si la tiene.
- `umbra done` sobre una tarea que esperaba aprobación la vuelve a evaluar desde Revisar: la
  aprobación anterior deja de valer.
- Los intentos de la persona se muestran como «tú» en el registro, la evidencia y `watch`.

## Requirements *(mandatory)*

- **FR-001**: `umbra open <n>` MUST abrir el worktree de la última ejecución en el editor de la
  persona y registrar el evento; en `watch`, la tecla `o` hace lo mismo.
- **FR-002**: `umbra done <n> -m <mensaje>` MUST confirmar los cambios pendientes del worktree
  como commit de la persona, registrar un intento con agente `human`, ejecutar el comando `test`
  como evidencia y, si pasa, encolar la ejecución desde la etapa siguiente a Construir.
- **FR-003**: Si los tests fallan, `umbra done` MUST dejar la tarea como estaba e informar.
- **FR-004**: El registro MUST narrar la toma de control y el retome en lenguaje llano; los
  intentos humanos MUST mostrarse como «tú».
- **FR-005**: El editor MUST poder configurarse con `[editor] command` en `project.toml`.
- **FR-006**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Con el constructor falso rompiendo los tests y un arreglo a mano en el worktree,
  `umbra done 1 -m "..."` lleva la tarea a «Espera tu aprobación» con un intento `human` y un
  artefacto `command:test` en verde, sin llamadas nuevas al constructor.
- **SC-002**: `umbra open 1` lanza el editor configurado con la ruta del worktree.
- **SC-003**: Todas las pruebas anteriores pasan.
