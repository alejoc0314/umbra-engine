"""Lecciones aprendidas (spec 035): umbra propone reglas a partir de sus tropiezos.

Viven fuera del repo, en `~/.umbra/lessons.db`, separadas por clave de proyecto. El motor solo
crea propuestas y suma orígenes; aprobar, descartar o retirar es cosa de la persona. Una
propuesta nunca entra en el contexto de una tarea."""

import fnmatch
import hashlib
import itertools
import json
import re
import sqlite3
import subprocess
from pathlib import Path, PurePosixPath

from umbra.actions.secrets import PATTERNS
from umbra.contracts.envelope import Finding, LessonDraft
from umbra.management import memory
from umbra.unified import config as cfg
from umbra.unified import project as proj
from umbra.unified.store import now

TEXT_CHARS = 280  # lo que puede proponer el redactor
STORED_CHARS = 400  # lo que se guarda (la persona puede editar algo más largo)
DETAIL_CHARS = 1000
HIDDEN = "«oculto»"
SOURCES = ("stage.rework", "run.blocked", "run.failed", "human.fixed", "run.rejected")
# detenciones que no enseñan nada del proyecto: fallos puntuales o esperas de la persona
TRANSIENT = {"agent_timeout", "agent_error", "base_conflict", "design_review", "design_choice",
             "lease_lost", "cancelled"}
_SEVERITY = re.compile(r"^\[(info|low|medium|high|critical)\]\s*")
_LOCATION = re.compile(r"\s*\(([^()\s]+):(\d+)\)")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lesson (
    project_key TEXT NOT NULL, number INTEGER NOT NULL, text TEXT NOT NULL,
    zone TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('proposed', 'approved', 'discarded', 'retired')),
    conflicts TEXT NOT NULL DEFAULT '[]', project_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (project_key, number)
);
CREATE TABLE IF NOT EXISTS lesson_origin (
    project_key TEXT NOT NULL, number INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('review_rejected', 'run_stopped', 'human_correction')),
    task INTEGER, run_id TEXT NOT NULL, stage TEXT, detail TEXT NOT NULL DEFAULT '',
    event_id INTEGER NOT NULL, created_at TEXT NOT NULL,
    UNIQUE (project_key, run_id, event_id)
);
CREATE TABLE IF NOT EXISTS lesson_history (
    project_key TEXT NOT NULL, number INTEGER NOT NULL, action TEXT NOT NULL,
    actor TEXT NOT NULL, channel TEXT NOT NULL, before TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lesson_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


# ---------- almacén ----------
def open_db() -> sqlite3.Connection:
    path = cfg.umbra_home() / "lessons.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, isolation_level=None, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA busy_timeout = 5000")
    db.executescript(SCHEMA)
    db.execute("INSERT OR IGNORE INTO lesson_meta (key, value) VALUES ('schema_version', '1')")
    return db


def _path_key(root: Path) -> str:
    return "path:" + hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()


def _repo_key(root: Path) -> str:
    try:
        proc = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=root,
                              capture_output=True, text=True, timeout=10)
        roots = proc.stdout.split() if proc.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        roots = []
    if roots:
        return min(roots)
    return _path_key(root)


def _combine(keys) -> str:
    keys = sorted(keys)
    if len(keys) == 1:
        return keys[0]
    return "space:" + hashlib.sha256("\n".join(keys).encode()).hexdigest()


def project_key(roots) -> str:
    """Repo: su primer commit. Espacio: hash de las claves de sus repos. Sin commits: la ruta."""
    return _combine(_repo_key(Path(r)) for r in roots)


def _former_keys(roots) -> tuple[str, list[str]]:
    """La clave vigente y todas las que pudo tener antes el mismo conjunto de repos: cada repo
    con commits pudo estar sin ellos (clave `path:`), en cualquier combinación."""
    keys = [_repo_key(Path(r)) for r in roots]
    current = _combine(keys)
    choices = [(k,) if k.startswith("path:") else (k, _path_key(Path(r)))
               for r, k in zip(roots, keys, strict=True)]
    olds = [_combine(c) for c in itertools.product(*choices)]
    return current, [o for o in dict.fromkeys(olds) if o != current]


