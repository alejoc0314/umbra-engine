# Implementation Plan: Contexto justo por tarea y lecciones aprendidas

**Branch**: `035-contexto-y-lecciones` | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/035-contexto-y-lecciones/spec.md`

## Summary

Dos piezas para trabajar bien en proyectos que ya existen:

1. **Explorar**: una etapa determinista, sin modelo, al inicio de la tarea. Arma un paquete de
   contexto acotado con:
   - los archivos de la zona y su motivo;
   - los tests que los cubren;
   - la historia de git;
   - las tareas anteriores de umbra en esa zona;
   - las lecciones aprobadas.
   Se guarda como evidencia ligada al SHA, llega a los agentes en un campo nuevo del sobre y se
   ve en `umbra explain` y en `watch`.
2. **Lecciones**: tras rechazos de Revisar, ejecuciones detenidas y correcciones de la persona,
   umbra cosecha una propuesta. La redacta un perfil barato, con borrador determinista de
   respaldo. La persona aprueba, descarta o retira desde la CLI, `watch` o Telegram. Las
   lecciones viven en `~/.umbra/lessons.db`, por clave de proyecto (primer commit): fuera del
   repo y a salvo de volver a clonar.

Detalle de las decisiones en [research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.12

**Primary Dependencies**: typer, rich, pydantic v2, pyyaml y textual (las de siempre; ninguna
nueva)

**Storage**:

- `.umbra/umbra.db`: migración V9 con la tabla `run_file`;
- artefactos en `.umbra/artifacts/`;
- `~/.umbra/lessons.db`: global, SQLite en modo WAL.

**Testing**: pytest con agentes falsos, repos git temporales y `UMBRA_HOME` temporal

**Target Platform**: Windows y POSIX

**Project Type**: CLI y TUI (`umbra`)

**Performance Goals**:

- Explorar en ≤ 10 s en repos de hasta 10 000 archivos;
- coste de modelo de Explorar: 0;
- redactar una lección cuesta ≤ US$0,10.

**Constraints**:

- el paquete nunca supera `[context] max_chars` (12 000 por defecto);
- Explorar es de solo lectura;
- la cosecha nunca bloquea un comando interactivo.

**Scale/Scope**: cientos de lecciones por proyecto; decenas de proyectos por máquina

## Constitution Check

*Antes del diseño: pasa, con una excepción justificada. Después del diseño: igual.*

| Principio | Cumplimiento |
|-----------|--------------|
| I. Terminal primero | `umbra lesson …` con `--json`; `explain --json` gana la clave `context`. Sin servidor. |
| II. Comandos antes que conversación | Explorar no usa modelo. El redactor tiene borrador determinista de respaldo (con `writer = ""` umbra funciona entero sin modelo). El chat solo usa `list` y `show`. |
| III. El agente propone, el motor decide | El redactor solo propone. El motor valida `LessonDraft`, decide duplicados y conflictos con ids reales, y solo la persona cambia estados. |
| IV. Agentes intercambiables | `lesson-writer` es un perfil declarativo. El núcleo no nombra agentes. `Envelope.context` es un campo opcional y compatible. |
| V. Sesiones acotadas | Redactor: 3 min, US$0,10 y ninguna acción. Explorar: sin agente, con presupuesto de tiempo para sus procesos de git. |
| VI. Evidencia o no pasó | El paquete es un artefacto con checksum y la huella de los SHA. Las lecciones no son evidencia ni hacen avanzar etapas. |
| VII. Humano antes de integrar | Sin cambios. Una lección no altera aprobaciones, políticas ni límites. |
| VIII. Reanudable e idempotente | Paquete por huella. Cosecha con `operation_key` por ejecución y evento. `UNIQUE (project_key, run_id, event_id)`. |
| IX. Aislamiento | Explorar solo lee el worktree. Las lecciones nunca escriben en el repo ni en lo versionado de `.umbra/`. Sin credenciales. |
| X. Simple hasta que duela | Solo librería estándar y git. **Excepción**: un estado global en `~/.umbra/lessons.db` (ver Complexity Tracking). |

## Project Structure

### Documentation (this feature)

```text
specs/035-contexto-y-lecciones/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md       # umbra lesson, explain, watch, Telegram, configuración
│   └── agents.md    # Envelope.context, perfil lesson-writer, LessonDraft
└── tasks.md         # /speckit-tasks
```

### Source Code (repository root)

```text
src/umbra/
├── management/
│   ├── explore.py          # NUEVO: zona, tests, historia, tareas previas, lecciones; armado con tope
│   └── lessons.py          # NUEVO: lessons.db, clave de proyecto, estados, cosecha, export/import, secretos
├── contracts/
│   └── envelope.py         # + Envelope.context, + LessonDraft
├── adapters/base.py        # presenta `context`
├── routines/
│   ├── engine.py           # etapa `explore`; `context` en agent_attempt; run_file al terminar build;
│   │                       #   harvest al dejar RUNNING
│   └── bridge.py           # /lecciones, /leccion, aviso agrupado
├── unified/
│   ├── store.py            # migración V9 (run_file)
│   └── explain.py          # sección Contexto
├── service.py              # human.fixed en resume_human; operaciones de lecciones (para CLI, watch y bridge)
├── cli/
│   ├── lessons.py          # NUEVO: umbra lesson …
│   ├── explain.py          # imprime la sección Contexto
│   ├── watch.py, watch_data.py, modals.py   # panel Lecciones (tecla l), bloque Contexto en el detalle
│   └── main.py             # registra el grupo `lesson`
└── defaults/
    ├── routines/feature.yaml, quick.yaml    # + `explore` al inicio
    └── profiles/lesson-writer.toml, lesson-writer.md

