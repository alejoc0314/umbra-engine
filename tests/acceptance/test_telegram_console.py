"""Telegram como consola de umbra (spec 023): lo que hace `umbra watch`, desde el teléfono."""

import json
import sys
import time
from pathlib import Path

from tests.acceptance.test_spec_conversation import install_flow
from tests.acceptance.test_telegram import poll, state
from tests.acceptance.test_verify_browser import with_dev
from tests.acceptance.test_watch_actions import sync_worker
from umbra.routines import bridge


def task(env, title="Sumar"):
    env.umbra("task", "add", title, "-a", "add(2, 3) == 5")


def texts(tg):
    return [m["text"] for m in tg.sent]


def wait(cond, seconds=30, info=None):
    end = time.monotonic() + seconds
    while not cond():
        assert time.monotonic() < end, f"no pasó a tiempo: {info() if info else ''}"
        time.sleep(0.1)


def test_a_finished_task_arrives_with_report_and_screenshots(env, tg):
    url = with_dev(env)
    env.mode("noop", "ok", "browse")
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    report = next(t for t in texts(tg) if "tarea #1 lista" in t)
    assert "<b>Qué se hizo</b>" in report and "Cómo se comprobó" in report
    assert "Criterios de aceptación: 1 de 1 cumplidos" in report
    assert "Visto en el navegador: 1 captura" in report and "Costo" in report
    assert tg.uploads == [("sendPhoto", {"files": 1, "names": ["home.png"]})]
    assert url  # la app se levantó para verla
    # y después del informe llega la decisión con botones
    assert "Espera tu aprobación" in texts(tg)[-1]


def test_tasks_explain_log_evidence_changes_agent_and_findings(env, tg):
    task(env)
    task(env, "Otra")
    env.umbra("run", "1", "--foreground")
    st = state(env)
    tg.say("/tareas")
    poll(env, tg, st)
    out = texts(tg)[-1]
    assert "<b>Te necesitan</b>" in out and "#1 Sumar" in out and "#2 Otra" in out
    for cmd, needle in (("/explicar 1", "Espera tu aprobación"), ("/registro 1", "Construir"),
                        ("/evidencia 1", "Qué se hizo"), ("/cambios 1", "calc.py"),
                        ("/agente 1", "Agente de #1"), ("/hallazgos 1", "no tiene hallazgos")):
        tg.say(cmd)
        poll(env, tg, st)
        assert needle in texts(tg)[-1], cmd
    tg.say("/explicar")
    poll(env, tg, st)
    assert "Indica el número" in texts(tg)[-1]
    tg.say("/explicar 9")
    poll(env, tg, st)
    assert "No se pudo" in texts(tg)[-1]


def test_task_lifecycle_from_the_phone(env, tg):
    sync_worker(env)
    st = state(env)
    tg.say("/tarea Sumar bien | add(2, 3) == 5 | add(0, 0) == 0")
    poll(env, tg, st)
    assert "Tarea 1 registrada" in texts(tg)[-1]
    row = env.conn.execute("SELECT status, acceptance FROM task").fetchone()
    assert row["status"] == "accepted" and json.loads(row["acceptance"]) == [
        "add(2, 3) == 5", "add(0, 0) == 0"]
    env.mode("broken")
    tg.say("/ejecutar 1")
    poll(env, tg, st)
    assert env.run()["status"] == "BLOCKED"
    env.mode("ok")
    tg.say("/reintentar 1 build")
    poll(env, tg, st)
    assert "desde Construir" in texts(tg)[-1] and env.run()["status"] == "WAITING_APPROVAL"
    tg.say("/rechazar 1 no me convence")
    poll(env, tg, st)
    assert env.run()["status"] == "CANCELLED" and env.prs()[-1]["state"] == "CLOSED"
    tg.say("/decero 1")
    poll(env, tg, st)
    assert env.run()["status"] == "WAITING_APPROVAL"
    tg.say("/integrar 1")
    poll(env, tg, st)
    assert env.run()["status"] == "SUCCEEDED" and "integrada" in texts(tg)[-1]
    tg.say("/tarea Pendiente | x")
    poll(env, tg, st)
    tg.say("/descartar 2")
    poll(env, tg, st)
    assert env.conn.execute("SELECT status FROM task WHERE number = 2").fetchone()[0] == "dropped"
    origins = {r[0] for r in env.conn.execute("SELECT DISTINCT origin FROM event WHERE type IN"
                                              " ('task.added', 'run.retried', 'run.queued')")}
    assert origins == {"telegram"}


def test_findings_decided_from_the_phone(env, tg):
    env.plain_routine()
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace('default_routine = "quick"',
                                           'default_routine = "feature"'))
    env.codex_mode("high:falta validar entradas")
    env.mode("noop", "ok")
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    sync_worker(env)
    st = state(env)
    tg.say("/hallazgos 1")
    poll(env, tg, st)
    assert "falta validar entradas" in texts(tg)[-1]
    env.codex_mode("clean")
    tg.say("/noaplica 1")
    poll(env, tg, st)
    assert "Decidido (1 hallazgos)" in texts(tg)[-1]
    assert env.run()["status"] == "WAITING_APPROVAL"


