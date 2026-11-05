# Implementation Plan: La pantalla principal de `umbra watch`

**Branch**: `013-pantalla-principal` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

Sobre los cimientos de la 012: la instantánea (`watch_data.Snapshot`) crece con la cabecera del
proyecto (worker, cola, gasto, atención), el orden por atención y el progreso por etapas de cada
fila; el detalle pasa a un `TabbedContent` con seis pestañas (Situación, Qué ha pasado,
Intentos, Evidencia, Cambios, Agente). Evidencia y Cambios se calculan bajo demanda en el hilo
lector (`Loader.extra(...)`) y se pintan con color (informe vía `Text.from_ansi`, parche vía
`rich.syntax.Syntax("diff")`). El registro de cada agente se escribe en disco mientras corre
(`run_bounded` lo vuelca línea a línea) y la pestaña Agente lo sigue por tamaño de archivo,
convertido a frases (`agent_story.py`). Con menos de 100 columnas la lista y el detalle se apilan.

## Technical Context

**Dependencies**: textual 8 (TabbedContent, Syntax de rich 15), sin dependencias nuevas.
**Storage**: sin migraciones; los registros de agente ya tienen ruta (`attempt.log_path`
derivable: `.umbra/artifacts/<attempt>-<stage>.jsonl`). **Performance**: tick sin cambios < 5 ms;
con Agente activa y un intento en curso < 20 ms (lectura incremental del archivo por offset).
**Testing**: Pilot + instantáneas; `run_bounded` con un proceso falso que escribe despacio.

## Constitution Check

| Principio | Cumple | Cómo |
|---|---|---|
| I/II | Sí | Sin acciones nuevas; `e` sigue existiendo (abre la pestaña). `umbra evidence` intacto. |
| III | Sí | Solo presentación. |
| V–IX | Sí | `run_bounded` conserva timeout, kill del árbol y el archivo final idéntico. |
| X | Sí | Sin dependencias; una pestaña = un widget ya existente. |

## Decisiones

- **Orden por atención** en `Loader._tasks`: grupo 0 = BLOCKED/FAILED/WAITING_APPROVAL; 1 =
  RUNNING/QUEUED/PAUSED; 2 = accepted/draft sin ejecución; 3 = done/dropped/SUCCEEDED/CANCELLED.
  La selección por defecto es la primera fila del grupo 0 si existe.
- **Progreso por etapas**: `explain._progress` ya da (etapa, marca); se pinta como `●` hecho,
  `▶` en curso, `■` detenida, `✗` fallo, `○` pendiente, con color `$stage-*` y `$state-*`.
- **Cabecera**: widget `Static#status` bajo el Header: `worker ● vivo · cola 1 · gasto $10.53 +
  925k tok · ⚠ 1 te necesita`; datos en `Snapshot.header` (lease `worker`, conteos, spend).
- **Pestañas**: `TabbedContent#detail` con TabPane ids `situation`, `timeline`, `attempts`,
  `evidence`, `changes`, `agent`; teclas `1`–`6`, `e` → evidence. Los ids `#attempts`, `#log`,
  `#specs` se conservan.
- **Bajo demanda**: `WatchApp` pasa `wants` (pestaña activa) al loader; `Loader.load` devuelve
  `evidence`/`changes` solo si se piden y cambió (run_id, head_sha). Cache por (run_id, head).
- **Agente en vivo**: `run_bounded(..., log_path)` abre el archivo al arrancar y escribe cada
  línea al llegar (hilo lector del pipe; stdin se escribe desde otro hilo para no bloquear);
  `Loader` guarda offset por archivo y devuelve solo líneas nuevas convertidas por
  `agent_story.lines(raw_lines, agent)`. El tick comprueba el tamaño del archivo aunque
  `data_version` no cambie.
- **Responsive**: `HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (100, "-wide")]` y CSS que apila
  `#main` en `-narrow`.
