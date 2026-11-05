"""Índice global de repos con umbra (`~/.umbra/projects.json`): lo alimentan `umbra init` y
`umbra new`; lo lee `umbra watch --all`."""

import json
from decimal import Decimal
from pathlib import Path

from umbra.unified import config as cfg
from umbra.unified import explain as ex
from umbra.unified import project
from umbra.unified.store import _unpriced, open_store

INDEX = "projects.json"


def _path() -> Path:
    return cfg.umbra_home() / INDEX


def load() -> list[dict]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in data if isinstance(p, dict) and p.get("root")]


def register(root: Path, stack: str) -> None:
    entries = [p for p in load() if Path(p["root"]) != root]
    entries.append({"root": root.as_posix(), "name": root.name, "stack": stack})
    try:
        _path().parent.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # el índice es una comodidad: no frena nada


def forget_missing() -> list[dict]:
    """Los repos que ya no existen salen del índice."""
    alive = [p for p in load() if (Path(p["root"]) / project.UMBRA_DIR / "project.toml").is_file()]
    if len(alive) != len(load()):
        _path().write_text(json.dumps(alive, ensure_ascii=False, indent=1), encoding="utf-8")
    return alive


def summary(root: Path) -> dict:
    """Qué pasa en un repo: cuántas tareas te necesitan, cuántas en marcha y el gasto."""
    conn = open_store(root / project.UMBRA_DIR)
    try:
        needs = conn.execute(
            "SELECT COUNT(*) FROM task t JOIN run r ON r.id = (SELECT id FROM run WHERE"
            " task_id = t.id ORDER BY created_at DESC LIMIT 1)"
            " WHERE r.status IN ('BLOCKED', 'FAILED', 'WAITING_APPROVAL')").fetchone()[0]
        needs += sum(1 for r in conn.execute("SELECT operation_key FROM operation WHERE"
                                             " operation_key LIKE 'spec:%:pr'")
                     if not conn.execute("SELECT 1 FROM operation WHERE operation_key = ?"
                                         " AND status = 'done'",
                                         (r[0][:-3] + ":merge",)).fetchone())
        working = conn.execute("SELECT COUNT(*) FROM run WHERE status IN ('QUEUED', 'RUNNING')"
                               ).fetchone()[0]
        total, tokens = Decimal(0), 0
        for u in conn.execute("SELECT cost, estimated, input_tokens, output_tokens FROM usage"):
            total += Decimal(u["cost"] or 0)
            tokens += _unpriced(u)
    finally:
        conn.close()
    return {"needs": needs, "working": working, "cost": ex.spend_text(total, tokens)}


def overview() -> list[dict]:
    out = []
    for p in forget_missing():
        try:
            out.append({**p, **summary(Path(p["root"]))})
        except Exception as e:  # ponytail: un repo roto no esconde a los demás
            out.append({**p, "needs": 0, "working": 0, "cost": f"error: {e}"[:40]})
    return out
