"""Decidir desde el teléfono (spec 019): avisos con botones por Telegram y el puente."""

import json

from tests.acceptance.test_parallel_spec import SPEC, TASKS, configure
from tests.acceptance.test_watch_actions import sync_worker
from umbra import service
from umbra.blocks import telegram
from umbra.routines import bridge

CHAT = 42  # el chat_id del Telegram falso (conftest)


def task(env):
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")


def state(env):
    """El puente tal como arrancaría desde este repo (un solo bot para todos los repos)."""
    from umbra.unified import project
    return bridge.State(telegram.settings(project.load_project(env.root)),
                        bridge.served(env.root), env.root.name)


def poll(env, fake, st=None):
    st = st or state(env)
    bridge.run_once(st, timeout=0)
    return st


def test_policy_block_arrives_with_buttons_and_authorizing_resumes(env, tg):
    env.mode("skip_test", "skip_test")  # «arregla» desactivando el test: la política frena
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    assert tg.sent[-1]["chat_id"] == str(CHAT)
    assert "umbra · repo · tarea #1 Sumar" in tg.sent[-1]["text"]  # el repo viaja en el texto
    labels = {data: text for text, data in tg.buttons()}
    assert labels["allow:1@repo"].startswith("🔓 Autorizar") and "retry:1@repo" in labels
    sync_worker(env)
    tg.tap("allow:1@repo")  # el botón trae el repo: el puente lo atiende aunque esté en otro
    poll(env, tg)
    assert env.run()["status"] == "WAITING_APPROVAL"
    allowed = env.conn.execute("SELECT origin FROM event WHERE type = 'policy.allowed'"
                               ).fetchone()[0]
    assert allowed == "telegram"
    assert any("Autorizado" in m["text"] for m in tg.sent)
    assert any(m == "editMessageReplyMarkup" for m, _ in tg.calls)
    # la espera de aprobación también llegó al teléfono, con sus botones
    assert any(data == "approve:1@repo" for i in (-2, -1) for _, data in tg.buttons(i))


def test_approve_and_diff_from_the_phone(env, tg):
    task(env)
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    assert "Espera tu aprobación" in tg.sent[-1]["text"]
    tg.tap("diff:1")
    poll(env, tg)
    assert "calc.py" in tg.sent[-1]["text"] and "github.test/pr/1" in tg.sent[-1]["text"]
    tg.tap("approve:1")
    poll(env, tg)
    assert env.run()["status"] == "SUCCEEDED"
    assert "integrada" in tg.sent[-1]["text"]
    decided = json.loads(env.conn.execute("SELECT payload FROM event WHERE type ="
                                          " 'telegram.decided' ORDER BY id DESC LIMIT 1"
                                          ).fetchone()[0])
    assert decided == {"action": "approve:1", "user": "alejandro"}


def test_answering_the_agent_by_text(env, tg):
    env.mode("blocked", "ok")
    task(env)
    env.umbra("run", "1", "--foreground")
    assert "Responde a este mensaje" in tg.sent[-1]["text"]
    sync_worker(env)
    tg.say("negativos también se suman", reply_to=tg.sent[-1]["text"])
    poll(env, tg)
    events = [tuple(r) for r in env.conn.execute(
        "SELECT type, payload FROM event WHERE type LIKE 'telegram.%' OR type = 'task.answered'")]
    row = env.conn.execute("SELECT payload FROM event WHERE type = 'task.answered'").fetchone()
    assert row, (events, [m["text"] for m in tg.sent])
    answered = json.loads(row[0])
    assert answered["answer"] == "negativos también se suman"
    assert env.run()["status"] == "WAITING_APPROVAL"
    tg.say("/ayuda")
    poll(env, tg)
    assert "Para responder" in tg.sent[-1]["text"]  # ayuda, sin tocar nada


def test_other_chats_are_ignored(env, tg):
    task(env)
    env.umbra("run", "1", "--foreground")
    before = len(tg.sent)
    tg.tap("approve:1", chat=99)
    tg.say("1 hola", chat=99)
    poll(env, tg)
    assert env.run()["status"] == "WAITING_APPROVAL" and len(tg.sent) == before


def test_spec_ready_arrives_and_one_tap_merges_it(env, tg):
    d = env.root / "specs" / "001-demo"
    d.mkdir(parents=True)
    (d / "spec.md").write_text(SPEC, encoding="utf-8")
    (d / "tasks.md").write_text(TASKS, encoding="utf-8")
    env.umbra("spec", "tasks", "specs/001-demo")
    configure(env, parallel=1, autopilot=True)
    env.mode("ok", "append_mul")
    sync_worker(env)
    env.umbra("night", "--spec", "specs/001-demo")
    assert "umbra · repo · spec 001-demo" in tg.sent[-1]["text"] and tg.buttons() == [
        ("✅ Integrar la spec", "spec:001-demo@repo")]
    # ninguna tarea pidió decisión (sí llegó el informe de cada una al integrarse)
    assert not any(d.startswith("approve:") for i in range(len(tg.sent))
                   for _, d in tg.buttons(i))
    assert sum("tarea #" in m["text"] and "lista" in m["text"] for m in tg.sent) == 2
    tg.tap("spec:001-demo")
    poll(env, tg)
    assert service.spec_pr(service.load(env.root), "specs/001-demo")["state"] == "merged"
    assert "integrada" in tg.sent[-1]["text"]


def test_bridge_stop(env, tg):
    assert env.umbra("bridge", "--stop").output.strip() == "no había ningún puente"
    bridge._beat()
    assert bridge.alive()
    assert env.umbra("bridge", "--stop").output.strip() == "puente detenido"
    assert not bridge.alive()
