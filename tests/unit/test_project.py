import pytest

from umbra.unified import project


def test_init_python_stack(git_repo):
    (git_repo / "pyproject.toml").write_text("")
    result = project.init_project(git_repo)
    assert result["created"] and result["stack"] == "python"
    assert result["commands"] == {"test": "pytest -q", "lint": "ruff check ."}
    assert (git_repo / ".umbra" / "routines").is_dir()
    assert (git_repo / ".umbra" / "profiles").is_dir()
    gitignore = (git_repo / ".gitignore").read_text()
    assert ".umbra/umbra.db*" in gitignore and ".umbra/worktrees/" in gitignore


@pytest.mark.parametrize("marker,stack", [("package.json", "node"), ("composer.json", "php"),
                                          (None, "generic")])
def test_detect_other_stacks(git_repo, marker, stack):
    if marker:
        (git_repo / marker).write_text("{}")
    assert project.init_project(git_repo)["stack"] == stack


def test_laravel_uses_artisan(git_repo):
    (git_repo / "composer.json").write_text("{}")
    (git_repo / "artisan").write_text("")
    assert project.init_project(git_repo)["commands"]["test"] == "php artisan test"


def test_init_is_idempotent(git_repo):
    (git_repo / "pyproject.toml").write_text("")
    project.init_project(git_repo)
    toml = (git_repo / ".umbra" / "project.toml").read_text()
    gitignore = (git_repo / ".gitignore").read_text()
    second = project.init_project(git_repo)
    assert not second["created"]
    assert (git_repo / ".umbra" / "project.toml").read_text() == toml
    assert (git_repo / ".gitignore").read_text() == gitignore


def test_init_from_subdirectory_uses_root(git_repo):
    sub = git_repo / "a" / "b"
    sub.mkdir(parents=True)
    project.init_project(sub)
    assert (git_repo / ".umbra" / "project.toml").exists()
    assert not (sub / ".umbra").exists()


def test_not_a_repo(tmp_path):
    with pytest.raises(project.NotARepo):
        project.init_project(tmp_path)
    assert not (tmp_path / ".umbra").exists()


def test_project_toml_with_bom_and_invalid_toml(git_repo):
    project.init_project(git_repo)
    path = git_repo / ".umbra" / "project.toml"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())  # como lo guarda PowerShell 5.1
    assert project.load_project(git_repo)["project"]["stack"] == "generic"
    path.write_text("esto no es toml")
    with pytest.raises(project.InvalidProject, match="no es TOML válido"):
        project.umbra_dir(git_repo)


def test_init_uses_current_branch_as_base(tmp_path):
    from tests.conftest import git
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "master")
    project.init_project(repo)
    assert project.load_project(repo)["project"]["base_branch"] == "master"


def test_fresh_repo_without_commits(git_repo, monkeypatch):
    from typer.testing import CliRunner

    from umbra.cli.main import app
    project.init_project(git_repo)
    monkeypatch.chdir(git_repo)
    runner = CliRunner()
    runner.invoke(app, ["task", "add", "x"])
    run = runner.invoke(app, ["run", "1"])
    assert run.exit_code == 2 and "commit inicial" in run.output
    assert runner.invoke(app, ["exec", "nope"]).exit_code == 2  # error claro, sin traceback


def test_status_requires_init(git_repo):
    with pytest.raises(project.NotInitialized):
        project.umbra_dir(git_repo)
