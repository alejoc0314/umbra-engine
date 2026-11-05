"""Conversar con umbra desde Telegram sobre cualquiera de tus repos (spec 022)."""

import json
import sys

from tests.acceptance.test_telegram import poll, state
from tests.conftest import git
from umbra.chat import launcher
from umbra.management import projects
from umbra.unified import project


def _flag(args, name):
    return args[args.index(name) + 1] if name in args else None


def chat_calls(env):
    return [c for c in env.claude_calls() if "--session-id" in c["args"] or "--resume" in c["args"]]


def test_free_text_is_a_conversation_about_the_project(env, tg):
    env.mode("noop", "noop", "noop")
    tg.say("como va el proyecto?")  # ASCII: el claude falso lee stdin en cp1252 en Windows
    st = poll(env, tg)
    call = chat_calls(env)[-1]
    assert call["prompt"].strip() == "como va el proyecto?"
    assert _flag(call["args"], "--permission-mode") == "dontAsk"
    assert call["cwd"].replace("\\", "/") == env.root.as_posix()
    assert tg.sent[-1]["text"] == "hecho"  # lo que respondió el claude falso
    tg.say("y la tarea 1?")
    poll(env, tg, st)
    assert _flag(chat_calls(env)[-1]["args"], "--resume") == "sess-fake"  # misma conversación
    tg.say("/nuevo")
    poll(env, tg, st)
    assert "Conversación nueva" in tg.sent[-1]["text"]
    tg.say("empecemos")
    poll(env, tg, st)
    assert "--session-id" in chat_calls(env)[-1]["args"]
    assert env.conn.execute("SELECT COUNT(*) FROM usage WHERE agent = 'claude'").fetchone()[0] == 3


def test_plain_text_and_hacer_both_may_act(env, tg, monkeypatch):
    seen = []

    def fake_ask(root, udir, conn, config, message, *, allow_changes=False, resume=None, **kw):
        seen.append((message, allow_changes, resume))
        return {"status": "ok", "answer": "listo", "session_id": "s1", "cost_usd": "0",
                "commands": ["umbra task accept 1"] if allow_changes else [], "error": None}

    monkeypatch.setattr(launcher, "ask", fake_ask)
    tg.say("acepta la tarea 1")
    st = poll(env, tg)
    tg.say("/hacer acepta la tarea 1")
    poll(env, tg, st)
    assert seen == [("acepta la tarea 1", True, None), ("acepta la tarea 1", True, "s1")]
    assert "(ejecuté: umbra task accept 1)" in tg.sent[-1]["text"]


def test_a_number_only_answers_the_agent_when_it_asked(env, tg):
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.mode("noop")
    tg.say("1 cosa que quiero preguntar")  # la tarea 1 no está detenida: es conversación
    poll(env, tg)
    assert chat_calls(env)[-1]["prompt"].strip() == "1 cosa que quiero preguntar"
    assert env.conn.execute("SELECT COUNT(*) FROM event WHERE type = 'task.answered'"
                            ).fetchone()[0] == 0


