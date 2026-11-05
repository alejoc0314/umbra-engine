"""Memoria de decisiones (spec 015, historia 1): lo que la persona decide una vez vale para las
tareas siguientes del mismo repo."""

import json

from umbra.routines import worker


def use_feature(env):
    env.plain_routine()  # sin escalada ni árbitro: aquí los hallazgos deben detener
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace('default_routine = "quick"',
                                           'default_routine = "feature"'))


def review_results(env, number):
    return [json.loads(r[0]) for r in env.conn.execute(
        "SELECT payload FROM event WHERE run_id = ? AND type = 'review.result' ORDER BY id",
        (env.run(number)["id"],))]


def test_waived_finding_is_written_shown_and_does_not_block_the_next_task(env):
    use_feature(env)
    env.codex_mode("high:falta validar entradas")  # el mismo hallazgo en todas las revisiones
    env.mode("ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    assert env.run(1)["status"] == "BLOCKED"
    assert env.umbra("memory", "show").output.strip() == \
        "umbra aún no ha aprendido nada en este repo"

    # (a) la decisión queda escrita y se puede ver y reconstruir
    env.umbra("finding", "waive", "1", "-m", "no aplica")
    learned = env.root / ".umbra" / "aprendido.md"
    assert learned.exists()
    text = learned.read_text(encoding="utf-8")
    assert "## Revisión: no pedir" in text
    assert "- falta validar entradas (tarea 1," in text and "no aplica)" in text
    assert "falta validar entradas" in env.umbra("memory", "show").output
    learned.unlink()
    out = json.loads(env.umbra("memory", "rebuild", "--json").output)
    assert out["path"].endswith("aprendido.md")
    assert learned.read_text(encoding="utf-8") == text
    assert json.loads(env.umbra("memory", "show", "--json").output)["text"] == text

    # (b) la tarea 2 recibe el mismo hallazgo y no se frena: ya está decidido
    env.umbra("task", "add", "Restar", "-a", "sub(3, 2) == 1")
    env.umbra("run", "2", "--foreground")
    assert env.run(2)["status"] == "WAITING_APPROVAL"
    assert review_results(env, 2)[-1]["remembered"] == 1
    # (d) el revisor recibió el hallazgo y su motivo en su sobre
    reviewer = env.codex_calls()[-1]["prompt"]
    assert "decisiones ya tomadas por la persona responsable" in reviewer
    assert "Aprendido en este repo" in reviewer and "falta validar entradas" in reviewer
    assert "no aplica" in reviewer


def test_answer_reaches_the_builder_of_another_task(env):
    env.mode("blocked", "ok", "ok", "ok")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    assert env.run(1)["status"] == "BLOCKED"
    env.umbra("task", "answer", "1", "Los negativos se suman igual.")
    worker.work(env.root)
    assert env.run(1)["status"] == "WAITING_APPROVAL"
    text = (env.root / ".umbra" / "aprendido.md").read_text(encoding="utf-8")
    assert "## Respuestas dadas" in text
    assert "¿Qué debe pasar con números negativos?" in text
    assert "Los negativos se suman igual." in text

    # (c) el constructor de otra tarea recibe la pregunta y la respuesta
    env.umbra("task", "add", "Restar", "-a", "sub(3, 2) == 1")
    env.umbra("run", "2", "--foreground")
    prompt = env.claude_calls()[-1]["prompt"]
    assert "Aprendido en este repo" in prompt
    # (el `claude` falso lee stdin con la codificación de la consola: se comparan tramos ASCII)
    assert "debe pasar con n" in prompt and "Los negativos se suman igual." in prompt