def migrate(db: sqlite3.Connection, roots) -> str:
    """Un repo que recibe su primer commit cambia de clave (`path:` → primer commit): sus
    lecciones pasan a la clave nueva (renumeradas tras las que ya tuviera) y queda un alias.
    En un espacio se revisan todas las combinaciones de repos que pudieron estar sin commits,
    así que vale aunque varios reciban su primer commit entre dos consultas. Idempotente.
    Devuelve la clave vigente sin resolver alias."""
    current, olds = _former_keys(roots)
    for old in olds:
        if old == current or not db.execute(
                "SELECT 1 FROM lesson WHERE project_key = ? LIMIT 1", (old,)).fetchone():
            continue
        db.execute("BEGIN IMMEDIATE")
        try:
            offset = db.execute("SELECT COALESCE(MAX(number), 0) FROM lesson WHERE"
                                " project_key = ?", (current,)).fetchone()[0]
            moved = [r["number"] for r in db.execute(
                "SELECT number FROM lesson WHERE project_key = ?", (old,))]
            for table in ("lesson", "lesson_origin", "lesson_history"):
                db.execute(f"UPDATE {table} SET project_key = ?, number = number + ? WHERE"
                           " project_key = ?", (current, offset, old))
            if offset:
                for n in moved:
                    row = _get(db, current, n + offset)
                    db.execute("UPDATE lesson SET conflicts = ? WHERE project_key = ? AND"
                               " number = ?", (json.dumps([c + offset for c in json.loads(
                                   row["conflicts"])]), current, n + offset))
            db.execute("INSERT OR REPLACE INTO lesson_meta (key, value) VALUES (?, ?)",
                       (f"alias:{old}", current))
            # los alias que apuntaban a la clave que acaba de migrar siguen a la nueva
            db.execute("UPDATE lesson_meta SET value = ? WHERE key LIKE 'alias:%' AND value = ?",
                       (current, old))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return current


def resolve(db: sqlite3.Connection, key: str) -> str:
    """La clave vigente: una clave migrada (de ruta a primer commit) apunta a la nueva, y se
    sigue la cadena si la nueva migró a su vez."""
    for _ in range(16):  # acotado: una cadena de alias nunca debería ser larga ni cíclica
        row = db.execute("SELECT value FROM lesson_meta WHERE key = ?",
                         (f"alias:{key}",)).fetchone()
        if row is None or row["value"] == key:
            break
        key = row["value"]
    return key


def redact(text: str) -> str:
    for pattern in PATTERNS.values():
        text = pattern.sub(HIDDEN, text)
    return text


def zone_ok(glob: str) -> bool:
    g = glob.replace("\\", "/").strip()
    return bool(g) and not g.startswith("/") and not re.match(r"^[A-Za-z]:", g) \
        and ".." not in g.split("/")


# ---------- borrador y validación ----------
def _clean(message: str) -> str:
    text = _LOCATION.sub("", _SEVERITY.sub("", message.strip()))
    return " ".join(text.split())


def draft(message: str, files: list[str]) -> LessonDraft:
    """Borrador determinista: el hallazgo, motivo o mensaje sin `archivo:línea`; la zona son
    las carpetas de los archivos implicados (el archivo mismo si está en la raíz)."""
    zone: list[str] = []
    for f in files:
        f = f.replace("\\", "/")
        parent = str(PurePosixPath(f).parent)
        glob = f"{parent}/**" if parent != "." else f
        if zone_ok(glob) and glob not in zone:
            zone.append(glob)
    return LessonDraft(text=_clean(message)[:TEXT_CHARS], zone=zone)


def validate(d: LessonDraft, known: set[int]) -> LessonDraft | None:
    """Lo que el motor acepta del redactor (principio III); None = usar el borrador."""
    if d.skip:
        return d
    text = " ".join(d.text.split())
    if not text or len(text) > TEXT_CHARS:
        return None
    if any(not zone_ok(z) for z in d.zone):
        return None
    if d.same_as is not None and d.same_as not in known:
        return None
    return d.model_copy(update={"text": text,
                                "conflicts_with": [c for c in d.conflicts_with if c in known]})


