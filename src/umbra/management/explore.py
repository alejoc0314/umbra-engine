"""Explorar (spec 035): el paquete de contexto de una tarea, sin modelo y con tope.

Reúne, solo para la zona que la tarea toca, los archivos relevantes, los tests que la cubren, la
historia de git, las tareas anteriores de umbra que la tocaron y las lecciones aprobadas. Lleva
referencias y hechos, no el contenido de los archivos: el agente los lee con sus herramientas."""

import re
import sqlite3
import subprocess
import time
from collections import Counter
from pathlib import Path, PurePosixPath

from umbra.contracts.envelope import TaskInfo
from umbra.unified import config as cfg
from umbra.unified.explain import RUN_STATES

GIT_BUDGET_S = 10.0  # para todas las llamadas a git de una exploración
GIT_TIMEOUT_S = 5.0  # por llamada
MAX_PER_IDENTIFIER = 15  # un identificador en más archivos no discrimina
MAX_IDENTIFIERS = 12
CO_CHANGE = 3  # archivos que más cambian junto a cada semilla
HISTORY = 8  # commits por zona
MAX_TASKS = 5
INVENTORY = "specs/000-linea-base/vistas.md"  # el de replica.py: inventario de vistas
ORDER = ("files", "tests", "lessons", "history", "tasks")  # prioridad al recortar
HEADERS = {"files": "# Zona de la tarea",
           "tests": "# Tests que la cubren (comando: `test`)",
           "lessons": "# Lecciones aprobadas por la persona (respétalas)",
           "history": "# Historia reciente",
           "tasks": "# Tareas anteriores de umbra en esta zona"}
OMITTED = {"files": "archivos de la zona", "tests": "tests", "lessons": "lecciones",
           "history": "commits de historia", "tasks": "tareas anteriores"}
_TOKEN = re.compile(r"[\w./\\-]+")
_IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_-]{3,}\b")


class Budget:
    def __init__(self, seconds: float = GIT_BUDGET_S):
        self.deadline = time.monotonic() + seconds

    def left(self) -> float:
        return self.deadline - time.monotonic()


def _git(cwd: Path, budget: Budget, *args: str) -> str | None:
    """Salida de git, o None si falla, se pasa de tiempo o se agotó el presupuesto."""
    left = budget.left()
    if left <= 0:
        return None
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=min(left, GIT_TIMEOUT_S))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _tracked(p, budget: Budget) -> list[str]:
    return [f for f in (_git(p.wt, budget, "ls-files") or "").splitlines() if f]


def _text(task: TaskInfo) -> str:
    return "\n".join([task.title, task.description, *task.acceptance])


def _is_test(path: str) -> bool:
    name = PurePosixPath(path).name
    stem = name.split(".")[0]
    dirs = PurePosixPath(path).parts[:-1]
    return (stem.startswith("test_") or stem.endswith(("_test", "Test", "Tests"))
            or ".test." in name or ".spec." in name
            or any(d in ("tests", "test", "__tests__", "spec") for d in dirs))


