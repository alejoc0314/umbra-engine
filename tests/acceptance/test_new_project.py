"""`umbra new`, playbooks y `watch --all` (spec 021)."""

import asyncio
import json
import sys
from pathlib import Path

from tests.conftest import git
from umbra.cli.projects_screen import ProjectsApp
from umbra.management import playbooks, projects
from umbra.unified.store import open_store

SCAFFOLD_PY = '''import pathlib
pathlib.Path("calc.py").write_text("def add(a, b):\\n    return 0\\n")
pathlib.Path("tests").mkdir()
pathlib.Path("tests/test_calc.py").write_text(
    "from calc import add\\n\\n\\ndef test_add():\\n    assert add(2, 3) == 5\\n")
pathlib.Path("pyproject.toml").write_text('[tool.pytest.ini_options]\\npythonpath = ["."]\\n')
'''


def team_playbook(env, name="python"):
    """Un playbook del equipo que pisa al de umbra: andamiaje sin red (un script de Python)."""
    d = playbooks.home() / name
    d.mkdir(parents=True)
    (d / "scaffold.py").write_text(SCAFFOLD_PY, encoding="utf-8")
    scaffold = f'"{sys.executable}" "{d / "scaffold.py"}"'
    (d / "playbook.toml").write_text(
        f'name = "{name}"\nscaffold = \'{scaffold}\'\ndefault_routine = "quick"\n\n'
        f"[commands]\ntest = '\"{sys.executable}\" -m pytest -q -p no:cacheprovider'\n\n"
        '[files]\n"ci.yml" = ".github/workflows/ci.yml"\n"AGENTS.md" = "AGENTS.md"\n',
        encoding="utf-8")
    (d / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (d / "AGENTS.md").write_text("# Reglas del equipo\n", encoding="utf-8")
    return d


def test_new_creates_a_repo_ready_for_its_first_task(env, tmp_path):
    team_playbook(env)
    env.mode("context", "ok")  # el cartógrafo y luego el constructor
    env.monkeypatch.chdir(tmp_path)
    out = env.umbra("new", "demo", "--stack", "python").output
    assert "proyecto creado" in out and "sin repo" not in out, out
    dest = tmp_path / "demo"
    assert (dest / ".github" / "workflows" / "ci.yml").read_text() == "name: ci\n"
    assert (dest / "AGENTS.md").exists() and (dest / "calc.py").exists()
    toml = (dest / ".umbra" / "project.toml").read_text()
    assert 'stack = "python"' in toml and 'default_routine = "quick"' in toml
    assert "pytest -q" in toml
    assert (dest / "CONTEXT.md").read_text().startswith("<!-- umbra:inicio -->")
    subjects = git(dest, "log", "--format=%s").stdout.strip().splitlines()
    assert subjects[-1] == "umbra: proyecto nuevo (python)" and len(subjects) == 2
    assert git(dest, "status", "--porcelain").stdout.strip() == ""
    assert git(dest, "remote", "get-url", "origin").stdout.strip().endswith("demo.git")
    assert any(p["name"] == "demo" for p in projects.load())
    # y la primera tarea llega a esperar aprobación, como en cualquier repo
    env.monkeypatch.chdir(dest)
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    status = open_store(dest / ".umbra").execute("SELECT status FROM run").fetchone()[0]
    assert status == "WAITING_APPROVAL"


def test_new_without_remote_or_context_and_refuses_existing_folder(env, tmp_path):
    team_playbook(env)
    env.monkeypatch.chdir(tmp_path)
    out = env.umbra("new", "local", "--stack", "python", "--no-remote", "--no-context",
                    "--json").output
    data = json.loads(out)
    assert data["remote"] is None and data["context"] is False
    assert not (tmp_path / "local" / "CONTEXT.md").exists()
    assert git(tmp_path / "local", "remote").stdout.strip() == ""
    assert len(env.claude_calls()) == 0
    again = env.umbra("new", "local", "--stack", "python", ok=False)
    assert "ya existe" in again.output
    unknown = env.umbra("new", "otro", "--stack", "cobol", ok=False)
    assert "no hay playbook" in unknown.output and "python" in unknown.output


def test_playbook_sync_brings_the_team_playbooks(env, tmp_path):
    src = tmp_path / "team-playbooks"
    src.mkdir()
    git(src, "init", "-q", "-b", "main")
    git(src, "config", "user.email", "t@t")
    git(src, "config", "user.name", "t")
    (src / "rails").mkdir()
    (src / "rails" / "playbook.toml").write_text('name = "rails"\n[commands]\ntest = "rspec"\n')
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "playbooks")
    assert "clonado" in env.umbra("playbook", "sync", str(src)).output
    assert "actualizado" in env.umbra("playbook", "sync", str(src)).output
    listed = json.loads(env.umbra("playbook", "list", "--json").output)
    assert "rails" in listed and "python" in listed and "laravel" in listed
    assert Path(listed["rails"]).parent == playbooks.home()


def test_projects_overview_and_the_picker(env, tmp_path):
    env.mode("broken")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    rows = json.loads(env.umbra("projects", "--json").output)
    me = next(p for p in rows if Path(p["root"]) == env.root)
    assert me["needs"] == 1 and me["working"] == 0 and me["cost"].startswith("$")

    async def main():
        app = ProjectsApp(projects.overview())
        async with app.run_test() as pilot:
            await pilot.pause(0.3)
            await pilot.press("enter")
            await pilot.pause(0.2)
        return app.return_value

    assert Path(asyncio.run(main())) == env.root