def record(db: sqlite3.Connection, key: str, d: LessonDraft, origins: list[dict],
           project_name: str) -> int | None:
    """Crea la propuesta `L<max+1>` o, si equivale a una existente (mismo texto normalizado y
    zona, o `same_as`), solo le suma los orígenes. Devuelve el número si es nueva."""
    text = redact(" ".join(d.text.split()))[:STORED_CHARS]
    zone = list(dict.fromkeys(z.replace("\\", "/") for z in d.zone))
    stamp = now()
    db.execute("BEGIN IMMEDIATE")
    try:
        target = None
        if d.same_as is not None and db.execute(
                "SELECT 1 FROM lesson WHERE project_key = ? AND number = ?",
                (key, d.same_as)).fetchone():
            target = d.same_as
        else:
            for r in db.execute("SELECT number, text, zone FROM lesson WHERE project_key = ?",
                                (key,)):
                if (memory.normalize(r["text"]) == memory.normalize(text)
                        and sorted(json.loads(r["zone"])) == sorted(zone)):
                    target = r["number"]
                    break
        fresh = [o for o in origins if not db.execute(
            "SELECT 1 FROM lesson_origin WHERE project_key = ? AND run_id = ? AND event_id = ?",
            (key, o["run_id"], o["event_id"])).fetchone()]
        created = None
        if target is None and fresh:
            created = target = db.execute(
                "SELECT COALESCE(MAX(number), 0) + 1 FROM lesson WHERE project_key = ?",
                (key,)).fetchone()[0]
            db.execute(
                "INSERT INTO lesson (project_key, number, text, zone, status, conflicts,"
                " project_name, created_at, updated_at) VALUES (?, ?, ?, ?, 'proposed', ?, ?,"
                " ?, ?)", (key, target, text, json.dumps(zone), json.dumps(d.conflicts_with),
                           project_name, stamp, stamp))
            _history(db, key, target, "proposed", stamp)
            for other in d.conflicts_with:  # el conflicto se marca en las dos
                row = db.execute("SELECT conflicts FROM lesson WHERE project_key = ? AND"
                                 " number = ?", (key, other)).fetchone()
                if row is None or other == target:
                    continue
                db.execute("UPDATE lesson SET conflicts = ? WHERE project_key = ? AND"
                           " number = ?", (json.dumps(sorted(set(json.loads(row["conflicts"]))
                                                             | {target})), key, other))
                _history(db, key, other, "conflict", stamp)
        elif target is not None and fresh:
            _history(db, key, target, "merged_origin", stamp)
        for o in fresh:
            db.execute(
                "INSERT OR IGNORE INTO lesson_origin (project_key, number, kind, task, run_id,"
                " stage, detail, event_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (key, target, o["kind"], o.get("task"), o["run_id"], o.get("stage"),
                 redact(o.get("detail") or "")[:DETAIL_CHARS], o["event_id"],
                 o.get("created_at") or stamp))
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return created


