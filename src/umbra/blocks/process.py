"""Ejecutar un proceso acotado: timeout, stdin, salida a archivo y kill del árbol.

La salida se vuelca al archivo de registro mientras el proceso corre (así `umbra watch` puede
mostrar al agente trabajando), y al terminar el archivo contiene exactamente lo mismo que
`ProcResult.output`.
"""

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

WINDOWS = sys.platform == "win32"


@dataclass
class ProcResult:
    exit_code: int
    timed_out: bool
    output: str
    idle: bool = False  # se cortó por inactividad (sin salida durante `idle_s`), no por el techo


def background_kwargs() -> dict:
    """Arranque en segundo plano: grupo de procesos propio y, en Windows, sin ventana.

    CREATE_NO_WINDOW da al proceso una consola oculta que heredan sus hijos (claude, codex,
    git, los tests): ninguno abre ventana. Con DETACHED_PROCESS, en cambio, el proceso no tiene
    consola y Windows le crea una visible a cada hijo de consola.
    """
    if WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW
                | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def resolve(exe: str) -> str:
    """Ruta real del ejecutable (en Windows resuelve .cmd/.exe del PATH)."""
    return shutil.which(exe) or exe


def _feed(proc: subprocess.Popen, text: str) -> None:
    try:
        proc.stdin.write(text)
        proc.stdin.close()
    except (OSError, ValueError):
        pass  # el proceso murió antes de leer: la salida lo contará


def run_bounded(cmd: list[str] | str, cwd: Path, timeout_s: float, log_path: Path | None = None,
                stdin: str | None = None, env: dict | None = None,
                idle_s: float | None = None, append: bool = False) -> ProcResult:
    """Lista = ejecutable + args (sin shell). String = comando registrado del proyecto (shell).

    `timeout_s` es el techo. Con `idle_s`, además, se corta si el proceso pasa ese tiempo sin
    escribir nada: un agente que avanza sigue; uno colgado muere antes."""
    kwargs = background_kwargs()  # grupo propio (para matar el árbol) y sin ventana
    shell = isinstance(cmd, str)
    if not shell:
        cmd = [resolve(cmd[0]), *cmd[1:]]
    proc = subprocess.Popen(
        cmd, cwd=cwd, shell=shell, env=env,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", **kwargs,
    )
    if stdin is not None:  # en un hilo: un prompt largo bloquearía si el hijo no lee aún
        threading.Thread(target=_feed, args=(proc, stdin), daemon=True).start()
    chunks: list[str] = []
    last = [time.monotonic()]  # última vez que el proceso escribió algo
    log = None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("a" if append else "w", encoding="utf-8")  # a: sesión retomada

    def pump() -> None:
        try:
            for line in proc.stdout:
                last[0] = time.monotonic()
                chunks.append(line)
                if log:
                    log.write(line)
                    log.flush()
        except ValueError:
            pass  # el pipe se cerró al matar el árbol

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    timed_out = idle = False
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            proc.wait(timeout=min(1.0, max(0.05, deadline - time.monotonic())))
            break
        except subprocess.TimeoutExpired:
            now = time.monotonic()
            idle = bool(idle_s) and now - last[0] >= idle_s
            if now >= deadline or idle:
                timed_out = True
                kill_tree(proc.pid)
                proc.wait()
                break
    reader.join(timeout=5)
    if log:
        log.close()
    out = "".join(chunks)
    return ProcResult(proc.returncode if not timed_out else -1, timed_out, out,
                      idle and timed_out)


def kill_tree(pid: int) -> None:
    if WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass


def wait_for_file(path: Path, timeout_s: float = 5) -> bool:
    """Espera a que exista (útil en pruebas de registros en vivo)."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if path.exists():
            return True
        time.sleep(0.05)
    return False
