import json
import os
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import git
from umbra import service
from umbra.cli.main import app
from umbra.unified import project
from umbra.unified.store import open_store

FAKES = Path(__file__).resolve().parent.parent / "fakes"


def install_fake(bin_dir: Path, name: str) -> None:
    script = FAKES / f"{name}.py"
    if sys.platform == "win32":
        (bin_dir / f"{name}.cmd").write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        path = bin_dir / name
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        path.chmod(0o755)


@dataclass
class Env:
    root: Path
    state: Path
    runner: CliRunner
    monkeypatch: pytest.MonkeyPatch

    def umbra(self, *args, input=None, ok=True):
        result = self.runner.invoke(app, list(args), input=input, catch_exceptions=False)
        if ok:
            assert result.exit_code == 0, result.output
        return result

    def mode(self, *modes):
        self.monkeypatch.setenv("FAKE_CLAUDE_MODE", ",".join(modes))

    @property
    def conn(self):
        return open_store(self.root / ".umbra")

    def run(self, number=1):
        return self.conn.execute(
            "SELECT r.* FROM run r JOIN task t ON t.id = r.task_id WHERE t.number = ?"
            " ORDER BY r.created_at DESC LIMIT 1", (number,)).fetchone()

    def prs(self):
        f = self.state / "gh.json"
        return json.loads(f.read_text())["prs"] if f.exists() else []

    def claude_calls(self):
        f = self.state / "claude_calls.json"
        return json.loads(f.read_text()) if f.exists() else []

    def codex_calls(self):
        f = self.state / "codex_calls.json"
        return json.loads(f.read_text()) if f.exists() else []

    def codex_mode(self, *modes):
        self.monkeypatch.setenv("FAKE_CODEX_MODE", ",".join(modes))

    def attempts(self, number=1):
        return [tuple(r) for r in self.conn.execute(
            "SELECT stage, status FROM attempt WHERE run_id = ? ORDER BY started_at",
            (self.run(number)["id"],))]

    def plain_routine(self):
        """La rutina `feature` sin escalada ni árbitro (spec 016), como rutina del proyecto:
        para las pruebas cuyo sentido es que los hallazgos o los tests detengan la tarea."""
        routines = self.root / ".umbra" / "routines"
        routines.mkdir(exist_ok=True)
        lines = ["name: feature", "stages:", "  - name: plan", "    profile: planner",
                 "  - name: build", "    profile: builder-tdd", "    max_fix_cycles: 2",
                 "  - name: review", "    profile: reviewer-strict", "    block_on: high",
                 "    max_fix_cycles: 2", "  - name: verify", "    profile: verifier",
                 "    block_on: high", "    max_fix_cycles: 2", "  - name: scan",
                 "    block_on: high", "    max_fix_cycles: 2", "  - name: ship",
                 "    human_approval: true"]
        (routines / "feature.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch, git_repo):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    root = git_repo
    (root / "calc.py").write_text("def add(a, b):\n    return 0\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["."]\n')
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-q", "origin", "main")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    install_fake(bin_dir, "claude")
    install_fake(bin_dir, "gh")
    install_fake(bin_dir, "codex")
    state = tmp_path / "state"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_STATE_DIR", str(state))
    # el agente falso reescribe calc.py con el mismo tamaño en el mismo segundo: sin .pyc obsoletos
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("UMBRA_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(root)
    monkeypatch.setattr(service, "interactive", lambda: True)

    project.init_project(root)
    cfg = root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace(
        'test = { run = "pytest -q", safe = true }',
        f"test = {{ run = '\"{sys.executable}\" -m pytest -q -p no:cacheprovider', safe = true }}"
    ).replace("[project]\n", '[project]\ndefault_routine = "quick"\n')
     .replace("summary = true", "summary = false")  # el resumen se prueba aparte
     .replace("desktop = true", "desktop = false")  # nunca avisos reales desde los tests
     .replace("[autopilot]\nenabled = true", "[autopilot]\nenabled = false")
     .replace("parallel = 2", "parallel = 1"))  # una a la vez, salvo que la prueba pida más
    return Env(root, state, CliRunner(), monkeypatch)


# ---------- Telegram falso (specs 019 y 022) ----------
CHAT = 42


class FakeTelegram:
    """Servidor HTTP local que hace de api.telegram.org: guarda lo enviado y entrega lo que la
    prueba «escribe» desde el teléfono."""

    def __init__(self):
        self.sent, self.queue, self.calls, self.uploads = [], [], [], []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                method = self.path.rsplit("/", 1)[-1]
                if self.headers.get("Content-Type", "").startswith("multipart/"):
                    # fotos y documentos: solo cuentan los archivos adjuntos
                    body = {"files": raw.count(b'filename="'),
                            "names": [n.decode() for n in
                                      __import__("re").findall(rb'filename="([^"]+)"', raw)]}
                    fake.calls.append((method, body))
                    fake.uploads.append((method, body))
                    result = [] if method == "sendMediaGroup" else {"message_id": 0}
                    out = json.dumps({"ok": True, "result": result}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(out)))
                    self.end_headers()
                    self.wfile.write(out)
                    return
                body = json.loads(raw)
                fake.calls.append((method, body))
                if method == "sendMessage":
                    fake.sent.append(body)
                    result = {"message_id": len(fake.sent)}
                elif method == "getUpdates":
                    result, fake.queue = [u for u in fake.queue
                                          if u["update_id"] >= body.get("offset", 0)], []
                else:
                    result = True
                out = json.dumps({"ok": True, "result": result}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.next_id = 1

    def push(self, **update):
        self.queue.append({"update_id": self.next_id, **update})
        self.next_id += 1

    def tap(self, data, chat=CHAT, user="alejandro"):
        self.push(callback_query={"id": f"cb{self.next_id}", "from": {"username": user},
                                  "message": {"message_id": len(self.sent),
                                              "chat": {"id": chat}}, "data": data})

    def say(self, text, chat=CHAT, reply_to=None):
        msg = {"chat": {"id": chat}, "from": {"username": "alejandro"}, "text": text}
        if reply_to:
            msg["reply_to_message"] = {"text": reply_to}
        self.push(message=msg)

    def buttons(self, i=-1):
        return [(b["text"], b["callback_data"])
                for row in self.sent[i].get("reply_markup", {}).get("inline_keyboard", [])
                for b in row]


@pytest.fixture
def tg(env):
    from umbra.routines import bridge
    fake = FakeTelegram()
    env.monkeypatch.setenv("UMBRA_TELEGRAM_API", fake.url)
    env.monkeypatch.setenv("UMBRA_TELEGRAM_TOKEN", "t0k")
    home = Path(os.environ["UMBRA_HOME"])  # un bot para todos los repos de la persona
    home.mkdir(parents=True, exist_ok=True)
    (home / "local.toml").write_text(
        f'[notify.telegram]\ntoken_env = "UMBRA_TELEGRAM_TOKEN"\nchat_id = {CHAT}\n')
    env.monkeypatch.setattr(bridge, "spawn", lambda root: None)  # sin proceso aparte
    yield fake
    fake.server.shutdown()
