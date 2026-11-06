"""Almacén SQLite del proyecto (.umbra/umbra.db)."""

import sqlite3
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

DB_NAME = "umbra.db"

RUN_STATES = (
    "QUEUED", "RUNNING", "PAUSED", "WAITING_APPROVAL",
    "BLOCKED", "FAILED", "CANCELLED", "SUCCEEDED",
)
ACTIVE_RUN_STATES = ("QUEUED", "RUNNING", "PAUSED", "WAITING_APPROVAL")

_V1 = """
CREATE TABLE spec (
    id TEXT PRIMARY KEY, version INTEGER NOT NULL UNIQUE, content_hash TEXT NOT NULL,
    body TEXT NOT NULL, author TEXT, created_at TEXT NOT NULL
);
CREATE TABLE task (
    id TEXT PRIMARY KEY, number INTEGER NOT NULL UNIQUE, title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '', acceptance TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL DEFAULT '[]', priority INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'accepted', 'dropped', 'done')),
    spec_id TEXT REFERENCES spec(id), revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE dependency (
    task_id TEXT NOT NULL REFERENCES task(id),
    depends_on_id TEXT NOT NULL REFERENCES task(id),
    PRIMARY KEY (task_id, depends_on_id),
    CHECK (task_id <> depends_on_id)
);
CREATE TABLE run (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES task(id), routine TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'PAUSED', 'WAITING_APPROVAL',
        'BLOCKED', 'FAILED', 'CANCELLED', 'SUCCEEDED')),
    stage TEXT, base_sha TEXT, head_sha TEXT, branch TEXT, worktree TEXT,
    idempotency_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE attempt (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES run(id), stage TEXT NOT NULL,
    attempt_no INTEGER NOT NULL, profile TEXT, agent TEXT, session_id TEXT,
    status TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
    UNIQUE (run_id, stage, attempt_no)
);
CREATE TABLE artifact (
    id TEXT PRIMARY KEY, run_id TEXT REFERENCES run(id), attempt_id TEXT REFERENCES attempt(id),
    kind TEXT NOT NULL, path TEXT NOT NULL, checksum TEXT, tested_sha TEXT,
    command TEXT, exit_code INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE finding (
    id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempt(id),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),
    rule TEXT, file TEXT, line INTEGER, message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE approval (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES run(id), head_sha TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE (run_id, head_sha, actor)
);
CREATE TABLE usage (
    id TEXT PRIMARY KEY, attempt_id TEXT REFERENCES attempt(id), agent TEXT NOT NULL,
    model TEXT, input_tokens INTEGER, output_tokens INTEGER, cost TEXT NOT NULL DEFAULT '0',
    estimated INTEGER NOT NULL DEFAULT 0, invocation_id TEXT NOT NULL UNIQUE
);
CREATE TABLE event (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT REFERENCES run(id), seq INTEGER,
    type TEXT NOT NULL, origin TEXT NOT NULL, actor TEXT, payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE (run_id, seq)
);
CREATE TABLE operation (
    operation_key TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
    external_ref TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE lease (
    name TEXT PRIMARY KEY, owner TEXT NOT NULL, token INTEGER NOT NULL, expires_at TEXT NOT NULL
);
"""

_V2 = """
CREATE TABLE conversation (
    id TEXT PRIMARY KEY,
    idea TEXT NOT NULL,
    spec_dir TEXT,
    phase TEXT NOT NULL CHECK (phase IN ('specify', 'clarify', 'spec_review',
        'plan', 'plan_review', 'tasks', 'done', 'discarded')),
    session_id TEXT,
    cost_seen TEXT NOT NULL DEFAULT '0',
    origin TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
ALTER TABLE spec ADD COLUMN dir TEXT;
ALTER TABLE task ADD COLUMN spec_dir TEXT;
ALTER TABLE task ADD COLUMN story TEXT;
ALTER TABLE task ADD COLUMN requirements TEXT NOT NULL DEFAULT '[]';
ALTER TABLE task ADD COLUMN story_hash TEXT;
ALTER TABLE usage ADD COLUMN conversation_id TEXT REFERENCES conversation(id);
CREATE UNIQUE INDEX task_story ON task(spec_dir, story) WHERE story IS NOT NULL;
"""

_V3 = """
ALTER TABLE task ADD COLUMN about TEXT NOT NULL DEFAULT '';
"""

_V4 = """
CREATE INDEX run_task ON run(task_id, created_at);
CREATE INDEX usage_attempt ON usage(attempt_id);
"""

_V5 = """
ALTER TABLE task ADD COLUMN allowed_paths TEXT NOT NULL DEFAULT '[]';
"""

