# Implementation Plan: Memoria de decisiones y mapa del repositorio

**Branch**: `015-memoria-contexto` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

Un módulo nuevo `src/umbra/management/memory.py` destila los eventos ya existentes
(`finding.decided`, `task.answered`, `policy.allowed`) en `.umbra/aprendido.md` y lo regenera
tras cada decisión (`service.decide_findings`, `service.answer`, `service.allow_paths`). El sobre
(`contracts/envelope.py`) gana `project_notes` (aprendido + `CONTEXT.md`, acotados) que
`Engine.agent_attempt` rellena y `adapters/base.render_prompt` incluye. `Engine.judge` ignora
hallazgos cuyo texto normalizado ya fue decidido «no aplica» en el repo. Un perfil
`cartographer` (solo lectura + escribir `CONTEXT.md`) lo genera con `umbra context build` y
`Engine.approve` lo actualiza tras integrar (intento `context`, nunca bloquea; commit directo a
la rama base con `git`). `watch` muestra lo aprendido con `m` en el panel derecho.

## Technical Context

**Dependencies**: sin nuevas. **Storage**: sin migraciones (los eventos ya existen; `aprendido.md`
es un archivo). **Testing**: agentes falsos (`tests/fakes/claude.py` modos `ok`/`noop`,
`tests/fakes/codex.py` modos `high:<msg>`/`medium:<msg>`); el cartógrafo se prueba con el `claude`
falso en modo `context` (nuevo: escribe `CONTEXT.md`).

## Constitution Check

| Principio | Cumple | Cómo |
|---|---|---|
| II | Sí | `umbra memory show/rebuild`, `umbra context build`; `m` en watch llama a lo mismo. |
| III | Sí | Lo aprendido se deriva de decisiones humanas registradas; el motor decide qué hallazgo cuenta. |
| VI | Sí | Nada avanza por texto del agente; solo cambia qué hallazgos bloquean (decisión humana previa). |
| VII | Sí | La actualización de `CONTEXT.md` tras integrar es un commit del motor sobre un archivo que la persona ya aceptó que umbra mantenga (como el merge del PR aprobado); se registra como evento. |
| IX | Sí | Solo el cartógrafo puede escribir `CONTEXT.md` (allowed_paths del perfil); el resto sigue bloqueado si lo toca. |
| X | Sí | Un archivo Markdown y un módulo; sin dependencias. |

## Decisiones

- **Formato de `aprendido.md`**: secciones `## Revisión: no pedir`, `## Para después`,
  `## Respuestas dadas`, `## Rutas autorizadas`; cada línea `- <texto> (tarea N, fecha, motivo)`.
  Generado íntegramente por `memory.rebuild(conn, root)`; nunca editado a mano.
- **Normalización** (`memory.normalize(text)`): minúsculas, sin `(archivo:línea)`, espacios
  colapsados, sin puntuación final. Se usa para comparar hallazgos en `Engine.judge`.
- **Tope en el sobre**: `project_notes` = `CONTEXT.md` (hasta 6 000 caracteres) + aprendido
  (hasta 4 000, decisiones más recientes primero).
- **Cartógrafo**: perfil `cartographer.toml` (`claude-code`, modelo `claude-sonnet-5-5`,
  `actions = ["read", "search", "edit"]`, `allowed_paths = ["CONTEXT.md"]` como campo nuevo del
  perfil que el adaptador traduce a `--allowedTools "Edit(CONTEXT.md),Write(CONTEXT.md)"`),
  instrucciones `cartographer.md` (secciones fijas marcadas con `<!-- umbra:… -->` para no pisar
  lo escrito a mano). `service.context_build(ctx)` lo ejecuta sobre la raíz del repo (no en un
  worktree) y hace commit si cambió.
- **Tras integrar**: `service.approve` → `context_refresh(ctx)` en un hilo del worker (no
  bloquea la aprobación); evento `context.updated` o `context.failed`.
