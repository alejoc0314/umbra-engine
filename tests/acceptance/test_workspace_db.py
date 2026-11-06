"""Tus proyectos de C:/apps y tu MySQL local desde Telegram (spec 024)."""

import json
import subprocess
import time

import pytest

from tests.acceptance.test_telegram import poll
from tests.acceptance.test_telegram_chat import twin
from umbra import service
from umbra.blocks import mysql
from umbra.chat import launcher
from umbra.management import projects


def wait(cond, seconds=30):
    end = time.monotonic() + seconds
    while not cond():
        assert time.monotonic() < end, "no pasó a tiempo"
        time.sleep(0.1)


def answers(*texts, then=None):
    """Un `launcher.ask` falso que contesta en orden y apunta con qué lo llamaron."""
    calls = []

    def fake(root, udir, conn, config, message, *, allow_changes=False, resume=None, extra=""):
        calls.append({"root": root, "message": message, "extra": extra})
        if then:
            then(root)
        return {"status": "ok", "answer": texts[min(len(calls), len(texts)) - 1],
                "session_id": f"s{len(calls)}", "cost_usd": "0", "commands": [], "error": None}
    return fake, calls


def test_projects_lists_every_folder_and_finds_unregistered_repos(env, tg, tmp_path):
    other = twin(env, tmp_path, "otro")
    projects.forget_missing()
    index = [p for p in projects.load() if p["name"] != "otro"]
    projects._path().write_text(json.dumps(index))  # como api-ventas
    (tmp_path / "suelta").mkdir()
    tg.say("/proyectos")
    st = poll(env, tg)
    text = tg.sent[-1]["text"]
    assert "otro" in st.roots and st.roots["otro"] == other
    assert "/adoptar" in text and "suelta" in text
    assert "otro" in {p["name"] for p in projects.load()}  # vuelve al índice


def test_adopting_a_plain_folder_creates_repo_and_switches(env, tg, tmp_path):
    folder = tmp_path / "suelta"
    folder.mkdir()
    (folder / "app.py").write_text("print('hola')\n")
    (folder / ".env").write_text("SECRETO=1\n")
    tg.say("/adoptar suelta")
    st = poll(env, tg)
    wait(lambda: st.current == "suelta")
    assert (folder / ".umbra" / "project.toml").is_file()
    tracked = subprocess.run(["git", "ls-files"], cwd=folder, capture_output=True,
                             text=True).stdout.split()
    assert "app.py" in tracked and ".env" not in tracked  # el secreto no se versiona
    wait(lambda: "umbra adoptó" in tg.sent[-1]["text"])
    assert "primer commit" in tg.sent[-1]["text"]
    tg.say("/adoptar suelta")
    poll(env, tg, st)
    assert "ya tiene umbra" in tg.sent[-1]["text"]
    tg.say("/adoptar ../fuera")
    poll(env, tg, st)
    assert "No hay una carpeta" in tg.sent[-1]["text"]


def test_adopting_a_folder_with_two_repos_creates_a_workspace(env, tg, tmp_path):
    folder = tmp_path / "tienda"
    for name in ("api", "front"):
        repo = folder / name
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    tg.say("/adoptar tienda")
    st = poll(env, tg)
    wait(lambda: st.current == "tienda")
    wait(lambda: "umbra adoptó" in tg.sent[-1]["text"])
    assert "espacio de trabajo con api, front" in tg.sent[-1]["text"]
    assert not (folder / ".git").exists()  # la carpeta padre no se vuelve un repo
    assert "repos = [\"api\", \"front\"]" in (folder / ".umbra" / "project.toml").read_text()
    assert (folder / "api" / ".umbra" / "project.toml").is_file()


