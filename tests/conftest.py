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


@pytest.fixture(autouse=True)
def lessons_without_writer(request, monkeypatch):
    """Las lecciones se cosechan con el borrador determinista: el redactor (un agente más)
    cambiaría las llamadas y los intentos que cuentan las demás pruebas (spec 035)."""
    if request.module.__name__.endswith("test_lessons"):
        return
    from umbra.unified import config as cfg
    monkeypatch.setattr(cfg, "LESSONS_WRITER", "")
