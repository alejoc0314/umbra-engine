# Feature Specification: Acciones desde `umbra watch`

**Feature Branch**: `feat/watch-actions`
**Created**: 2026-10-29
**Status**: Implemented
**Input**: "Desde la pantalla del watch quiero poder ejecutar el accept, seguir con los procesos,
etc." Decisiones del usuario: aprobar desde `watch` sí, con ventana de evidencia y
confirmación; atajos de una letra y además la paleta de comandos.

## Requisitos

- **FR-001**: `watch` MUST ofrecer, sobre la tarea seleccionada, solo las acciones que aplican a
  su situación: aceptar, descartar, ejecutar/reintentar (eligiendo etapa), empezar de cero,
  pausar/retomar, cancelar, ver evidencia, aprobar y rechazar.
- **FR-002**: Cada acción MUST ejecutar el mismo código que su comando (`umbra.service`) y
  mostrar el comando equivalente al terminar.
- **FR-003**: Aprobar MUST mostrar la evidencia y pedir confirmación; rechazar, cancelar,
  descartar y empezar de cero MUST pedir confirmación. La opción por defecto es «No».
- **FR-004**: Aprobar y rechazar MUST exigir una terminal interactiva, igual que en la CLI.
- **FR-005**: Las operaciones MUST ejecutarse en segundo plano sin congelar la pantalla; los
  errores se muestran como aviso sin cerrar `watch`.
- **FR-006**: Las acciones MUST estar también en la paleta de comandos.
- **FR-007**: Los eventos generados desde `watch` MUST registrar origen `watch`.
- **FR-008**: El chat MUST NOT poder lanzar `umbra watch` (es interactivo: colgaría la sesión).

## Fuera de alcance (siguiente vuelta)

Crear y editar tareas con formularios; `umbra plan` desde `watch`.

## Verificación

Pruebas que manejan `watch` por teclado (Textual pilot): aceptar → ejecutar → aprobar con
confirmación; cancelar la aprobación con `n`; reintentar eligiendo etapa; empezar de cero;
rechazar con motivo; pausar, retomar, ver evidencia y cancelar; error mostrado sin romper la
pantalla; teclas que no aplican no hacen nada.