def _history(db, key: str, number: int, action: str, stamp: str, actor: str = "umbra",
             channel: str = "engine", before: str | None = None) -> None:
    db.execute("INSERT INTO lesson_history (project_key, number, action, actor, channel,"
               " before, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (key, number, action, actor, channel, before, stamp))


# ---------- decisiones de la persona ----------
class LessonError(Exception):
    """Un error para la persona: la lección no existe o la transición no vale."""


STATUS_ES = {"proposed": "propuesta", "approved": "aprobada", "discarded": "descartada",
             "retired": "retirada"}
# acción → (estados desde los que vale, estado al que lleva)
TRANSITIONS = {"approve": ({"proposed", "retired"}, "approved"),
               "discard": ({"proposed"}, "discarded"),
               "retire": ({"approved"}, "retired")}
_VERBS = {"approve": "aprobar", "discard": "descartar", "retire": "retirar"}
_NUMBER = re.compile(r"^[Ll]?(\d+)$")


def parse_number(ref: str | int) -> int:
    """`L7` o `7` → 7."""
    m = _NUMBER.match(str(ref).strip())
    if not m:
        raise LessonError(f"«{ref}» no es una lección: usa L7 o 7")
    return int(m.group(1))


def _matches(glob: str, path: str) -> bool:
    return fnmatch.fnmatchcase(path.replace("\\", "/"), glob.replace("\\", "/"))


def stale(zone: list[str], files: list[str]) -> bool:
    """Posiblemente obsoleta: tiene zona y ningún archivo actual del repo cae en ella."""
    return bool(zone) and not any(_matches(g, f) for g in zone for f in files)


def _get(db, key: str, n: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM lesson WHERE project_key = ? AND number = ?",
                     (key, n)).fetchone()
    if row is None:
        raise LessonError(f"L{n} no existe en este proyecto (mira `umbra lesson list --all`)")
    return row


def _item(db, row, files: list[str] | None = None) -> dict:
    zone = json.loads(row["zone"])
    origins = db.execute("SELECT COUNT(*) FROM lesson_origin WHERE project_key = ? AND"
                         " number = ?", (row["project_key"], row["number"])).fetchone()[0]
    return {"id": f"L{row['number']}", "number": row["number"], "status": row["status"],
            "text": row["text"], "zone": zone, "origins": origins,
            "stale": stale(zone, files) if files else False,
            "conflicts": [f"L{c}" for c in json.loads(row["conflicts"])],
            "updated_at": row["updated_at"]}


_ORDER = {"proposed": 0, "approved": 1, "retired": 2, "discarded": 3}


def list_(db, key: str, status: str | None = None, all_: bool = False,
          files: list[str] | None = None) -> list[dict]:
    """Por defecto propuestas y aprobadas (propuestas primero); `all_` incluye el resto."""
    rows = list(db.execute("SELECT * FROM lesson WHERE project_key = ?", (key,)))
    if status:
        rows = [r for r in rows if r["status"] == status]
    elif not all_:
        rows = [r for r in rows if r["status"] in ("proposed", "approved")]
    rows.sort(key=lambda r: (_ORDER[r["status"]], -r["number"]))
    return [_item(db, r, files) for r in rows]


def show(db, key: str, n: int, conn: sqlite3.Connection | None = None,
         files: list[str] | None = None) -> dict:
    """La lección con sus orígenes, su historial y las tareas en las que se aplicó."""
    out = _item(db, _get(db, key, n), files)
    out["origins_detail"] = [dict(r) for r in db.execute(
        "SELECT kind, task, run_id, stage, detail, created_at FROM lesson_origin WHERE"
        " project_key = ? AND number = ? ORDER BY created_at, rowid", (key, n))]
    out["history"] = [dict(r) for r in db.execute(
        "SELECT action, actor, channel, before, created_at FROM lesson_history WHERE"
        " project_key = ? AND number = ? ORDER BY rowid", (key, n))]
    out["applied_in"] = applied_in(conn, n) if conn is not None else []
    return out


def applied_in(conn: sqlite3.Connection, n: int) -> list[dict]:
    """Las ejecuciones cuyo paquete de contexto llevó la lección (eventos `explore.ready`)."""
    out = []
    try:
        rows = list(conn.execute(
            "SELECT e.run_id, e.payload, e.created_at, t.number FROM event e JOIN run r ON"
            " r.id = e.run_id JOIN task t ON t.id = r.task_id WHERE e.type = 'explore.ready'"
            " ORDER BY e.id"))
    except sqlite3.Error:
        return []
    for r in rows:
        used = json.loads(r["payload"] or "{}").get("lessons") or []
        if any(isinstance(x, dict) and x.get("id") == n for x in used):
            out.append({"task": r["number"], "run_id": r["run_id"],
                        "created_at": r["created_at"]})
    return out


def _move(db, key: str, n: int, action: str, actor: str, channel: str,
          changes: dict | None = None, before: str | None = None) -> dict:
    allowed, target = TRANSITIONS[action]
    db.execute("BEGIN IMMEDIATE")
    try:
        row = _get(db, key, n)
        if row["status"] not in allowed:
            raise LessonError(f"no se puede {_VERBS[action]} L{n}: está "
                              f"{STATUS_ES[row['status']]}")
        stamp = now()
        sets = {"status": target, "updated_at": stamp, **(changes or {})}
        db.execute(f"UPDATE lesson SET {', '.join(f'{c} = ?' for c in sets)} WHERE"
                   " project_key = ? AND number = ?", (*sets.values(), key, n))
        _history(db, key, n, target, stamp, actor, channel, before)
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return _item(db, _get(db, key, n))


def approve(db, key: str, n: int, text: str | None = None, zone: list[str] | None = None,
            project_wide: bool = False, *, actor: str, channel: str) -> dict:
    """Aprueba (o vuelve a aprobar una retirada). Si se edita, lo anterior va al historial."""
    row = _get(db, key, n)
    changes, before = {}, {}
    if text is not None:
        clean = redact(" ".join(text.split()))
        if not clean or len(clean) > STORED_CHARS:
            raise LessonError(f"el texto debe tener entre 1 y {STORED_CHARS} caracteres")
        if clean != row["text"]:
            changes["text"], before["text"] = clean, row["text"]
    if project_wide or zone is not None:
        new = [] if project_wide else list(dict.fromkeys(
            z.replace("\\", "/").strip() for z in zone if z.strip()))
        if any(not zone_ok(z) for z in new):
            raise LessonError("la zona debe ser un glob relativo al repo, sin «..» "
                              "(p. ej. src/pagos/**)")
        if new != json.loads(row["zone"]):
            changes["zone"], before["zone"] = json.dumps(new), json.loads(row["zone"])
    return _move(db, key, n, "approve", actor, channel, changes,
                 json.dumps(before, ensure_ascii=False) if before else None)


def discard(db, key: str, n: int, reason: str = "", *, actor: str, channel: str) -> dict:
    return _move(db, key, n, "discard", actor, channel,
                 before=json.dumps({"reason": reason}, ensure_ascii=False) if reason else None)


def retire(db, key: str, n: int, reason: str = "", *, actor: str, channel: str) -> dict:
    return _move(db, key, n, "retire", actor, channel,
                 before=json.dumps({"reason": reason}, ensure_ascii=False) if reason else None)


def resolve_conflict(db, key: str, a: int, b: int, *, actor: str, channel: str) -> list[dict]:
    """Marca dos lecciones como compatibles: quita el conflicto entre ellas."""
    db.execute("BEGIN IMMEDIATE")
    try:
        rows = {a: _get(db, key, a), b: _get(db, key, b)}
        stamp = now()
        for n, other in ((a, b), (b, a)):
            left = [c for c in json.loads(rows[n]["conflicts"]) if c != other]
            db.execute("UPDATE lesson SET conflicts = ?, updated_at = ? WHERE project_key = ?"
                       " AND number = ?", (json.dumps(left), stamp, key, n))
            _history(db, key, n, "resolved", stamp, actor, channel, f"L{other}")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return [_item(db, _get(db, key, a)), _item(db, _get(db, key, b))]


def applicable(db, key: str, files: list[str]) -> list[dict]:
    """Las aprobadas y sin conflicto que tocan los archivos (zona `[]` = todo el proyecto):
    primero las de zona específica y, dentro de cada grupo, la aprobación más reciente."""
    out = []
    for r in db.execute("SELECT * FROM lesson WHERE project_key = ? AND status = 'approved'"
                        " ORDER BY updated_at DESC, number DESC", (key,)):
        if json.loads(r["conflicts"]):
            continue
        zone = json.loads(r["zone"])
        if zone and not any(_matches(g, f) for g in zone for f in files):
            continue
        out.append({"id": r["number"], "text": r["text"], "zone": zone})
    out.sort(key=lambda x: not x["zone"])  # estable: conserva lo más reciente primero
    return out


# ---------- exportar e importar (US5) ----------
EXPORT_SCHEMA = 1
_ORIGIN_COLS = ("kind", "task", "run_id", "stage", "detail", "event_id", "created_at")
_HISTORY_COLS = ("action", "actor", "channel", "before", "created_at")


def export(db, key: str, project_name: str) -> dict:
    """Todas las lecciones con su estado, orígenes, historial y fechas. Sin la clave de
    proyecto: es local de esta máquina."""
    out = []
    for r in db.execute("SELECT * FROM lesson WHERE project_key = ? ORDER BY number", (key,)):
        n = r["number"]
        out.append({
            "number": n, "text": r["text"], "zone": json.loads(r["zone"]),
            "status": r["status"], "conflicts": json.loads(r["conflicts"]),
            "created_at": r["created_at"], "updated_at": r["updated_at"],
            "origins": [dict(o) for o in db.execute(
                f"SELECT {', '.join(_ORIGIN_COLS)} FROM lesson_origin WHERE project_key = ?"
                " AND number = ? ORDER BY rowid", (key, n))],
            "history": [dict(h) for h in db.execute(
                f"SELECT {', '.join(_HISTORY_COLS)} FROM lesson_history WHERE"
                " project_key = ? AND number = ? ORDER BY rowid", (key, n))]})
    return {"schema": EXPORT_SCHEMA, "project_name": project_name, "exported_at": now(),
            "lessons": out}


def _check(data) -> list[dict]:
    if not isinstance(data, dict) or data.get("schema") != EXPORT_SCHEMA:
        raise LessonError("el archivo no es una exportación de lecciones que umbra entienda "
                          f"(esquema {EXPORT_SCHEMA})")
    items = data.get("lessons")
    if not isinstance(items, list):
        raise LessonError("el archivo no trae la lista de lecciones")
    for it in items:
        ok = (isinstance(it, dict) and isinstance(it.get("number"), int)
              and isinstance(it.get("text"), str) and it["text"].strip()
              and it.get("status") in STATUS_ES and isinstance(it.get("zone", []), list)
              and all(isinstance(z, str) and zone_ok(z) for z in it.get("zone", []))
              and isinstance(it.get("created_at"), str)
              and isinstance(it.get("updated_at"), str))
        if not ok:
            raise LessonError(f"lección inválida en el archivo: {str(it)[:120]}")
    return items


def import_(db, key: str, data: dict, project_name: str) -> dict:
    """Trae lecciones exportadas. Una equivalente (mismo texto normalizado y zona) ya existente
    se fusiona: suma orígenes e historial que falten y conserva el estado local (regla
    conservadora). Las nuevas toman `L<max+1>` con su estado y fechas, y los conflictos se
    renumeran. Importar dos veces no duplica nada."""
    items = _check(data)
    created = merged = added = 0
    db.execute("BEGIN IMMEDIATE")
    try:
        existing = [(r["number"], memory.normalize(r["text"]), sorted(json.loads(r["zone"])))
                    for r in db.execute("SELECT number, text, zone FROM lesson WHERE"
                                        " project_key = ?", (key,))]
        nxt = max((n for n, _, _ in existing), default=0)
        mapping: dict[int, int] = {}
        fresh: set[int] = set()
        for it in items:
            text = redact(" ".join(it["text"].split()))[:STORED_CHARS]
            zone = list(dict.fromkeys(z.replace("\\", "/") for z in it.get("zone", [])))
            norm = memory.normalize(text)
            local = next((n for n, t, z in existing if t == norm and z == sorted(zone)), None)
            if local is None:
                nxt += 1
                local = nxt
                db.execute(
                    "INSERT INTO lesson (project_key, number, text, zone, status, conflicts,"
                    " project_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, '[]', ?, ?,"
                    " ?)", (key, local, text, json.dumps(zone), it["status"], project_name,
                            it["created_at"], it["updated_at"]))
                existing.append((local, norm, sorted(zone)))
                fresh.add(local)
                created += 1
            else:
                merged += 1
            mapping[it["number"]] = local
            for o in it.get("origins") or []:
                cur = db.execute(
                    "INSERT OR IGNORE INTO lesson_origin (project_key, number, kind, task,"
                    " run_id, stage, detail, event_id, created_at) VALUES"
                    " (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (key, local, o["kind"], o.get("task"), o["run_id"], o.get("stage"),
                     redact(o.get("detail") or "")[:DETAIL_CHARS], o["event_id"],
                     o["created_at"]))
                added += cur.rowcount
            for h in it.get("history") or []:
                before = redact(h["before"]) if h.get("before") else None
                if local not in fresh and db.execute(
                        "SELECT 1 FROM lesson_history WHERE project_key = ? AND number = ? AND"
                        " action = ? AND actor = ? AND channel = ? AND created_at = ?",
                        (key, local, h["action"], h["actor"], h["channel"],
                         h["created_at"])).fetchone():
                    continue
                _history(db, key, local, h["action"], h["created_at"], h["actor"],
                         h["channel"], before)
        for it in items:  # conflictos, ya con los números locales y en las dos lecciones
            a = mapping[it["number"]]
            for c in it.get("conflicts") or []:
                b = mapping.get(c)
                if b is None or b == a or not ({a, b} & fresh):
                    continue
                for x, y in ((a, b), (b, a)):
                    row = _get(db, key, x)
                    db.execute("UPDATE lesson SET conflicts = ? WHERE project_key = ? AND"
                               " number = ?", (json.dumps(sorted(
                                   set(json.loads(row["conflicts"])) | {y})), key, x))
        db.execute("COMMIT")
    except (sqlite3.IntegrityError, KeyError, TypeError, AttributeError) as e:
        db.execute("ROLLBACK")
        raise LessonError(f"el archivo trae datos inválidos ({e!r})") from e
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return {"created": created, "merged": merged, "origins_added": added}


