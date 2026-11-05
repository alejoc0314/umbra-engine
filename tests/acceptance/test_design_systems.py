"""Sistemas de diseño por proyecto y réplica del diseño actual (spec 031)."""

import os
from pathlib import Path

import pytest
import typer

from tests.acceptance.test_design import flag
from tests.acceptance.test_e2 import feature_task, run_feature
from tests.acceptance.test_onboarding import EXPLORE
from tests.acceptance.test_spec_conversation import install_flow
from tests.acceptance.test_telegram import poll, state
from tests.acceptance.test_telegram_console import texts, wait
from tests.acceptance.test_verify_browser import with_dev
from tests.conftest import git
from umbra.cli import design as design_cli
from umbra.management import design_systems as ds
from umbra.unified import project


def install_system(name="kit") -> Path:
    folder = Path(os.environ["UMBRA_HOME"]) / "design" / name
    folder.mkdir(parents=True)
    (folder / "sistema.toml").write_text(
        'nombre = "Kit del equipo"\ndescripcion = "apps internas"\nguias = ["guia.md"]\n'
        'starter = "kit.lienzo"\n', encoding="utf-8")
    (folder / "guia.md").write_text("Botones siempre en MAYUSCULA.\n", encoding="utf-8")
    (folder / "kit.lienzo").write_text('{"kit": true}', encoding="utf-8")
    return folder


def test_catalog_choice_and_resolution(env):
    install_system()
    assert list(ds.catalog()) == ["kit"] and ds.needs_choice(project.load_project(env.root))
    ds.set_system(env.root, "kit")
    config = project.load_project(env.root)
    assert config["design"]["system"] == "kit" and not ds.needs_choice(config)
    design = ds.resolved(config)
    assert design["guides"][0].endswith("kit/guia.md") and design["starter"].endswith("kit.lienzo")
    ds.set_system(env.root, "ninguno")  # cambia sin duplicar la sección ni la clave
    text = (env.root / ".umbra" / "project.toml").read_text(encoding="utf-8")
    assert text.count("[design]") == 1 and text.count("system =") == 1
    assert 'system = "ninguno"' in text
    with pytest.raises(ValueError):
        ds.set_system(env.root, "otro")


def test_designer_gets_the_system_guides_and_starter(env):
    install_system()
    ds.set_system(env.root, "kit")
    env.mode("plan_ui", "design", "noop")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    designer = env.claude_calls()[1]
    assert "Botones siempre en MAYUSCULA" in designer["prompt"]
    assert "Botones siempre en MAYUSCULA" in env.claude_calls()[2]["prompt"]  # el crítico
    wt = Path(env.run()["worktree"])
    assert (wt / "design" / "repo.lienzo").read_text(encoding="utf-8") == '{"kit": true}'


def test_spec_new_asks_the_system_first(env, monkeypatch):
    install_system()
    monkeypatch.setattr(typer, "prompt", lambda *a, **k: "1")
    design_cli.ask_system(env.root, project.load_project(env.root))
    assert project.load_project(env.root)["design"]["system"] == "kit"
    monkeypatch.setattr(typer, "prompt", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    design_cli.ask_system(env.root, project.load_project(env.root))  # ya elegido: no pregunta


def test_spec_from_the_phone_asks_the_system_then_starts(env, tg):
    install_system()
    install_flow(env)
    st = state(env)
    tg.say("/spec una idea")
    poll(env, tg, st)
    keys = [b["callback_data"] for row in tg.sent[-1]["reply_markup"]["inline_keyboard"]
            for b in row]
    assert keys == ["ds:kit@repo", "ds:ninguno@repo"]
    tg.tap("ds:kit@repo")
    poll(env, tg, st)
    assert project.load_project(env.root)["design"]["system"] == "kit"
    wait(lambda: any("Empiezo la spec" in t or "Spec nueva" in t for t in texts(tg)))
    tg.say("/sistema ninguno")
    poll(env, tg, st)
    assert project.load_project(env.root)["design"]["system"] == "ninguno"


def test_onboarding_asks_the_system_first(env):
    install_system()
    env.mode(*EXPLORE, "onboard_questions", "onboard_write")
    out = env.umbra("onboard", input="1\n1\n1\n1\n").output
    assert "Pregunta 1 de 3: ¿Qué sistema de diseño" in out
    assert project.load_project(env.root)["design"]["system"] == "kit"
    files = git(env.root, "log", "-1", "--name-only", "--format=").stdout
    assert ".umbra/project.toml" in files  # va en el commit del onboarding


def test_replicate_the_current_design(env):
    with_dev(env)
    env.mode("replicate", "replicate")
    out = env.umbra("design", "replicar", input="y\n").output
    assert "1 vistas replicadas" in out and "Réplica guardada" in out
    files = git(env.root, "log", "-1", "--name-only", "--format=").stdout
    assert "design/actual/inicio.png" in files and "design/sistema.md" in files
    call = env.claude_calls()[0]
    assert flag(call["args"], "--model") == "sonnet" and "mcp__playwright" in call["args"][
        call["args"].index("--allowedTools") + 1]
    (env.root / "design" / "actual" / "inicio.png").unlink()
    git(env.root, "commit", "-qam", "quitar")
    out = env.umbra("design", "replicar", input="n\n").output
    assert "descartada" in out and not (env.root / "design" / "actual" / "inicio.png").exists()


def test_replica_needs_dev_and_only_touches_design(env):
    assert "dev" in env.umbra("design", "replicar", ok=False).output
    with_dev(env)
    env.mode("replicate_stray")
    result = env.umbra("design", "replicar", ok=False)
    assert result.exit_code != 0 and "calc.py" in result.output
    assert "return 42" not in (env.root / "calc.py").read_text()


def test_replicate_from_the_phone(env, tg):
    with_dev(env)
    env.mode("replicate")
    st = state(env)
    tg.say("/replicar")
    poll(env, tg, st)
    wait(lambda: any("vistas replicadas" in t for t in texts(tg)), 60)
    assert any(u[0] in ("sendPhoto", "sendMediaGroup") for u in tg.uploads)
    tg.tap("dr:approve@repo")
    poll(env, tg, st)
    assert "Réplica guardada" in tg.sent[-1]["text"]
