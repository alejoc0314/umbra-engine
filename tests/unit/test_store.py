import sqlite3

import pytest

from umbra.unified import store


@pytest.fixture
def conn(tmp_path):
    return store.open_store(tmp_path / ".umbra")


def add_task(conn, number):
    tid = store.new_id()
    conn.execute(
        "INSERT INTO task (id, number, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (tid, number, f"t{number}", store.now(), store.now()),
    )
    return tid


def add_run(conn, task_id, key):
    rid = store.new_id()
    conn.execute(
        "INSERT INTO run (id, task_id, routine, status, idempotency_key, created_at, updated_at)"
        " VALUES (?, ?, 'feature', 'QUEUED', ?, ?, ?)",
        (rid, task_id, key, store.now(), store.now()),
    )
    return rid


def test_migration_sets_version_and_is_reentrant(tmp_path):
    conn = store.open_store(tmp_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(store.MIGRATIONS)
    conn.close()
    store.open_store(tmp_path)  # reabrir no re-ejecuta la migración


@pytest.mark.parametrize("stmt", [
    "duplicate_task", "duplicate_run_key", "duplicate_attempt", "duplicate_operation",
    "duplicate_invocation", "self_dependency",
])
def test_unique_rules_reject_duplicates(conn, stmt):
    t1 = add_task(conn, 1)
    run = add_run(conn, t1, "k1")
    ops = {
        "duplicate_task": lambda: add_task(conn, 1),
        "duplicate_run_key": lambda: add_run(conn, t1, "k1"),
        "duplicate_attempt": lambda: [conn.execute(
            "INSERT INTO attempt (id, run_id, stage, attempt_no, status, started_at)"
            " VALUES (?, ?, 'build', 1, 'running', ?)", (store.new_id(), run, store.now()))
            for _ in range(2)],
        "duplicate_operation": lambda: [conn.execute(
            "INSERT INTO operation (operation_key, kind, status, updated_at)"
            " VALUES ('op', 'pr', 'done', ?)", (store.now(),)) for _ in range(2)],
        "duplicate_invocation": lambda: [conn.execute(
            "INSERT INTO usage (id, agent, invocation_id) VALUES (?, 'claude', 'inv')",
            (store.new_id(),)) for _ in range(2)],
        "self_dependency": lambda: conn.execute(
            "INSERT INTO dependency (task_id, depends_on_id) VALUES (?, ?)", (t1, t1)),
    }
    with pytest.raises(sqlite3.IntegrityError):
        ops[stmt]()


def test_status_summary_sums_cost_as_decimal(conn):
    t1 = add_task(conn, 1)
    add_run(conn, t1, "k1")
    for cost, est in (("0.1", 0), ("0.2", 1)):
        conn.execute(
            "INSERT INTO usage (id, agent, cost, estimated, invocation_id)"
            " VALUES (?, 'x', ?, ?, ?)",
            (store.new_id(), cost, est, store.new_id()),
        )
    summary = store.status_summary(conn)
    assert summary["spend"] == {"total": "0.3", "estimated": "0.2"}  # sin error de float
    assert summary["tasks"]["draft"] == 1
    assert summary["active_runs"][0]["task"] == 1


def test_to_cost_avoids_float_noise():
    assert store.to_cost(0.1) == "0.1"
