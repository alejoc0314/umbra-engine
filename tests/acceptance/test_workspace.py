"""Espacios de trabajo: una carpeta padre con varios repos (spec 032)."""

import json
import os
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.acceptance.conftest import Env, install_fake
from tests.acceptance.test_watch_actions import sync_worker
from tests.conftest import git
from umbra import service
from umbra.management import projects
from umbra.unified import project
from umbra.unified.store import new_id, now, open_store

CALC = "def add(a, b):\n    return 0\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
SPEC = """# Pagos

### User Story 1 - Endpoint (Priority: P1)

**Repo**: api

Que add sume en el back. FR-001

**Acceptance Scenarios**:

1. **Given** a, **When** b, **Then** add(2, 3) == 5

### User Story 2 - Pantalla (Priority: P2)

**Repo**: web

Que add sume en el front. FR-002

**Acceptance Scenarios**:

1. **Given** c, **When** d, **Then** add(2, 3) == 5
"""


def make_repo(tmp_path, name):
    repo = tmp_path / "ws" / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@umbra.local")
    git(repo, "config", "user.name", "umbra test")
    (repo / "calc.py").write_text(CALC)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text(TEST)
    (repo / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["."]\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    remote = tmp_path / "remotes" / f"{name}.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    return repo


def tune_repo(repo):
    cfg = repo / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace(
        'test = { run = "pytest -q", safe = true }',
        f"test = {{ run = '\"{sys.executable}\" -m pytest -q -p no:cacheprovider', safe = true }}"
    ).replace("[project]\n", '[project]\ndefault_routine = "quick"\n'))


@pytest.fixture
def ws(tmp_path, monkeypatch):
    for name in ("api", "web"):
        make_repo(tmp_path, name)
    root = tmp_path / "ws"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for fake in ("claude", "gh", "codex"):
        install_fake(bin_dir, fake)
    state = tmp_path / "state"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_STATE_DIR", str(state))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("UMBRA_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(root)
    monkeypatch.setattr(service, "interactive", lambda: True)
    env = Env(root, state, CliRunner(), monkeypatch)
    env.umbra("init", "-y")
    for name in ("api", "web"):
        tune_repo(root / name)
    cfg = root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace("summary = true", "summary = false")
                   .replace("desktop = true", "desktop = false")
                   .replace("parallel = 2", "parallel = 1"))
    return env


def spec(env, text=SPEC):
    d = env.root / "specs" / "001-pagos"
    d.mkdir(parents=True)
    (d / "spec.md").write_text(text, encoding="utf-8")
    return d


def remote_file(env, repo, branch, path):
    git(env.root / repo, "fetch", "-q", "origin", branch)
    return git(env.root / repo, "show", f"origin/{branch}:{path}").stdout


# ---------- crear el espacio ----------
def test_init_creates_the_workspace_and_each_repo(ws):
    config = project.load_project(ws.root)
    assert project.repo_names(config) == ["api", "web"]
    for name in ("api", "web"):
        assert project.load_project(ws.root / name)["project"]["stack"] == "python"
    # desde dentro de un repo se trabaja con el espacio completo
    assert service.load(ws.root / "web").root == ws.root.resolve()
    assert service.load(ws.root / "api" / "tests").root == ws.root.resolve()
    # en el índice de proyectos, el espacio una vez y sus repos no aparecen sueltos
    assert [p["name"] for p in projects.load()] == ["ws"]
    again = ws.umbra("init").output
    assert "ya existía" in again


def test_code_workspace_sets_the_order(tmp_path):
    for name in ("api", "web"):
        make_repo(tmp_path, name)
    (tmp_path / "ws" / "x.code-workspace").write_text(
        '{\n  // front primero\n  "folders": [{"path": "web"}, {"path": "./api"},],\n}\n')
    assert project.child_repos(tmp_path / "ws") == ["web", "api"]


def test_one_repo_is_not_a_workspace(tmp_path, monkeypatch):
    make_repo(tmp_path, "api")
    with pytest.raises(project.NotARepo, match="dentro de api"):
        project.init_project(tmp_path / "ws")


def test_a_repo_with_running_tasks_is_not_joined(tmp_path):
    for name in ("api", "web"):
        make_repo(tmp_path, name)
    api = tmp_path / "ws" / "api"
    project.init_project(api)
    conn = open_store(api / ".umbra")
    task = new_id()
    conn.execute("INSERT INTO task (id, number, title, status, created_at, updated_at)"
                 " VALUES (?, 1, 't', 'accepted', ?, ?)", (task, now(), now()))
    conn.execute("INSERT INTO run (id, task_id, routine, status, idempotency_key, created_at,"
                 " updated_at) VALUES (?, ?, 'quick', 'RUNNING', 'k', ?, ?)",
                 (new_id(), task, now(), now()))
    conn.close()
    with pytest.raises(project.NotInitialized, match="api tiene tareas en marcha"):
        project.init_project(tmp_path / "ws")
    assert not (tmp_path / "ws" / ".umbra").exists()


# ---------- una spec que reparte historias ----------
def test_stories_say_their_repo_and_chain_across_repos(ws):
    spec(ws)
    ws.umbra("spec", "tasks", "specs/001-pagos")
    tasks = ws.conn.execute("SELECT number, repos FROM task ORDER BY number").fetchall()
    assert [(t["number"], json.loads(t["repos"])) for t in tasks] == [(1, ["api"]), (2, ["web"])]
    deps = ws.conn.execute("SELECT COUNT(*) FROM dependency").fetchone()[0]
    assert deps == 1  # la del front espera a la del back
    rows = json.loads(ws.umbra("task", "list", "--json").output)
    assert [r["title"] for r in rows] == ["api · Historia 1: Endpoint",
                                          "web · Historia 2: Pantalla"]


