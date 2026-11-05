"""Onboarding de un proyecto ya iniciado (spec 029)."""

import json

from tests.acceptance.test_telegram import poll, state
from tests.acceptance.test_telegram_console import texts, wait
from tests.conftest import git

EXPLORE = ["explore"] * 5  # los cinco exploradores, en paralelo
FOCUS = ("arquitectura", "dominio", "convenciones", "interfaz", "riesgos")


def flag(args, name):
    return args[args.index(name) + 1]


def notes(env):
    return env.root / ".umbra" / "artifacts" / "onboarding"


def test_onboarding_from_the_terminal(env):
    env.mode(*EXPLORE, "onboard_questions", "onboard_write")
    out = env.umbra("onboard", input="1\nsolo la uso yo\n1\n").output
    for name in ("reconocimiento", "linea-base", *FOCUS):
        assert (notes(env) / f"{name}.md").is_file(), name
    recon = (notes(env) / "reconocimiento.md").read_text(encoding="utf-8")
    assert "calc.py" in recon or "commits" in recon
    assert "**test**" in (notes(env) / "linea-base.md").read_text(encoding="utf-8")
    assert "Pregunta 1 de 2" in out and "Equipo interno (recomendada)" in out
    calls = env.claude_calls()
    for explorer in calls[:5]:  # solo lectura y con el modelo del explorador
        assert flag(explorer["args"], "--model") == "sonnet"
        assert "Edit" not in flag(explorer["args"], "--allowedTools")
    writer = calls[6]
    assert "Equipo interno" in writer["prompt"] and "solo la uso yo" in writer["prompt"]
    assert "Edit(CONTEXT.md)" in flag(writer["args"], "--allowedTools")
    log = git(env.root, "log", "-1", "--format=%s", "--name-only").stdout
    assert "umbra: onboarding" in log
    for path in ("CONTEXT.md", ".specify/memory/constitution.md",
                 "specs/000-linea-base/inventario.md"):
        assert path in log
    status = git(env.root, "status", "--porcelain", "-uall").stdout
    assert "onboarding" not in status and "CONTEXT" not in status  # las notas no ensucian
    st = json.loads((notes(env) / "estado.json").read_text(encoding="utf-8"))
    assert st["phase"] == "hecho" and st["answers"] == ["Equipo interno", "solo la uso yo"]


def test_onboarding_resumes_without_exploring_again(env):
    env.mode(*EXPLORE, "onboard_questions", "onboard_write")
    out = env.umbra("onboard", input="1\n").output  # responde una y se va
    assert "Queda a medias" in out
    assert len(env.claude_calls()) == 6
    out = env.umbra("onboard", input="2\n1\n").output
    assert "Pregunta 2 de 2" in out and "Aprobado" in out
    assert len(env.claude_calls()) == 7  # solo el redactor: no volvió a explorar
    assert "umbra: onboarding" in git(env.root, "log", "-1", "--format=%s").stdout
    assert "ya está hecho" in env.umbra("onboard").output


def test_writer_may_only_touch_its_artifacts(env):
    env.mode(*EXPLORE, "onboard_questions", "onboard_stray")
    result = env.umbra("onboard", input="1\n1\n", ok=False)
    assert result.exit_code != 0 and "calc.py" in result.output
    assert "return 42" not in (env.root / "calc.py").read_text()  # restaurado
    assert "onboarding" not in git(env.root, "log", "-1", "--format=%s").stdout


def test_onboarding_from_the_phone(env, tg):
    env.mode(*EXPLORE, "onboard_questions", "onboard_write", "onboard_write")
    st = state(env)
    tg.say("/onboarding")
    poll(env, tg, st)
    wait(lambda: any("Pregunta 1 de 2" in t for t in texts(tg)), 60)
    question = next(m for m in tg.sent if "Pregunta 1 de 2" in m["text"])
    keys = [b["callback_data"] for row in question["reply_markup"]["inline_keyboard"]
            for b in row]
    assert keys == ["oq:1@repo", "oq:0@repo", "oq:otra@repo"]  # la recomendada primero
    tg.tap("oq:1@repo")
    poll(env, tg, st)
    wait(lambda: any("Pregunta 2 de 2" in t for t in texts(tg)))
    tg.say("nada de nada")  # texto libre: es la respuesta
    poll(env, tg, st)
    wait(lambda: any("Lo apruebas" in t for t in texts(tg)))
    tg.tap("or:changes@repo")
    poll(env, tg, st)
    wait(lambda: any("Qué cambio" in t for t in texts(tg)))
    tg.say("agrega el glosario")
    poll(env, tg, st)
    wait(lambda: sum("Lo apruebas" in t for t in texts(tg)) == 2)
    assert "agrega el glosario" in env.claude_calls()[-1]["prompt"]
    tg.tap("or:approve@repo")
    poll(env, tg, st)
    wait(lambda: any("Aprobado" in t for t in texts(tg)))
    assert "umbra: onboarding" in git(env.root, "log", "-1", "--format=%s").stdout
