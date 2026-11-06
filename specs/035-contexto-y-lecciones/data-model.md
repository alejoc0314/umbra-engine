# Data Model: Contexto justo por tarea y lecciones aprendidas

## Por proyecto: `.umbra/umbra.db` (migración V9)

### `run_file`

Los archivos que cambió cada ejecución. Sirve para encontrar las tareas anteriores que tocaron
una zona.

| Campo  | Tipo | Notas                                              |
|--------|------|----------------------------------------------------|
| run_id | TEXT | FK `run(id)`                                       |
| repo   | TEXT | `""` en un repo; nombre de la carpeta en un espacio |
| path   | TEXT | relativo al repo, con `/`                          |

PK `(run_id, repo, path)`. Se llena al terminar `build` (reemplaza lo anterior de esa ejecución).
Las ejecuciones previas se rellenan una vez desde git, cuando se puede.

### Paquete de contexto (artefacto, sin tabla nueva)

- **Archivos**:
  - `.umbra/artifacts/<run_id>-context-<fp8>.md`: lo que reciben los agentes;
  - `.umbra/artifacts/<run_id>-context-<fp8>.json`: el resumen estructurado.
  `fp8` son los 8 primeros caracteres de la huella de los SHA base.
- **Fila en `artifact`**: `kind = 'context'`, `checksum` (sha256 del `.md`), `tested_sha` (la
  huella) y `command = 'explore'`.
- **Evento**: `explore.ready`, con el resumen; `explore.failed` lleva el motivo.

Resumen (`.json` y payload del evento):

```json
{
  "fingerprint": "…", "chars": 9310, "max_chars": 12000,
  "files":   [{"path": "src/a.py", "repo": "", "why": "en scope"}],
  "tests":   [{"path": "tests/test_a.py", "covers": "src/a.py", "command": "test"}],
  "history": [{"sha": "1a2b3c4", "date": "2026-10-30", "subject": "…", "paths": ["src/a.py"]}],
  "tasks":   [{"number": 12, "title": "…", "outcome": "SUCCEEDED", "findings": ["…"]}],
  "lessons": [{"id": 7, "text": "…"}],
  "omitted": [{"kind": "history", "count": 14, "why": "tope"}],
  "notes":   ["sin tests detectados para la zona"]
}
```

**Reglas**:

- `chars` ≤ `max_chars`, siempre.
- Lo omitido se cuenta por tipo.
- Si la huella no cambia, el paquete se reutiliza.

## Global: `~/.umbra/lessons.db` (WAL)

### `lesson`

| Campo        | Tipo    | Notas                                                         |
|--------------|---------|---------------------------------------------------------------|
| project_key  | TEXT    | clave de proyecto o espacio (ver research §7)                 |
| number       | INTEGER | consecutivo por proyecto; la persona lo ve como `L<n>`        |
| text         | TEXT    | ≤ 400 caracteres, sin secretos                                |
| zone         | TEXT    | lista JSON de globs relativos (con prefijo `repo/` en un espacio); `[]` = todo el proyecto |
| status       | TEXT    | `proposed`, `approved`, `discarded` o `retired`               |
| conflicts    | TEXT    | lista JSON de `number` en conflicto sin resolver              |
| project_name | TEXT    | nombre legible, para listar y exportar                        |
| created_at   | TEXT    | UTC                                                           |
| updated_at   | TEXT    | UTC                                                           |

PK `(project_key, number)`.

### `lesson_origin`

| Campo       | Tipo    | Notas                                                    |
|-------------|---------|----------------------------------------------------------|
| project_key | TEXT    |                                                          |
| number      | INTEGER | FK a `lesson`                                            |
| kind        | TEXT    | `review_rejected`, `run_stopped` o `human_correction`    |
| task        | INTEGER | número de tarea                                          |
| run_id      | TEXT    |                                                          |
| stage       | TEXT    |                                                          |
| detail      | TEXT    | hallazgo, motivo o mensaje de la persona (sin secretos)  |
| event_id    | INTEGER | evento fuente en `.umbra/umbra.db`                       |
| created_at  | TEXT    |                                                          |

UNIQUE `(project_key, run_id, event_id)`: cosechar dos veces no duplica.

### `lesson_history`

| Campo       | Tipo    | Notas                                                          |
|-------------|---------|----------------------------------------------------------------|
| project_key | TEXT    |                                                                |
| number      | INTEGER |                                                                |
| action      | TEXT    | `proposed`, `approved`, `edited`, `discarded`, `retired`, `merged_origin`, `conflict` o `resolved` |
| actor       | TEXT    | usuario del sistema, o `telegram:<chat_id>`                    |
| channel     | TEXT    | `cli`, `watch`, `telegram` o `engine`                          |
| before      | TEXT    | texto o zona anteriores, si se editaron                        |
| created_at  | TEXT    |                                                                |

### `lesson_meta`

`(key, value)`: versión del esquema y alias de claves migradas (de ruta a primer commit).

## Estados de una lección

```text
proposed ──aprobar──▶ approved ──retirar──▶ retired
    │                    ▲
    └──descartar──▶ discarded

(origen nuevo equivalente) ─▶ suma un origen; no cambia el estado
```

- Solo la persona hace las transiciones, desde la CLI, `watch` o Telegram. El motor solo crea
  propuestas y suma orígenes.
- Una lección `discarded` no se vuelve a proponer: los orígenes equivalentes se suman a ella.
- Una lección `retired` se puede volver a aprobar con `umbra lesson approve`, y eso queda en el
  historial.

## Qué se aplica a una tarea

Una lección entra en el paquete si cumple todo esto:

- `status = approved`;
- `conflicts` está vacía;
- su zona es `[]` o algún glob coincide con un archivo de la zona de la tarea.

**Orden**: primero las de zona específica y luego las de todo el proyecto; dentro de cada grupo,
la aprobación más reciente primero.

Una lección está **posiblemente obsoleta** cuando ningún glob de su zona coincide con
`git ls-files`. Se calcula al listar, no se guarda.
