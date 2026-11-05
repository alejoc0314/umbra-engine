# Quickstart: verificar el levantamiento de requisitos

## Automático (sin red ni modelos)

```powershell
uv run pytest -q
uv run ruff check .
```

Cubre: parser de historias, `spec tasks` (crear, repetir sin duplicar, desalineada, todo o
nada), settings por fase, bloque `umbra-question`, costo por diferencia, conversación completa
con un `claude` falso que reproduce un stream grabado, tecla `s` en `watch` y copia de la spec
al worktree de la primera tarea.

## Manual (smoke test real sobre `sandbox/`)

1. `umbra spec new "añadir potencia a la calculadora"`
   - En < 2 s se ve actividad; el asistente lee `sandbox/calc.py`.
   - Si pregunta, salen opciones con la recomendada primero.
   - Se detiene en «Aprobar spec / Pedir cambios / Descartar».
2. «Pedir cambios: añade un caso de exponente negativo» → vuelve al mismo punto de control con la
   spec ajustada.
3. Aprobar spec → plan → resumen y «Aprobar plan». Comprobar que durante la fase specify no
   apareció `plan.md`.
4. Aprobar plan → `tasks.md` → tareas en borrador: `umbra task list` muestra una por historia,
   con criterios y alcance.
5. Cerrar a mitad de otra conversación y `umbra spec resume` → misma fase e historial.
6. `umbra spec list` y `umbra status` → «0 de N», costo de la conversación.
7. `umbra task accept <primera>` y `umbra run` → el PR incluye `specs/NNN-*/`.
8. Editar una historia en `spec.md` → `umbra spec list` la marca desalineada;
   `umbra spec tasks <ruta>` muestra el cambio y pide confirmación.
9. `git status` en la carpeta de trabajo: nada cambió fuera de `specs/` y `.specify/feature.json`.
