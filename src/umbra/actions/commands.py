"""Comandos registrados del proyecto (.umbra/project.toml [commands])."""

import hashlib
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from umbra.blocks.process import background_kwargs, kill_tree, run_bounded
from umbra.unified.store import new_id, now

TIMEOUT_S = 15 * 60


class UnknownCommand(Exception):
    pass


def registered(config: dict) -> dict[str, dict]:
    return config.get("commands", {})


def isolated(command: str, cwd: Path, blocks: dict) -> list[str] | str:
    """Con `[blocks] isolation = "docker"`, el comando corre en un contenedor efímero."""
    if blocks.get("isolation", "none") != "docker":
        return command
    return ["docker", "run", "--rm", "--network", blocks.get("network", "none"),
            "--cpus", str(blocks.get("cpus", 2)), "--memory", str(blocks.get("memory", "2g")),
            "--pids-limit", str(blocks.get("pids", 512)), "--security-opt", "no-new-privileges",
            "-v", f"{cwd.resolve()}:/work", "-w", "/work",
            blocks.get("image", "python:3.12-slim"), "sh", "-c", command]


class NotReady(Exception):
    pass


def background(config: dict, name: str = "dev") -> dict | None:
    """El comando de larga duración `name` (`background = true` y `url`), si está registrado."""
    spec = registered(config).get(name)
    return spec if spec and spec.get("background") and spec.get("url") else None


def start_background(config: dict, name: str, cwd: Path, udir: Path,
                     ready_timeout_s: float | None = None,
                     env: dict[str, str] | None = None) -> dict | None:
    """Arranca `name` (p. ej. el servidor de desarrollo) y espera a que su `url` responda.

    Devuelve `{proc, url, command, log}` o None si no hay tal comando; NotReady si no arranca."""
    spec = background(config, name)
    if not spec:
        return None
    log = udir / "artifacts" / f"{new_id()}-{name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    out = log.open("w", encoding="utf-8")
    cmd = isolated(spec["run"], cwd, config.get("blocks", {}))
    proc = subprocess.Popen(cmd, cwd=cwd, shell=isinstance(cmd, str), stdin=subprocess.DEVNULL,
                            stdout=out, stderr=subprocess.STDOUT,
                            env={**os.environ, **env} if env else None, **background_kwargs())
    url = spec["url"]
    deadline = time.monotonic() + (ready_timeout_s or spec.get("ready_timeout_s", 60))
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            out.close()
            raise NotReady(f"`{spec['run']}` terminó (exit {proc.returncode}) antes de responder"
                           f" en {url}; registro: {log.as_posix()}")
        try:
            urllib.request.urlopen(url, timeout=2).close()  # noqa: S310 (url del proyecto)
            break
        except (urllib.error.URLError, OSError, ValueError):
            pass
        except urllib.error.HTTPError:
            break  # responde (aunque sea 404): ya está arriba
        time.sleep(0.25)
    else:
        kill_tree(proc.pid)
        out.close()
        raise NotReady(f"`{spec['run']}` no respondió en {url} a tiempo; registro: "
                       f"{log.as_posix()}")
    return {"proc": proc, "url": url, "command": spec["run"], "log": log.as_posix(), "out": out}


def stop_background(dev: dict) -> None:
    kill_tree(dev["proc"].pid)
    try:
        dev["proc"].wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    dev["out"].close()


def run_registered(conn, config: dict, name: str, cwd: Path, udir: Path,
                   run_id: str | None = None, attempt_id: str | None = None,
                   tested_sha: str | None = None) -> dict:
    """Ejecuta el comando y guarda un artefacto con comando, exit code y salida."""
    spec = registered(config).get(name)
    if not spec:
        raise UnknownCommand(f"comando '{name}' no registrado en .umbra/project.toml")
    artifact_id = new_id()
    log = udir / "artifacts" / f"{artifact_id}-{name}.log"
    cmd = isolated(spec["run"], cwd, config.get("blocks", {}))
    result = run_bounded(cmd, cwd, spec.get("timeout_s", TIMEOUT_S), log_path=log)
    checksum = hashlib.sha256(log.read_bytes()).hexdigest()
    conn.execute(
        "INSERT INTO artifact (id, run_id, attempt_id, kind, path, checksum, tested_sha, command,"
        " exit_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (artifact_id, run_id, attempt_id, f"command:{name}", log.as_posix(), checksum,
         tested_sha, spec["run"], result.exit_code, now()),
    )
    return {"artifact_id": artifact_id, "command": spec["run"], "exit_code": result.exit_code,
            "timed_out": result.timed_out, "output": result.output, "log": log.as_posix()}
