# Implementation Plan: Paralelismo, aprobación por spec y modo noche

**Branch**: `018-paralelo-spec` | **Spec**: [spec.md](spec.md)

## Summary

Migración V6: `run.base_branch`. `service.run` decide la base por tarea (`spec/<carpeta>` si
tiene `spec_dir`, creada en el remoto desde la base si falta). `Engine.base_branch(run)` se usa
en `sync_with_base` y `ship`; `ship` sobre una rama de spec integra el PR (`gh.merge_pr`),
marca `SUCCEEDED`/`done`, evento `run.integrated`, y si todas las tareas de la spec están
hechas abre el PR de la spec (`operation spec:<dir>:pr`, evento `spec.ready` sin run, aviso).
Worker: lease `worker` como despachador y un hilo por ejecución (conexión propia) hasta
`[blocks] parallel`; tras cada ejecución, `service.autopilot(dispatch=False)` arranca lo que
quepa. `service.approve_spec` (`umbra approve --spec`, tecla `I`), `service.night`
(`umbra night`, tecla `N`). `spec_progress` expone el PR de la spec; `spec_line` lo cuenta.

## Constitution Check

Enmienda 1.2.0: se retira «ejecución paralela de tareas en un mismo repositorio» de fuera de
alcance; VII admite que dentro de una rama de spec umbra integre tareas que pasaron tests,
revisión y política, con la aprobación humana sobre la spec completa (PR único a la base).
III, V, VI, VIII, IX, X sin cambios: cada ejecución mantiene su lease, su worktree y sus
`operation_key`.

## Pruebas

`tests/acceptance/test_parallel_spec.py`: solape de intentos con `parallel = 2` (modo `slow`
del `claude` falso); spec de dos historias → integradas en `spec/001-demo` → PR de spec →
`umbra approve --spec`; `umbra night`; tecla `I` en `watch`.