# ---------- cosecha ----------
def _describe(f: dict) -> str:
    where = f" ({f['file']}:{f.get('line')})" if f.get("file") else ""
    return f"[{f.get('severity', 'high')}] {f.get('message', '')}{where}"


def _source(row) -> dict | None:
    p = json.loads(row["payload"] or "{}")
    kind, stage, messages, files = None, p.get("stage"), [], list(p.get("files") or [])
    if row["type"] == "stage.rework" and stage == "review":
        kind, messages = "review_rejected", [m for m in p.get("feedback") or [] if m]
    elif row["type"] in ("run.blocked", "run.failed") and p.get("code") not in TRANSIENT:
        kind = "run_stopped"
        found = (p.get("details") or {}).get("findings") or []
        messages = [_describe(f) for f in found] if p.get("code") == "findings" and found \
            else [p.get("reason") or ""]
    elif row["type"] == "human.fixed":
        kind, stage, messages = "human_correction", stage or "build", [p.get("message") or ""]
    elif row["type"] == "run.rejected" and (p.get("reason") or "").strip():
        kind, stage, messages = "human_correction", stage or "ship", [p["reason"]]
    messages = [m for m in messages if _clean(m)]
    if not kind or not messages:
        return None
    files += [m.group(1) for msg in messages for m in _LOCATION.finditer(msg)]
    return {"kind": kind, "task": row["number"], "run_id": row["run_id"], "stage": stage,
            "event_id": row["id"], "created_at": row["created_at"], "messages": messages,
            "detail": "; ".join(messages), "files": list(dict.fromkeys(files))}


