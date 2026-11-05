# Data Model: Levantamiento de requisitos

Migración V2 en `unified/store.py` (se añade a `MIGRATIONS`; V1 no se toca).

```sql
CREATE TABLE conversation (
    id TEXT PRIMARY KEY,
    idea TEXT NOT NULL,
    spec_dir TEXT,                       -- specs/NNN-*, se conoce tras la fase specify
    phase TEXT NOT NULL CHECK (phase IN ('specify', 'clarify', 'spec_review',
        'plan', 'plan_review', 'tasks', 'done', 'discarded')),
    session_id TEXT,                     -- de system/init; para --resume
    cost_seen TEXT NOT NULL DEFAULT '0', -- último total_cost_usd acumulado de la sesión
    origin TEXT NOT NULL,                -- cli | watch
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
ALTER TABLE spec ADD COLUMN dir TEXT;
ALTER TABLE task ADD COLUMN spec_dir TEXT;
ALTER TABLE task ADD COLUMN story TEXT;               -- 'US1', 'US2'…
ALTER TABLE task ADD COLUMN requirements TEXT NOT NULL DEFAULT '[]';  -- ["FR-001", …]
ALTER TABLE task ADD COLUMN story_hash TEXT;          -- sha256 del texto de la historia
ALTER TABLE usage ADD COLUMN conversation_id TEXT REFERENCES conversation(id);
CREATE UNIQUE INDEX task_story ON task(spec_dir, story) WHERE story IS NOT NULL;
```

## Entidades

**Conversation** — una conversación de requisitos.

```text
specify ──► clarify ──► spec_review ──aprobar──► plan ──► plan_review ──aprobar──► tasks ──► done
               ▲            │ pedir cambios                 │ pedir cambios
               └────────────┘                         plan ◄┘
cualquier fase ──descartar──► discarded
```

- Solo el usuario mueve `spec_review → plan` y `plan_review → tasks` (puntos de control).
- `clarify` se salta si la spec no tiene `[NEEDS CLARIFICATION]` ni el asistente pregunta.
- `tasks → done` cuando `spec_tasks()` crea las tareas.
- Cada transición es un evento `spec.<fase>` con `origin`.

**Story** (no es tabla; sale del parser `management/specfile.py`):

| Campo | Origen |
| --- | --- |
| `id` | `US<n>` del encabezado |
| `title`, `priority` | encabezado; prioridad P1–P3 (P4+ → 3) |
| `text` | sección completa de la historia; base de `story_hash` |
| `scenarios` | lista numerada de escenarios de aceptación → `task.acceptance` |
| `requirements` | línea `**Requisitos**:` o `FR-\d+` citados → `task.requirements` |
| `steps`, `paths` | fase `[USn]` de `tasks.md` y rutas citadas → descripción y `task.scope` |

**Task** (existente): una por historia; `UNIQUE(spec_dir, story)` hace `spec tasks` idempotente.
Desalineada = `story_hash` ≠ hash actual de la historia en `spec.md` (se calcula al mostrar, no
se guarda).

**Costo por spec** = `usage` con `conversation_id` de sus conversaciones + `usage` de los
intentos de sus tareas.