# ponytail: migraciones = lista de scripts por user_version; nunca editar uno ya publicado.
_V6 = """
ALTER TABLE run ADD COLUMN base_branch TEXT;
"""
# espacios de trabajo (spec 032): en qué repo(s) del espacio se hace la tarea (lista JSON)
_V7 = """
ALTER TABLE task ADD COLUMN repos TEXT NOT NULL DEFAULT '[]';
"""
# tareas entre repos (spec 033): base y último commit de la ejecución en cada repo
_V8 = """
CREATE TABLE run_part (
    run_id TEXT NOT NULL REFERENCES run(id), repo TEXT NOT NULL,
    base_sha TEXT NOT NULL, head_sha TEXT,
    PRIMARY KEY (run_id, repo)
);
"""
# contexto por tarea (spec 035): los archivos que cambió cada ejecución
_V9 = """
CREATE TABLE run_file (
    run_id TEXT NOT NULL REFERENCES run(id), repo TEXT NOT NULL DEFAULT '', path TEXT NOT NULL,
    PRIMARY KEY (run_id, repo, path)
);
"""
MIGRATIONS = [_V1, _V2, _V3, _V4, _V5, _V6, _V7, _V8, _V9]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def new_id() -> str:
    return uuid.uuid4().hex


def connect(path: Path, same_thread: bool = True) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None,
                           check_same_thread=same_thread)
    conn.row_factory = sqlite3.Row
    for attempt in range(50):  # ponytail: pasar a WAL no espera al busy timeout; ~5 s y se rinde
        try:
            if conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                conn.execute("PRAGMA journal_mode=WAL")
            break
        except sqlite3.OperationalError:
            if attempt == 49:
                raise
            time.sleep(0.1)
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    return conn


def open_store(umbra_dir: Path, same_thread: bool = True) -> sqlite3.Connection:
    return connect(umbra_dir / DB_NAME, same_thread)


def data_version(conn: sqlite3.Connection) -> int:
    """Cambia cuando OTRA conexión escribe: permite saber si hay algo nuevo sin consultar."""
    return conn.execute("PRAGMA data_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> int:
    """Aplica las migraciones pendientes. Si otro proceso abre la misma base a la vez (el puente
    y un worker sobre un proyecto nuevo), una de las dos falla al crear lo que la otra ya creó:
    se deshace, se relee la versión y se sigue desde ahí."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    while version < len(MIGRATIONS):
        try:
            conn.executescript(f"BEGIN IMMEDIATE;\n{MIGRATIONS[version]}\n"
                               f"PRAGMA user_version = {version + 1};\nCOMMIT;")
        except sqlite3.OperationalError:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            if conn.execute("PRAGMA user_version").fetchone()[0] <= version:
                raise  # nadie más la aplicó: es un error de verdad
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    return len(MIGRATIONS)


def to_cost(value: Decimal | str | int | float) -> str:
    # ponytail: float solo entra convertido vía str para no arrastrar error binario.
    return format(Decimal(str(value)).normalize(), "f")


def status_summary(conn: sqlite3.Connection) -> dict:
    tasks = {s: 0 for s in ("draft", "accepted", "done", "dropped")}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM task GROUP BY status"):
        tasks[row["status"]] = row["n"]
    marks = ",".join("?" * len(ACTIVE_RUN_STATES))
    active = [
        dict(r)
        for r in conn.execute(
            f"SELECT r.id, t.number AS task, r.status, r.stage FROM run r "
            f"JOIN task t ON t.id = r.task_id WHERE r.status IN ({marks}) ORDER BY r.created_at",
            ACTIVE_RUN_STATES,
        )
    ]
    total = estimated = Decimal(0)
    unpriced = 0
    for row in conn.execute("SELECT cost, estimated, input_tokens, output_tokens FROM usage"):
        total += Decimal(row["cost"])
        if row["estimated"]:
            estimated += Decimal(row["cost"])
        unpriced += _unpriced(row)
    return {
        "tasks": tasks,
        "active_runs": active,
        "spend": {"total": str(total), "estimated": str(estimated)},
        "unpriced_tokens": unpriced,
    }


def _unpriced(row) -> int:
    """Tokens sin precio: Codex informa tokens pero no dólares (y $0.00 sería mentira)."""
    if row["estimated"] and Decimal(row["cost"]) == 0:
        return (row["input_tokens"] or 0) + (row["output_tokens"] or 0)
    return 0


def run_spend(conn: sqlite3.Connection, run_id: str) -> tuple[Decimal, int]:
    """(dólares conocidos, tokens sin precio) de una ejecución."""
    total, tokens = Decimal(0), 0
    for row in conn.execute(
            "SELECT u.cost, u.estimated, u.input_tokens, u.output_tokens FROM usage u"
            " JOIN attempt a ON a.id = u.attempt_id WHERE a.run_id = ?", (run_id,)):
        total += Decimal(row["cost"])
        tokens += _unpriced(row)
    return total, tokens
