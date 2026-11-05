# Data Model: E0 (esquema v1)

Todas las tablas viven en `.umbra/umbra.db`. `id` = uuid4 hex salvo indicación. Fechas ISO-8601 UTC.

| Tabla | Columnas | Restricciones |
| --- | --- | --- |
| spec | id, version, content_hash, body, author, created_at | UNIQUE(version) |
| task | id, number, title, description, acceptance (JSON), scope (JSON), priority, status, spec_id?, revision, created_at, updated_at | UNIQUE(number); status ∈ draft/accepted/dropped/done |
| dependency | task_id, depends_on_id | PK(task_id, depends_on_id); CHECK(task_id <> depends_on_id) |
| run | id, task_id, routine, status, stage, base_sha, head_sha, branch, idempotency_key, created_at, updated_at | UNIQUE(idempotency_key); status ∈ QUEUED/RUNNING/PAUSED/WAITING_APPROVAL/BLOCKED/FAILED/CANCELLED/SUCCEEDED |
| attempt | id, run_id, stage, attempt_no, profile, agent, session_id, status, started_at, ended_at | UNIQUE(run_id, stage, attempt_no) |
| artifact | id, attempt_id?, run_id, kind, path, checksum, tested_sha, command, exit_code, created_at | — |
| finding | id, attempt_id, severity, rule, file, line, message, status | severity ∈ info/low/medium/high/critical |
| approval | id, run_id, head_sha, decision, actor, created_at | UNIQUE(run_id, head_sha, actor) |
| usage | id, attempt_id, agent, model, input_tokens, output_tokens, cost (TEXT decimal), estimated (0/1), invocation_id | UNIQUE(invocation_id) |
| event | run_id?, seq, type, origin, actor, payload (JSON), created_at | PK autoincrement; UNIQUE(run_id, seq) |
| operation | operation_key, kind, status, external_ref, updated_at | PK(operation_key) |
| lease | name, owner, token, expires_at | PK(name) |

Migraciones: `user_version` 0 → 1 crea todo lo anterior. Cada migración futura se añade al final
de la lista y nunca se edita una ya publicada.