def zone(parts, task: TaskInfo, inventory: str | None, budget: Budget | None = None) -> list[dict]:
    """Los archivos de la zona de la tarea, cada uno con su motivo (research §2)."""
    budget = budget or Budget()
    text = _text(task)
    tokens = [t.strip("./\\").replace("\\", "/") for t in _TOKEN.findall(text)]
    words = {w.lower() for t in tokens for w in re.split(r"[./_-]", t) if len(w) >= 4}
    idents = list(dict.fromkeys(
        i for i in _IDENT.findall(text)
        if "_" in i or "-" in i.strip("-") or re.search(r"[a-z][A-Z]", i)))[:MAX_IDENTIFIERS]
    out: list[dict] = []
    for p in parts:
        files = _tracked(p, budget)
        tracked = set(files)
        found: dict[str, str] = {}

        def add(path: str, why: str, found=found) -> None:
            found.setdefault(path, why)

        for s in task.scope:
            own = p.own(s.replace("\\", "/").strip("/"))
            if not own:
                continue
            for f in files:
                if f == own or f.startswith(own.rstrip("/") + "/"):
                    add(f, "en scope")
        for t in tokens:
            own = p.own(t) if "/" in t else t
            if own in tracked:
                add(own, "nombrado en la tarea")
            elif "." in t and "/" not in t:
                same = [f for f in files if PurePosixPath(f).name == t]
                for f in same if len(same) <= 3 else []:
                    add(f, "nombrado en la tarea")
        for line in (inventory or "").splitlines():
            if words & {w.lower() for w in re.findall(r"\w{4,}", line)}:
                for t in _TOKEN.findall(line):
                    own = p.own(t.strip("./`"))
                    if own in tracked:
                        add(own, "vista del inventario")
        for ident in idents:
            hits = (_git(p.wt, budget, "grep", "-l", "-w", "-F", "-e", ident) or "").split()
            for f in hits if len(hits) <= MAX_PER_IDENTIFIER else []:
                add(f, f"usa «{ident}»")
        for w in words:
            same = [f for f in files if PurePosixPath(f).stem.lower() == w]
            for f in same if len(same) <= 3 else []:
                add(f, f"se llama como «{w}»")
        for seed in list(found):
            log = _git(p.wt, budget, "log", "-n", "100", "--full-diff", "--format=",
                       "--name-only", "--", seed)
            counts = Counter(f for f in (log or "").splitlines()
                             if f and f != seed and f in tracked and f not in found)
            together = [(f, n) for f, n in counts.items() if n >= 2]  # 1 vez es casualidad
            for f, _n in sorted(together, key=lambda kv: (-kv[1], kv[0]))[:CO_CHANGE]:
                add(f, f"cambia junto a {PurePosixPath(seed).name}")
        out += [{"path": p.show(f), "repo": p.repo, "why": why} for f, why in found.items()]
    return out


def _by_part(parts, files: list[dict]):
    """(parte, rutas dentro de su repo) de las partes que tienen archivos de la zona."""
    for p in parts:
        own = [o for f in files if f.get("repo", "") == p.repo and (o := p.own(f["path"]))]
        if own:
            yield p, own


def tests_for(parts, files: list[dict], budget: Budget | None = None) -> list[dict]:
    """Los tests que cubren la zona: por convención de nombres y por `git grep` del módulo."""
    budget = budget or Budget()
    out: dict[str, dict] = {}
    for p, own in _by_part(parts, files):
        tests = [f for f in _tracked(p, budget) if _is_test(f)]
        for path in own:
            if _is_test(path):
                continue
            pure = PurePosixPath(path)
            stem, ext = pure.name.split(".")[0], pure.suffix
            names = {f"test_{stem}{ext}", f"{stem}_test{ext}", f"{stem}Test{ext}",
                     f"{stem}Tests{ext}"}
            hits = [t for t in tests
                    if PurePosixPath(t).name in names
                    or PurePosixPath(t).name.startswith((f"{stem}.test.", f"{stem}.spec."))]
            if len(stem) >= 3 and tests:
                grep = _git(p.wt, budget, "grep", "-l", "-w", "-F", "-e", stem, "--", *tests)
                hits += [t for t in (grep or "").split() if t != path]
            for t in hits:
                out.setdefault(p.show(t), {"path": p.show(t), "covers": p.show(path),
                                           "command": "test"})
    return list(out.values())


def history(parts, files: list[dict], budget: Budget | None = None) -> list[dict]:
    """Los commits recientes de la zona (hasta 8 por repo), con sus archivos de la zona."""
    budget = budget or Budget()
    out = []
    for p, own in _by_part(parts, files):
        log = _git(p.wt, budget, "log", f"-n{HISTORY}", "--abbrev=7", "--date=short",
                   "--format=%x1e%h%x09%ad%x09%s", "--name-only", "--", *own) or ""
        for chunk in log.split("\x1e")[1:]:
            head, *names = chunk.strip("\n").split("\n")
            sha, date, subject = (head.split("\t", 2) + ["", ""])[:3]
            out.append({"sha": sha, "date": date, "subject": subject,
                        "paths": [p.show(n) for n in names if n]})
    return out