def sources(conn: sqlite3.Connection, run_ids: list[str] | None = None,
            seen: set[tuple[str, int]] = frozenset()) -> dict[str, list[dict]]:
    """Los tropiezos aún sin cosechar, agrupados por ejecución (en orden de eventos)."""
    marks = ",".join("?" * len(SOURCES))
    sql = (f"SELECT e.id, e.run_id, e.type, e.payload, e.created_at, t.number FROM event e"
           f" JOIN run r ON r.id = e.run_id JOIN task t ON t.id = r.task_id"
           f" WHERE e.type IN ({marks})")
    args: list = list(SOURCES)
    if run_ids is not None:
        sql += f" AND e.run_id IN ({','.join('?' * len(run_ids))})"
        args += list(run_ids)
    out: dict[str, list[dict]] = {}
    for row in conn.execute(sql + " ORDER BY e.id", args):
        if (row["run_id"], row["id"]) in seen:
            continue
        if src := _source(row):
            out.setdefault(row["run_id"], []).append(src)
    return out


def _roots(engine) -> list[Path]:
    if engine.space:
        members = proj.members(*engine.space)
        if members:
            return sorted(members.values())
    return [engine.root]


def key_for(engine) -> str | None:
    """La clave vigente del proyecto del engine; None si `lessons.db` no se puede abrir."""
    try:
        db = open_db()
    except (sqlite3.Error, OSError):
        return None
    try:
        return resolve(db, migrate(db, _roots(engine)))
    finally:
        db.close()


