# Implementation Plan: Decidir desde `umbra watch`

**Branch**: `014-decidir-desde-watch` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

Motor: `task.allowed_paths` (migración V5) que `policy.check_diff` respeta y el motor comunica al
agente (`Engine.person_feedback`), evento `policy.allowed`; respuestas como evento
`task.answered` que el motor añade al sobre en el siguiente intento; `service.allow_paths`,
`service.answer`, `service.approve_all`/`waiting_tasks`, `service.open_findings`,
`git.fast_forward` tras aprobar. CLI sombra: `umbra task allow`, `umbra task answer`,
`umbra approve --all`, `umbra finding list` con hallazgos abiertos. `watch`: `Snapshot.decision`
(código, rutas frenadas, preguntas, cuántas esperan, hallazgos abiertos) alimenta el panel
«Decisión» (teclas destacadas encima de la explicación, borde ámbar) y `check_action`.

## Constitution Check

| Principio | Cumple | Cómo |
|---|---|---|
| II | Sí | Cada tecla tiene su comando y muestra el equivalente. |
| III | Sí | Autorizar y responder son decisiones de la persona registradas como eventos; el motor sigue decidiendo transiciones. |
| VII | Sí | Integrar en bloque pasa por `service.approve` una a una (tty interactiva, head_sha). |
| IX | Sí | La autorización es por tarea y por ruta; la política sigue para el resto. |

## Decisiones

- `a` reutiliza el binding de aceptar: en borrador acepta; detenida con rutas frenadas, autoriza.
- `r` en una tarea detenida por preguntas responde (y reanuda); en otros bloqueos, reintenta.
- `T` solo aparece con dos o más tareas en espera.
- `h` aparece en cualquier tarea con hallazgos abiertos.