def test_conversation_knows_other_projects_and_can_switch(env, tg, tmp_path, monkeypatch):
    other = twin(env, tmp_path, "otro")
    fake, calls = answers("Eso es de otro.\nUMBRA> usar otro", "Listo en otro.")
    monkeypatch.setattr(launcher, "ask", fake)
    tg.say("en otro crea una tarea")
    st = poll(env, tg)
    assert st.current == "otro"
    assert [c["root"] for c in calls] == [env.root, other]
    assert calls[1]["message"] == "en otro crea una tarea"  # se le repite el mensaje allí
    assert "Con umbra: otro, repo" in calls[0]["extra"] and "UMBRA> usar" in calls[0]["extra"]
    reply = tg.sent[-1]["text"]
    assert "Paso a otro" in reply and "Listo en otro." in reply and "UMBRA>" not in reply


def test_conversation_can_adopt_a_folder(env, tg, tmp_path, monkeypatch):
    (tmp_path / "suelta").mkdir()
    (tmp_path / "suelta" / "a.txt").write_text("a\n")
    fake, _ = answers("La adopto.\nUMBRA> adoptar suelta")
    monkeypatch.setattr(launcher, "ask", fake)
    tg.say("trabajemos en suelta")
    st = poll(env, tg)
    wait(lambda: st.current == "suelta")


def test_db_changes_wait_for_the_button(env, tg, monkeypatch):
    applied = []
    monkeypatch.setattr(mysql, "execute",
                        lambda config, sql, database=None: applied.append(sql) or 3)

    def propose(root):  # lo que haría la conversación con `umbra db change`
        env.umbra("db", "change", "UPDATE clientes SET activo = 0 WHERE id = 7", "--db", "crm")
    fake, _ = answers("Te propuse el cambio.", then=propose)
    monkeypatch.setattr(launcher, "ask", fake)
    tg.say("desactiva el cliente 7")
    st = poll(env, tg)
    offer = next(m for m in tg.sent if "Cambio propuesto" in m["text"])
    assert "crm" in offer["text"] and "UPDATE clientes" in offer["text"]
    assert applied == []  # proponer no toca la BD
    ok = next(d for label, d in tg.buttons(tg.sent.index(offer)) if label == "Aplicar cambio")
    tg.tap(ok)
    poll(env, tg, st)
    assert applied == ["UPDATE clientes SET activo = 0 WHERE id = 7"]
    assert "3 filas" in tg.sent[-1]["text"]
    assert service.db_pending(service.load(env.root)) == []
    tg.tap(ok)  # dos veces no se aplica
    poll(env, tg, st)
    assert "no hay un cambio pendiente" in tg.sent[-1]["text"] and len(applied) == 1

    tg.say("y el 8 también")
    poll(env, tg, st)
    no = [d for label, d in tg.buttons(-2) if label == "Descartar"][0]
    tg.tap(no)
    poll(env, tg, st)
    assert "descartado" in tg.sent[-1]["text"] and len(applied) == 1


def test_only_a_person_applies_db_changes(env, monkeypatch):
    change = env.umbra("db", "change", "DELETE FROM t", "--json").output
    cid = json.loads(change)["id"]
    monkeypatch.setattr(service, "interactive", lambda: False)
    assert env.umbra("db", "apply", cid, ok=False).exit_code == 3
    settings = launcher.build_settings({}, "umbra", headless=True, allow_changes=True)
    perms = settings["permissions"]
    assert "Bash(umbra db apply *)" in perms["deny"]
    assert "Bash(umbra db query *)" in perms["allow"]
    assert "Bash(umbra db change *)" in perms["allow"]


@pytest.mark.parametrize("sql", ["SELECT * FROM t", "  -- hola\n select 1;", "SHOW TABLES",
                                 "describe t", "/* x */ EXPLAIN SELECT 1"])
def test_reads_pass(sql):
    assert mysql.check_read_only(sql)


@pytest.mark.parametrize("sql", ["UPDATE t SET a = 1", "drop table t", "INSERT INTO t VALUES (1)",
                                 "-- select\nDELETE FROM t", "SELECT * FROM t INTO OUTFILE '/x'",
                                 ""])
def test_writes_are_not_queries(sql):
    with pytest.raises(mysql.MySQLError):
        mysql.check_read_only(sql)