def twin(env, tmp_path, name):
    """Otro repo con umbra y el mismo bot, registrado como el primero."""
    root = tmp_path / name
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "calc.py").write_text("def add(a, b):\n    return 0\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    project.init_project(root)
    (root / ".umbra" / "project.toml").write_text(
        (env.root / ".umbra" / "project.toml").read_text())
    return root


def test_projects_switch_and_buttons_route_to_their_repo(env, tg, tmp_path):
    other = twin(env, tmp_path, "otro")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")  # en «repo»: espera aprobación
    tg.say("/proyectos")
    st = poll(env, tg)
    text = tg.sent[-1]["text"]
    assert "▶ repo" in text and "  otro" in text and "te necesitan 1" in text
    assert set(st.roots) == {"repo", "otro"}
    assert {p["name"] for p in projects.load()} >= {"repo", "otro"}
    tg.say("/usar otro")
    poll(env, tg, st)
    assert st.current == "otro" and "nada te necesita" in tg.sent[-1]["text"]
    tg.say("/estado")
    poll(env, tg, st)
    assert tg.sent[-1]["text"].startswith("otro:")
    env.mode("noop")
    tg.say("que hay?")  # la conversación va al proyecto actual
    poll(env, tg, st)
    assert chat_calls(env)[-1]["cwd"].replace("\\", "/") == other.as_posix()
    tg.tap("diff:1@repo")  # un botón de «repo» se atiende en «repo» aunque el actual sea «otro»
    poll(env, tg, st)
    assert "calc.py" in tg.sent[-1]["text"] and st.current == "repo"
    tg.say("/usar nada")
    poll(env, tg, st)
    assert "No conozco" in tg.sent[-1]["text"]


def test_long_answers_are_split(env, tg, monkeypatch):
    monkeypatch.setattr(launcher, "ask", lambda *a, **k: {
        "status": "ok", "answer": "x" * 8000, "session_id": "s", "cost_usd": "0",
        "commands": [], "error": None})
    tg.say("cuentamelo todo")
    poll(env, tg)
    assert [len(m["text"]) for m in tg.sent[-3:]] == [3900, 3900, 200]


def test_serve_is_a_single_process_for_all_repos(env, tg, monkeypatch):
    from umbra.routines import bridge
    bridge._beat()  # «otro» puente vivo (otro proceso)
    monkeypatch.setattr(bridge, "_me", lambda: "999@otro")
    assert bridge.serve(env.root) == 0
    assert sys.platform  # (sin más efectos: no se tocó el latido ajeno)
    assert bridge.alive()


def test_local_toml_holds_personal_config_and_is_ignored_by_git(env):
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace("desktop = false", "desktop = true"))
    (env.root / ".umbra" / "local.toml").write_text(
        '[notify]\ndesktop = false\n\n[notify.telegram]\ntoken_env = "T"\nchat_id = 7\n\n'
        '[editor]\ncommand = "vim"\n', encoding="utf-8")
    loaded = project.load_project(env.root)
    assert loaded["notify"]["desktop"] is False  # local.toml pisa project.toml…
    assert loaded["notify"]["bell"] is True  # …sin borrar el resto de la tabla
    assert loaded["notify"]["telegram"]["chat_id"] == 7 and loaded["editor"]["command"] == "vim"
    assert loaded["commands"]["test"]["safe"] is True
    assert ".umbra/local.toml" in (env.root / ".gitignore").read_text()
    assert "local.toml" not in git(env.root, "status", "--porcelain", "--ignored=no").stdout


def test_markdown_answers_arrive_formatted_for_telegram(env, tg, monkeypatch):
    md = ("Ahora mismo **no hay nada en marcha**.\n\n## Pendiente\n\n- Tarea 17 (`umbra run 17`)\n"
          "- Otra <cosa> & tal\n\n```bash\numbra status\n```")
    monkeypatch.setattr(launcher, "ask", lambda *a, **k: {
        "status": "ok", "answer": md, "session_id": "s", "cost_usd": "0", "commands": [],
        "error": None})
    tg.say("que hay?")
    poll(env, tg)
    sent = tg.sent[-1]
    assert sent["parse_mode"] == "HTML"
    assert sent["text"] == ("Ahora mismo <b>no hay nada en marcha</b>.\n\n<b>Pendiente</b>\n\n"
                            "• Tarea 17 (<code>umbra run 17</code>)\n• Otra &lt;cosa&gt; &amp; tal"
                            "\n\n<pre>umbra status</pre>")
    tg.say("/estado")  # sin Markdown: texto plano, sin parse_mode
    poll(env, tg)
    assert "parse_mode" not in tg.sent[-1]


def test_a_broken_resumed_session_retries_fresh_and_errors_have_detail(env, tg, monkeypatch):
    seen = []

    def fake_ask(root, udir, conn, config, message, *, allow_changes=False, resume=None, **kw):
        seen.append(resume)
        if resume == "vieja":
            return {"status": "error", "answer": "", "session_id": resume, "cost_usd": "0",
                    "commands": [], "error": "No conversation found with session ID"}
        return {"status": "ok", "answer": "ok", "session_id": "nueva", "cost_usd": "0",
                "commands": [], "error": None}

    monkeypatch.setattr(launcher, "ask", fake_ask)
    st = state(env)
    st.sessions["repo"] = "vieja"
    tg.say("sigues ahi?")
    poll(env, tg, st)
    assert seen == ["vieja", None] and tg.sent[-1]["text"] == "ok"
    assert st.sessions["repo"] == "nueva"
    # un error de claude sin texto ya no se muestra como «None»
    from umbra.adapters.claude_code import parse_stream
    res = parse_stream('{"type":"result","subtype":"error_max_turns","is_error":true}')
    assert "sin detalle" in res.error and "error_max_turns" in res.error
    res = parse_stream('{"type":"result","is_error":true,"errors":["budget exceeded"]}')
    assert res.error == "budget exceeded"


def test_chat_error_leaves_a_log_with_the_raw_output(env):
    env.mode("error")
    out = env.umbra("chat", "hola", "--json", ok=False).output
    data = json.loads(out)
    assert data["status"] == "error" and "last-error.log" in data["error"]
    log = env.root / ".umbra" / "artifacts" / "chat" / "last-error.log"
    assert "boom" in log.read_text(encoding="utf-8")
