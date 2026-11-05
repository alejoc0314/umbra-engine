"""Métricas del piloto calculadas solo con datos del almacén."""

from datetime import datetime
from decimal import Decimal

from umbra.unified.store import run_spend


def _seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def _first(conn, run_id: str, type_: str) -> str | None:
    row = conn.execute("SELECT created_at FROM event WHERE run_id = ? AND type = ?"
                       " ORDER BY id LIMIT 1", (run_id, type_)).fetchone()
    return row[0] if row else None


def _avg(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def compute(conn) -> dict:
    runs = []
    for r in conn.execute("SELECT r.id, r.status, t.number, t.title FROM run r"
                          " JOIN task t ON t.id = r.task_id ORDER BY r.created_at"):
        rid = r["id"]
        queued = _first(conn, rid, "run.queued")
        builds = conn.execute("SELECT COUNT(*) FROM attempt WHERE run_id = ? AND stage = 'build'"
                              " AND status != 'interrupted'", (rid,)).fetchone()[0]
        reworks = conn.execute("SELECT COUNT(*) FROM event WHERE run_id = ?"
                               " AND type = 'stage.rework'", (rid,)).fetchone()[0]
        cost, unpriced = run_spend(conn, rid)
        runs.append({
            "task": r["number"], "title": r["title"], "status": r["status"],
            "time_to_pr_s": _seconds(queued, _first(conn, rid, "pr.opened")),
            "time_to_merge_s": _seconds(queued, _first(conn, rid, "run.succeeded")),
            "fix_cycles": max(builds - 1, 0), "reworks": reworks, "cost": str(cost),
            "unpriced_tokens": unpriced,
            "first_pass": r["status"] == "SUCCEEDED" and builds <= 1 and reworks == 0,
        })
    merged = [r for r in runs if r["status"] == "SUCCEEDED"]
    total = sum((Decimal(r["cost"]) for r in runs), Decimal(0))
    return {
        "runs": runs,
        "summary": {
            "runs": len(runs), "merged": len(merged),
            "blocked": sum(r["status"] == "BLOCKED" for r in runs),
            "failed": sum(r["status"] == "FAILED" for r in runs),
            "avg_time_to_pr_s": _avg([r["time_to_pr_s"] for r in runs]),
            "avg_time_to_merge_s": _avg([r["time_to_merge_s"] for r in merged]),
            "avg_fix_cycles": _avg([r["fix_cycles"] for r in runs]),
            "first_pass_rate": round(sum(r["first_pass"] for r in merged) / len(merged), 2)
            if merged else None,
            "total_cost": str(total),
            "unpriced_tokens": sum(r["unpriced_tokens"] for r in runs),
            "cost_per_delivery": str((total / len(merged)).quantize(Decimal("0.0001")))
            if merged else None,
        },
    }