def test_spec_conversation_from_the_phone(env, tg):
    install_flow(env)
    st = state(env)
    tg.say("/spec una idea")
    poll(env, tg, st)
    assert "Empiezo la spec" in texts(tg)[-1]
    wait(lambda: any("¿Cuántos?" in t for t in texts(tg)))
    question = next(m for m in tg.sent if m["text"] == "¿Cuántos?")
    keys = [b["callback_data"] for row in question["reply_markup"]["inline_keyboard"] for b in row]
    assert keys == ["sq:1@repo", "sq:0@repo", "sq:otra@repo"]  # la recomendada primero
    assert question["reply_markup"]["inline_keyboard"][0][0]["text"] == "1000 (recomendada)"
    tg.tap("sq:1@repo")
    poll(env, tg, st)
    wait(lambda: any("Revisa la spec" in t for t in texts(tg)))
    assert st.talks["repo"].pending == ("review",)
    tg.say("/spec_ver")
    poll(env, tg, st)
    assert tg.uploads[-1] == ("sendDocument", {"files": 1, "names": ["spec.md"]})
    tg.tap("sr:approve@repo")
    poll(env, tg, st)
    wait(lambda: any("Revisa el plan" in t for t in texts(tg)))
    tg.tap("sr:approve@repo")
    poll(env, tg, st)
    wait(lambda: any("Tareas en borrador: [1, 2]" in t for t in texts(tg)))
    wait(lambda: st.talks["repo"].done)
    assert [r["spec_dir"] for r in env.conn.execute("SELECT spec_dir FROM task")] \
        == ["specs/001-x"] * 2
    events = [(r["type"], r["origin"]) for r in env.conn.execute(
        "SELECT type, origin FROM event WHERE type LIKE 'spec.%' ORDER BY id")]
    assert events == [("spec.started", "telegram"), ("spec.approved", "telegram"),
                      ("spec.approved", "telegram"), ("spec.tasks", "telegram")]
    tg.say("/spec_salir")
    poll(env, tg, st)
    assert "No hay una spec en curso" in texts(tg)[-1]


def test_asking_for_a_spec_in_plain_words_opens_the_conversation(env, tg, monkeypatch):
    from tests.acceptance.test_workspace_db import answers
    from umbra.chat import launcher
    install_flow(env)
    fake, calls = answers("La abro.\nUMBRA> spec una idea")
    monkeypatch.setattr(launcher, "ask", fake)
    st = state(env)
    tg.say("crea una spec para una idea")
    poll(env, tg, st)
    assert "UMBRA> spec" in calls[0]["extra"] and "umbra spec new" in calls[0]["extra"]
    assert "La abro." in texts(tg)[-1] and "Empiezo la spec" in texts(tg)[-1]
    wait(lambda: any("¿Cuántos?" in t for t in texts(tg)))
    assert "repo" in st.talks


def test_spec_changes_and_discard_from_the_phone(env, tg):
    install_flow(env)
    st = state(env)
    tg.say("/spec una idea")
    poll(env, tg, st)
    wait(lambda: any("¿Cuántos?" in t for t in texts(tg)))
    tg.tap("sq:otra@repo")
    poll(env, tg, st)
    wait(lambda: "Escribe tu respuesta" in texts(tg)[-1])
    tg.say("unos 50")
    poll(env, tg, st)
    wait(lambda: any("Revisa la spec" in t for t in texts(tg)))
    assert env.claude_calls()[-1]["message"] == "unos 50"
    tg.tap("sr:changes@repo")
    poll(env, tg, st)
    wait(lambda: "Qué cambios pides" in texts(tg)[-1])
    tg.say("mas corta")
    poll(env, tg, st)
    wait(lambda: env.claude_calls()[-1]["message"] == "Cambios pedidos: mas corta",
         info=lambda: (texts(tg)[-4:], [c["message"] for c in env.claude_calls()]))
    wait(lambda: not st.talks["repo"].busy)
    tg.tap("sr:discard@repo")
    poll(env, tg, st)
    wait(lambda: any("descartada" in t for t in texts(tg)))
    assert env.conn.execute("SELECT phase FROM conversation").fetchone()[0] == "discarded"


def test_new_project_and_plan_from_the_phone(env, tg, tmp_path):
    from tests.acceptance.test_new_project import team_playbook
    team_playbook(env)
    env.mode("context", "propose")
    st = state(env)
    tg.say("/nuevo_proyecto demo python")
    poll(env, tg, st)
    assert "Creando demo" in texts(tg)[-1]
    wait(lambda: any("Proyecto creado" in t for t in texts(tg)), 60)
    assert st.current == "demo" and (tmp_path / "demo" / "CONTEXT.md").exists()
    (tmp_path / "demo" / "specs").mkdir()
    (tmp_path / "demo" / "specs" / "idea.md").write_text("# Idea\nUna calculadora.\n")
    tg.say("/plan specs/idea.md")
    poll(env, tg, st)
    assert "Planificando" in texts(tg)[-1]
    wait(lambda: any("Tareas en borrador" in t for t in texts(tg)), 60)
    from umbra.unified.store import open_store
    assert open_store(tmp_path / "demo" / ".umbra").execute(
        "SELECT COUNT(*) FROM task WHERE status = 'draft'").fetchone()[0] == 3


def test_night_and_help_and_menu(env, tg):
    sync_worker(env)
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5", "--draft")
    st = state(env)
    tg.say("/noche")
    poll(env, tg, st)
    assert "Aceptadas 1" in texts(tg)[-1]
    tg.say("/ayuda")
    poll(env, tg, st)
    assert "/nuevo_proyecto" in texts(tg)[-1] and "/spec" in texts(tg)[-1]
    tg.say("/loquesea")
    poll(env, tg, st)
    assert "No conozco /loquesea" in texts(tg)[-1]
    from umbra.blocks import telegram
    telegram.set_commands(st.tg, bridge.COMMANDS)
    method, body = tg.calls[-1]
    assert method == "setMyCommands" and body["commands"][0]["command"] == "tareas"
    assert sys.platform and Path(env.root).exists()