def _files(conn: sqlite3.Connection, run_id: str) -> list[str]:
    return [f"{r['repo']}/{r['path']}" if r["repo"] else r["path"] for r in conn.execute(
        "SELECT repo, path FROM run_file WHERE run_id = ? ORDER BY repo, path", (run_id,))]


def _origin(src: dict) -> dict:
    return {k: src[k] for k in ("kind", "task", "run_id", "stage", "detail", "event_id",
                                "created_at")}


def _in_zone(zone: list[str], files: list[str]) -> bool:
    return not zone or not files or any(fnmatch.fnmatch(f, g) for g in zone for f in files)


def _finding(message: str) -> Finding:
    sev = _SEVERITY.match(message)
    loc = _LOCATION.search(message)
    return Finding(severity=sev.group(1) if sev else "high", message=_clean(message),
                   file=loc.group(1) if loc else None, line=int(loc.group(2)) if loc else None)


def _written(engine, db, key: str, run_id: str, srcs: list[dict], files: list[str],
             writer: str) -> LessonDraft | None:
    """El borrador del redactor, ya validado por el motor; None si falla o no valida."""
    known: dict[int, sqlite3.Row] = {r["number"]: r for r in db.execute(
        "SELECT number, text, zone, status FROM lesson WHERE project_key = ?", (key,))}
    near = [r for r in known.values() if _in_zone(json.loads(r["zone"]), files)]
    notes = "# Lecciones existentes en esta zona\n" + ("\n".join(
        f"- L{r['number']} ({r['status']}): {r['text']}" for r in near) or "- ninguna")
    facts = [f"{s['kind']} en {s['stage']}: {s['detail']}" for s in srcs]
    if files:
        facts.append("Archivos implicados: " + ", ".join(files[:30]))
    run = engine.run_row(run_id)
    wt = Path(run["worktree"]) if run["worktree"] and Path(run["worktree"]).is_dir() \
        else engine.root
    try:
        attempt_id, result = engine.agent_attempt(
            run, "lesson", engine.profile(writer), wt, feedback=facts,
            previous=[_finding(m) for s in srcs if s["kind"] == "review_rejected"
                      for m in s["messages"]],
            output_model=LessonDraft, extra_notes=notes)
    except Exception:  # noqa: BLE001 — sin redactor queda el borrador determinista
        return None
    if not result.ok or not isinstance(result.output, LessonDraft):
        return None
    engine.finish_attempt(attempt_id, "done")
    return validate(result.output, set(known))