tests/
├── unit/test_explore.py    # zona, tests por convención, tope y omisiones, repo vacío, espacio
├── unit/test_lessons.py    # clave de proyecto, estados, duplicados, conflictos, secretos, export/import
└── acceptance/test_context_lessons.py   # escenarios 1–17 de quickstart.md con agentes falsos
```

**Structure Decision**: se mantiene la estructura de un solo paquete `src/umbra`. La lógica nueva
va en dos módulos de `management/`, como `memory.py` y `constitution.py`. El motor solo los llama.

## Diseño por pieza

### Explorar (`management/explore.py`)

- `explore(conn, parts, task, config) -> Package`:
  - semillas, expansión y prioridad (research §2);
  - lecciones aplicables, que vienen de `lessons.applicable(key, zone_files)`;
  - armado con tope: se llena por bloques en orden de prioridad, se recorta por líneas completas
    y se cuenta lo omitido.
- En el motor, la etapa `explore` funciona así:
  - si ya existe el artefacto de la huella, lo reutiliza;
  - si no, lo arma, guarda el `.md` y el `.json`, inserta un `artifact` con `kind = 'context'` y
    emite `explore.ready`;
  - cualquier excepción emite `explore.failed` y devuelve `Outcome("next")`: nunca bloquea (FR-007).
- `agent_attempt` lee el último paquete de la ejecución y lo pone en `envelope.context` para las
  etapas de contracts/agents.md.
- Al terminar `build` (y en `resume_human`), se escribe `run_file` con los archivos del diff.

### Lecciones (`management/lessons.py`)

- `project_key(parts)`, con alias para migrar claves de ruta a primer commit.
- `open_db()` sobre `cfg.umbra_home() / "lessons.db"`, con `busy_timeout`.
- Transiciones `approve`, `discard`, `retire` y `resolve`, con `lesson_history` y validación de
  estado.
- `applicable(key, files)` y `stale(lesson, ls_files)`.
- `harvest(ctx_or_engine, run_ids=None)`:
  - busca las fuentes sin cosechar;
  - llama a `agent_attempt(..., stage="lesson", output_model=LessonDraft)`, o usa el borrador
    determinista;
  - valida y oculta secretos;
  - crea la propuesta o suma el origen;
  - emite `lessons.proposed` con el número de propuestas, que dispara el aviso de watch y
    Telegram.
- `export(key)` e `import_(key, data)`.

### Puntos de enganche

- `engine.run` llama a `lessons.harvest` cuando la ejecución deja `RUNNING`. Lo hace en
  `try/except`: un fallo se registra como evento y no cambia el estado de la ejecución.
- `service.resume_human` emite `human.fixed` con el mensaje y los archivos.
- `service.reject` ya registra el motivo; la cosecha lo recoge.

## Riesgos

- **Zona mal deducida** en tareas sin `scope` ni rutas: el paquete sale pobre, pero no hace daño,
  porque Construir sigue pudiendo explorar. Se mide en el piloto. Si hace falta, se añade un
  explorador barato opcional en la rutina (research §1).
- **Ruido de propuestas**: el redactor puede devolver `skip`. Los duplicados suman origen y lo
  descartado no vuelve. Si en el piloto hay más de 1 propuesta por cada 3 ejecuciones, se sube
  el umbral (solo rechazos `high` o más).
- **`lessons.db` bloqueada o corrupta**: se avisa y las tareas siguen sin lecciones. `export`
  sirve de copia de seguridad.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Estado global `~/.umbra/lessons.db` además de `.umbra/umbra.db` por proyecto | FR-017 (fuera del repo, privado) y FR-018 (sobrevive a mover o volver a clonar). | `.umbra/umbra.db` se pierde al volver a clonar; un archivo versionado en `.umbra/` viola FR-017; un JSON por proyecto necesita un lock propio entre procesos, y SQLite ya lo da con WAL. |
