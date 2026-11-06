"""Worker: un proceso por repo que ejecuta las ejecuciones pendientes y luego termina.

El proceso tiene el lease `worker` (un despachador por repo) y atiende hasta `[blocks] parallel`
ejecuciones a la vez, cada una en su hilo con su propia conexión y su propio worktree."""

import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from umbra.adapters import UnknownAgent
from umbra.blocks import lease
from umbra.blocks.process import background_kwargs
from umbra.routines.engine import LeaseLost, for_run
from umbra.unified import project as proj
from umbra.unified.agents import AgentNotVerified
from umbra.unified.events import add_event
from umbra.unified.store import now, open_store

LEASE = "worker"
HEARTBEAT_S = 20
POLL_S = 0.2


def owner_id() -> str:
    return f"{os.getpid()}@{socket.gethostname()}"


def parallel_limit(project: dict) -> int:
    return max(1, int(project.get("blocks", {}).get("parallel", 1)))


def pending_run(conn, busy: tuple[str, ...] = ()) -> str | None:
    marks = ",".join("?" * len(busy)) or "''"
    row = conn.execute("SELECT id FROM run WHERE status IN ('QUEUED', 'RUNNING')"
                       f" AND id NOT IN ({marks}) ORDER BY created_at LIMIT 1", busy).fetchone()
    return row["id"] if row else None


def run_one(root: Path, udir: Path, project: dict, token: int, run_id: str,
            lost: threading.Event) -> None:
    conn = open_store(udir)
    try:
        for_run(root, udir, conn, project, run_id,
                guard=lambda: lease.holds(conn, LEASE, token)).process(run_id)
    except LeaseLost:
        lost.set()
        return
    except Exception as e:  # un fallo de una ejecución no tumba el worker
        conn.execute("UPDATE run SET status = 'FAILED', updated_at = ? WHERE id = ?",
                     (now(), run_id))
        code = ("agent_not_verified" if isinstance(e, AgentNotVerified)
                else "agent_unknown" if isinstance(e, UnknownAgent) else "internal_error")
        add_event(conn, run_id, "run.failed", "worker", reason=str(e), code=code,
                  details={"error": str(e)}, trace=traceback.format_exc()[-2000:])
    try:  # piloto automático: arranca lo que quepa (sin lanzar otro worker: este sigue)
        from umbra import service
        service.autopilot(service.Ctx(root, udir, conn, project), "autopilot",
                          dispatch_worker=False)
    except Exception as e:
        add_event(conn, None, "autopilot.skipped", "worker", reason=str(e))
    finally:
        conn.close()


def work(root: Path) -> int:
    """Procesa ejecuciones hasta que no queden. Devuelve cuántas procesó."""
    udir = root / proj.UMBRA_DIR
    conn = open_store(udir)
    me = owner_id()
    token = lease.acquire(conn, LEASE, me)
    if token is None:
        return 0
    stop, lost = threading.Event(), threading.Event()

    def heartbeat():
        hb = open_store(udir)
        while not stop.wait(HEARTBEAT_S):
            if not lease.renew(hb, LEASE, token):
                return

    threading.Thread(target=heartbeat, daemon=True).start()
    project = proj.load_project(root)
    threads: dict[str, threading.Thread] = {}
    processed = 0
    try:
        while True:
            for run_id, t in list(threads.items()):
                if not t.is_alive():
                    threads.pop(run_id)
                    processed += 1
            if lost.is_set():
                return processed
            while len(threads) < parallel_limit(project) and \
                    (run_id := pending_run(conn, tuple(threads))):
                t = threading.Thread(target=run_one, args=(root, udir, project, token, run_id,
                                                           lost), daemon=True)
                threads[run_id] = t
                t.start()
            if not threads:
                break
            time.sleep(POLL_S)
    finally:
        stop.set()
        lease.release(conn, LEASE, token)
    return processed


def spawn(root: Path) -> None:
    """Lanza el worker desacoplado de la terminal (sobrevive a cerrarla)."""
    log = root / proj.UMBRA_DIR / "artifacts" / "worker.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as out:
        subprocess.Popen([sys.executable, "-m", "umbra.cli.main", "_worker", "--root", str(root)],
                         cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                         close_fds=True, **background_kwargs())