def harvest(engine, run_ids: list[str] | None = None) -> int:
    """Propone lecciones a partir de los tropiezos sin cosechar; devuelve cuántas son nuevas."""
    settings = cfg.lessons_settings(engine.space[1] if engine.space else engine.project)
    if not settings["enabled"]:
        return 0
    db = open_db()
    try:
        key = resolve(db, migrate(db, _roots(engine)))
        seen = {(r["run_id"], r["event_id"]) for r in db.execute(
            "SELECT run_id, event_id FROM lesson_origin WHERE project_key = ?", (key,))}
        created = 0
        for run_id, srcs in sources(engine.conn, run_ids, seen).items():
            op = f"lesson:{run_id}:{srcs[-1]['event_id']}"
            if engine.operation(op):
                continue
            files = list(dict.fromkeys(f for s in srcs for f in s["files"])) \
                or _files(engine.conn, run_id)
            written = _written(engine, db, key, run_id, srcs, files, settings["writer"]) \
                if settings["writer"] else None
            if written is not None and written.skip:
                drafts = []
            elif written is not None:
                drafts = [(written, [_origin(s) for s in srcs])]
            else:
                drafts = [(draft(s["messages"][0], s["files"] or files), [_origin(s)])
                          for s in srcs]
            new = [n for d, origins in drafts
                   if (n := record(db, key, d, origins, engine.home.name))]
            created += len(new)
            engine.record_operation(op, "lesson", "done", json.dumps(new))
            engine.event(run_id, "lessons.proposed", proposed=len(new),
                         lessons=[f"L{n}" for n in new])
        return created
    finally:
        db.close()