def test_a_story_without_a_valid_repo_creates_nothing(ws):
    spec(ws, SPEC.replace("**Repo**: web", "**Repo**: movil"))
    result = ws.umbra("spec", "tasks", "specs/001-pagos", ok=False)
    assert "historia 2" in result.output and "movil" in result.output
    assert "api, web" in result.output
    assert ws.conn.execute("SELECT COUNT(*) FROM task").fetchone()[0] == 0


def test_the_spec_conversation_knows_the_repos(ws):
    from umbra.chat import elicit
    text = elicit.phase_message("specify", "pagos", root=ws.root)
    assert "api (python), web (python)" in text and "**Repo**" in text


def test_a_manual_task_needs_its_repo(ws):
    result = ws.umbra("task", "add", "Algo", ok=False)
    assert "no dice en qué repo" in result.output
    ws.umbra("task", "add", "Algo", "--repo", "web", "--draft")
    assert ws.umbra("task", "repo", "1", "api").exit_code == 0
    assert json.loads(ws.conn.execute("SELECT repos FROM task").fetchone()[0]) == ["api"]


# ---------- ejecutar e integrar ----------
def run_spec(ws):
    spec(ws)
    ws.umbra("spec", "tasks", "specs/001-pagos")
    sync_worker(ws)
    ws.mode("ok")
    return ws.umbra("night", "--spec", "specs/001-pagos").output


def test_each_task_works_in_its_repo_and_the_spec_opens_one_pr_per_repo(ws):
    run_spec(ws)
    assert ws.run(1)["status"] == ws.run(2)["status"] == "SUCCEEDED"
    # cada tarea, en un worktree de su repo; la rama de la spec existe en los dos
    assert "return a + b" in remote_file(ws, "api", "spec/001-pagos", "calc.py")
    assert "return a + b" in remote_file(ws, "web", "spec/001-pagos", "calc.py")
    # la spec viaja versionada en cada repo
    assert "Pagos" in remote_file(ws, "web", "spec/001-pagos", "specs/001-pagos/spec.md")
    prs = [p for p in ws.prs() if p["base"] == "main"]
    assert [(Path(p["repo"]).name, p["head"]) for p in prs] == [
        ("api.git", "spec/001-pagos"), ("web.git", "spec/001-pagos")]
    ctx = service.load(ws.root)
    pr = service.spec_pr(ctx, "specs/001-pagos")
    assert pr["state"] == "waiting" and [p["repo"] for p in pr["repos"]] == ["api", "web"]

    out = ws.umbra("approve", "--spec", "001-pagos", input="y\n").output
    assert "spec integrada" in out
    for name in ("api", "web"):
        assert "return a + b" in remote_file(ws, name, "main", "calc.py")
        # la copia local de la base de cada repo, al día
        assert "return a + b" in (ws.root / name / "calc.py").read_text()
    assert service.spec_pr(ctx, "specs/001-pagos")["state"] == "merged"


def test_a_failed_merge_halfway_resumes_with_what_is_missing(ws):
    run_spec(ws)
    web = ws.root / "web"
    # alguien cambia calc.py en el main del front: el PR de la spec choca
    git(web, "checkout", "-q", "-b", "otro", "origin/main")
    (web / "calc.py").write_text("def add(a, b):\n    return 1\n")
    git(web, "commit", "-qam", "otro cambio")
    git(web, "push", "-q", "origin", "otro:main")
    result = ws.umbra("approve", "--spec", "001-pagos", input="y\n", ok=False)
    assert "integrado en api; falta web" in result.output
    assert "return a + b" in remote_file(ws, "api", "main", "calc.py")
    # se deshace el choque en el main del front y se aprueba de nuevo: solo entra lo que faltaba
    (web / "calc.py").write_text(CALC)
    git(web, "commit", "-qam", "vuelta atrás")
    git(web, "push", "-q", "origin", "otro:main")
    git(web, "checkout", "-q", "main")
    api_main = git(ws.root / "api", "rev-parse", "origin/main").stdout
    ws.umbra("approve", "--spec", "001-pagos", input="y\n")
    assert git(ws.root / "api", "rev-parse", "origin/main").stdout == api_main
    assert "return a + b" in remote_file(ws, "web", "main", "calc.py")
    assert service.spec_pr(service.load(ws.root), "specs/001-pagos")["state"] == "merged"


def test_an_approved_task_outside_a_spec_merges_in_its_repo(ws):
    ws.umbra("task", "add", "Sumar en el front", "-a", "add(2, 3) == 5", "--repo", "web")
    ws.mode("ok")
    ws.umbra("run", "1", "--foreground")
    assert ws.run(1)["status"] == "WAITING_APPROVAL"
    assert ws.run(1)["worktree"].startswith((ws.root / ".umbra").as_posix())
    ws.umbra("approve", "1", input="y\n")
    assert "return a + b" in remote_file(ws, "web", "main", "calc.py")
    assert "return 0" in remote_file(ws, "api", "main", "calc.py")


def test_exec_in_a_workspace_asks_for_the_repo(ws):
    result = ws.umbra("exec", "test", ok=False)
    assert "--repo" in result.output and "api, web" in result.output
    ok = ws.umbra("exec", "test", "--repo", "api", ok=False)
    assert ok.exit_code == 1  # los tests de api corren (y fallan: add aún devuelve 0)
