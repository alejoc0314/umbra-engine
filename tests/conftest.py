import subprocess

import pytest


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@umbra.local")
    git(repo, "config", "user.name", "umbra test")
    return repo


@pytest.fixture(autouse=True)
def umbra_home(tmp_path, monkeypatch):
    """Ninguna prueba toca ~/.umbra de la persona (índice de proyectos, preferencias, playbooks)."""
    monkeypatch.setenv("UMBRA_HOME", str(tmp_path / "umbra-home"))
