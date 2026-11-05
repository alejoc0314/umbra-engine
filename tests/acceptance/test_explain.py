"""Estados comprensibles: explicaciones, narración, política de tests y manejo de detenidas."""

import json

import pytest

from umbra.unified import explain as ex


def task(env, title="Sumar"):
    env.umbra("task", "add", title, "-a", "add(2, 3) == 5")


def explain_json(env, n=1):
    return json.loads(env.umbra("explain", str(n), "--json").output)


def test_adding_a_test_to_an_existing_file_is_not_blocked(env):  # el caso real
    env.mode("append_test")
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"


def test_skipping_an_existing_test_is_blocked_and_explained(env):
    env.mode("skip_test")
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    exp = explain_json(env)
    assert exp["code"] == "policy" and exp["state"].startswith("Detenida")
    assert exp["headline"] == "El agente desactivó un test (lo marcó para saltarse)."
    assert "red de seguridad" in exp["why"]
    assert any("pytest.mark.skip" in d for d in exp["details"])
    assert {"what": exp["actions"][0]["what"], "command": "umbra retry 1 --from build"} == \
        exp["actions"][0]
    assert exp["progress"][0] == ["Construir", "detenida"]


def test_retry_tells_the_agent_why_it_was_stopped(env):
    env.mode("delete_test")
    task(env)
    env.umbra("run", "1", "--foreground")
    env.mode("ok")
    env.umbra("retry", "1", "--from", "build", "--foreground")
    prompt = env.claude_calls()[-1]["prompt"]
    assert "se detuvo por esto" in prompt and "test existente borrado" in prompt
    assert "Deja los tests existentes" in prompt


def test_run_on_a_stopped_task_explains_instead_of_starting_over(env):
    env.mode("broken")
    task(env)
    env.umbra("run", "1", "--foreground")
    first = env.run()
    result = env.umbra("run", "1", ok=False)
    assert result.exit_code == 4 and "umbra retry 1" in result.output
    env.mode("ok")
    env.umbra("run", "1", "--new", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    old = env.conn.execute("SELECT status FROM run WHERE id = ?", (first["id"],)).fetchone()
    assert old[0] == "CANCELLED"  # la detenida se cerró y limpió


def test_states_are_explained_in_plain_words(env):
    env.umbra("task", "add", "Borrador", "--draft")
    assert explain_json(env)["headline"].startswith("Es un borrador")
    task(env, "Lista")
    assert explain_json(env, 2)["state"] == "Lista para ejecutar"
    env.umbra("run", "2", "--foreground")
    waiting = explain_json(env, 2)
    assert waiting["state"] == "Espera tu aprobación"
    assert [a["command"] for a in waiting["actions"]][1] == "umbra approve 2"
    assert all(mark == "hecho" for _, mark in waiting["progress"])
    env.umbra("approve", "2", input="y\n")
    assert explain_json(env, 2)["state"] == "Integrada"


def test_list_status_and_log_speak_plainly(env):
    env.mode("broken")
    task(env)
    env.umbra("run", "1", "--foreground")
    rows = json.loads(env.umbra("task", "list", "--json").output)
    assert rows[0]["situation"] == "Detenida: los tests siguen fallando"
    status = json.loads(env.umbra("status", "--json").output)
    assert status["attention"][0]["task"] == 1
    narrated = env.umbra("log", "1").output
    assert "Tests del proyecto: fallan" in narrated and "evidence.tests" not in narrated
    assert "evidence.tests" in env.umbra("log", "1", "--raw").output


@pytest.mark.parametrize("code", sorted(ex.REASONS))
def test_every_stop_reason_has_a_headline_and_an_action(code):
    headline, why, details, actions = ex.REASONS[code](7, {})
    assert headline.endswith(".") and why and actions
    assert all(a.what for a in actions)


@pytest.mark.parametrize("reason,code", [
    ("política: test existente modificado: tests/t.py", "policy"),
    ("los tests siguen fallando tras 3 intentos", "tests_failing"),
    ("el agente necesita aclaraciones: ¿qué base?", "agent_questions"),
    ("el agente no produjo cambios", "no_changes"),
    ("2 hallazgos bloqueantes en verify tras 3 revisiones", "findings"),
    ("secretos en el diff: x", "secrets"),
])
def test_old_reasons_without_code_are_understood(reason, code):
    found, details = ex.classify({"reason": reason}, "BLOCKED")
    assert found == code
    if code == "policy":
        assert details["violations"][0]["code"] == "test_changed"
    if code == "findings":
        assert details["stage"] == "verify"


def render_text(exp_dict):
    """Texto tal como se ve en `umbra explain` / el panel Situación de watch."""
    import io

    from rich.console import Console

    from umbra.cli.explain import renderable
    from umbra.unified.explain import Action, Explanation
    exp = Explanation(**{k: v for k, v in exp_dict.items() if k != "actions"},
                      actions=[Action(**a) for a in exp_dict["actions"]])
    console = Console(file=io.StringIO(), width=100, color_system=None)
    console.print(renderable(exp, compact=True))
    return console.file.getvalue()


def test_explanation_shows_what_the_task_is_about(env):
    env.umbra("task", "add", "Base", "-a", "x")
    env.umbra("task", "add", "Sumar bien", "-d", "add debe sumar dos números", "-a",
              "add(2, 3) == 5", "-s", "calc.py", "-p", "1", "--draft")
    env.umbra("task", "deps", "2", "--on", "1")
    exp = explain_json(env, 2)
    about = exp["about"]
    assert about["description"] == "add debe sumar dos números"
    assert about["acceptance"] == ["add(2, 3) == 5"] and about["scope"] == ["calc.py"]
    assert about["priority"] == "alta"
    assert about["depends_on"] == [{"number": 1, "title": "Base", "status": "Aceptada"}]
    assert explain_json(env, 1)["about"]["unblocks"][0]["number"] == 2
    text = render_text(exp)
    assert "De qué trata" in text and "Se considera hecha cuando:" in text
    assert "add(2, 3) == 5" in text and "Depende de: 1 Base" in text


def test_explanation_shows_what_the_agent_planned_and_did(env):
    env.mode("noop", "ok", "noop")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "-r", "feature", "--foreground")
    about = explain_json(env)["about"]
    assert about["plan"] == "modo noop" and about["work"] == "modo ok"
    text = render_text(explain_json(env))
    assert "Cómo lo planteó el planificador" in text and "Qué hizo el agente" in text


def test_task_without_criteria_is_flagged(env):
    env.umbra("task", "add", "Algo vago", "--draft")
    assert "Sin criterios de aceptación" in render_text(explain_json(env))