def _backfill(conn: sqlite3.Connection, parts, budget: Budget) -> None:
    """Las ejecuciones de antes de `run_file`: sus archivos desde git, si los SHA existen."""
    if len(parts) != 1 or parts[0].repo:
        return
    rows = conn.execute(
        "SELECT r.id, r.base_sha, r.head_sha FROM run r WHERE r.base_sha IS NOT NULL"
        " AND r.head_sha IS NOT NULL AND r.head_sha != r.base_sha"
        " AND NOT EXISTS (SELECT 1 FROM run_file f WHERE f.run_id = r.id)"
        " AND NOT EXISTS (SELECT 1 FROM run_part rp WHERE rp.run_id = r.id)").fetchall()
    for r in rows:
        names = _git(parts[0].wt, budget, "diff", "--name-only", r["base_sha"], r["head_sha"])
        conn.executemany("INSERT OR IGNORE INTO run_file (run_id, repo, path) VALUES (?, '', ?)",
                         [(r["id"], n) for n in (names or "").splitlines() if n])


def previous_tasks(conn: sqlite3.Connection | None, parts, files: list[dict],
                   exclude: str | None = None, budget: Budget | None = None) -> list[dict]:
    """Las tareas de umbra que tocaron la zona (las 5 más recientes), con cómo terminaron y los
    hallazgos bloqueantes de Revisar."""
    if conn is None or not files:
        return []
    _backfill(conn, parts, budget or Budget())
    wanted = set()
    for f in files:
        repo = f.get("repo", "")
        path = f["path"][len(repo) + 1:] if repo and f["path"].startswith(repo + "/") \
            else f["path"]
        wanted.add((repo, path))
    seen: dict[str, sqlite3.Row] = {}
    for r in conn.execute(
            "SELECT f.repo, f.path, r.id, r.status, r.updated_at, t.number, t.title"
            " FROM run_file f JOIN run r ON r.id = f.run_id JOIN task t ON t.id = r.task_id"
            " WHERE r.id != ?", (exclude or "",)):
        if (r["repo"], r["path"]) in wanted:
            seen.setdefault(r["id"], r)
    out = []
    for r in sorted(seen.values(), key=lambda r: r["updated_at"], reverse=True)[:MAX_TASKS]:
        findings = [m for (m,) in conn.execute(
            "SELECT f.message FROM finding f JOIN attempt a ON a.id = f.attempt_id"
            " WHERE a.run_id = ? AND a.stage = 'review' AND f.severity IN ('high', 'critical')"
            " ORDER BY a.started_at", (r["id"],))]
        out.append({"number": r["number"], "title": r["title"], "outcome": r["status"],
                    "findings": findings})
    return out


def _line(kind: str, item: dict) -> str:
    if kind == "files":
        return f"- {item['path']} — {item['why']}"
    if kind == "tests":
        return f"- {item['path']} — cubre {item['covers']}"
    if kind == "lessons":
        return f"- L{item['id']}: {item['text']}"
    if kind == "history":
        names = ", ".join(PurePosixPath(n).name for n in item["paths"])
        return f"- {item['sha']} {item['date']} «{item['subject'][:100]}» ({names})"
    outcome = RUN_STATES.get(item["outcome"], item["outcome"]).lower()
    asked = "; ".join(f"«{f[:160]}»" for f in item["findings"][:3])
    return (f"- #{item['number']} «{item['title']}» — {outcome}"
            + (f"; Revisar pidió: {asked}" if asked else ""))


def _render(kept: dict[str, list[str]], omitted: dict[str, int], notes: list[str]) -> str:
    blocks = [HEADERS[k] + "\n" + "\n".join(kept[k]) for k in ORDER if kept[k]]
    if notes:
        blocks.append("# Notas\n" + "\n".join(f"- {n}" for n in notes))
    if any(omitted.values()):
        blocks.append("# Omitido por tope\n" + "\n".join(
            f"- {n} {OMITTED[k]}" for k, n in omitted.items() if n))
    return "\n".join(blocks) + "\n" if blocks else ""


def build_package(files: list[dict], tests: list[dict], lessons: list[dict],
                  hist: list[dict], tasks: list[dict], max_chars: int,
                  notes: list[str] | None = None) -> tuple[str, dict]:
    """El paquete en markdown y su resumen. Llena por bloques en orden de prioridad (zona,
    tests, lecciones, historia, tareas), recorta por líneas completas y nunca pasa del tope."""
    notes = list(notes or [])
    items = {"files": files, "tests": tests, "lessons": lessons, "history": hist,
             "tasks": tasks}
    kept: dict[str, list[str]] = {k: [] for k in ORDER}
    included: dict[str, list[dict]] = {k: [] for k in ORDER}
    omitted = {k: len(items[k]) for k in ORDER}
    for kind in ORDER:
        for item in items[kind]:
            kept[kind].append(_line(kind, item))
            omitted[kind] -= 1
            if len(_render(kept, omitted, notes)) > max_chars:
                kept[kind].pop()
                omitted[kind] += 1
                break
            included[kind].append(item)
    md = _render(kept, omitted, notes)
    if len(md) > max_chars:  # tope minúsculo: ni las notas caben enteras
        md = md[:max_chars].rsplit("\n", 1)[0] + "\n" if "\n" in md[:max_chars] else ""
    summary = {"chars": len(md), "max_chars": max_chars, **included,
               "omitted": [{"kind": k, "count": n, "why": "tope"}
                           for k, n in omitted.items() if n],
               "notes": notes}
    return md, summary


def _approved_lessons(key: str | None, files: list[str], config: dict,
                      notes: list[str]) -> list[dict]:
    """Las lecciones aprobadas que aplican a la zona; si `lessons.db` falla, ninguna."""
    from umbra.management import lessons as lessons_db
    if not key or not cfg.lessons_settings(config)["enabled"]:
        return []
    try:
        db = lessons_db.open_db()
        try:
            return lessons_db.applicable(db, key, files)
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001 — las lecciones ayudan, pero nunca bloquean
        notes.append(f"no se pudieron leer las lecciones: {e or type(e).__name__}")
        return []


def explore(conn: sqlite3.Connection | None, parts, task: TaskInfo, config: dict,
            run_id: str | None = None, lesson_key: str | None = None) -> tuple[str, dict]:
    """La exploración completa de una tarea: zona, tests, historia, tareas anteriores y
    lecciones, armadas en un paquete con el tope de `[context] max_chars`."""
    budget = Budget()
    inventory = "\n".join(
        (p.wt / INVENTORY).read_text(encoding="utf-8", errors="replace")
        for p in parts if (p.wt / INVENTORY).is_file())
    files = zone(parts, task, inventory or None, budget)
    tests = tests_for(parts, files, budget)
    hist = history(parts, files, budget)
    tasks = previous_tasks(conn, parts, files, run_id, budget)
    notes = []
    lessons = _approved_lessons(lesson_key, [f["path"] for f in files], config, notes)
    if not any(_git(p.wt, budget, "rev-parse", "--verify", "--quiet", "HEAD") for p in parts):
        notes.append("sin historia de git: el repo no tiene commits")
    elif not hist:
        notes.append("sin historia de git para la zona")
    if not files:
        notes.append("no se dedujeron archivos de la tarea: explora el repo por tu cuenta")
    if not tests:
        notes.append("sin tests detectados para la zona")
    if budget.left() <= 0:
        notes.append("se agotó el tiempo de exploración: el paquete puede estar incompleto")
    return build_package(files, tests, lessons, hist, tasks, cfg.context_limit(config), notes)
