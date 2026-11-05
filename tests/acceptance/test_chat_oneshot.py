import json
from decimal import Decimal

from umbra.chat import launcher
from umbra.unified import project
from umbra.unified.events import add_event


def _flag(call, name):
    args = call["args"]
    return args[args.index(name) + 1]


def _set_config(env, text):
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text() + text)


def test_chat_message_prints_answer(env, monkeypatch):
    monkeypatch.setenv("PYTHONUTF8", "1")  # el falso lee stdin con la codificación local
    env.mode("noop")
    result = env.umbra("chat", "¿qué tareas hay?")
    assert result.stdout.strip() == "hecho"
    [call] = env.claude_calls()
    assert "-p" in call["args"]
    assert _flag(call, "--permission-mode") == "dontAsk"
    assert _flag(call, "--max-budget-usd") == "0.5"
    assert "--session-id" in call["args"]
    assert call["prompt"] == "¿qué tareas hay?"


def test_chat_message_from_stdin(env):
    env.mode("noop")
    result = env.umbra("chat", "-", input="hola")
    assert result.stdout.strip() == "hecho"
    assert env.claude_calls()[0]["prompt"] == "hola"


def test_chat_empty_message_fails_without_calling_claude(env):
    result = env.umbra("chat", "   ", ok=False)
    assert result.exit_code == 2
    assert env.claude_calls() == []


def test_chat_claude_error_exits_1(env):
    env.mode("error")
    result = env.umbra("chat", "hola", ok=False)
    assert result.exit_code == 1 and "boom" in result.stderr


def test_chat_message_without_claude_exits_2(env, monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    assert env.umbra("chat", "hola", ok=False).exit_code == 2


def test_chat_records_usage(env):
    env.mode("noop")
    before = env.conn.execute("SELECT COUNT(*) FROM usage").fetchone()[0]
    env.umbra("chat", "hola")
    rows = env.conn.execute("SELECT * FROM usage").fetchall()
    assert len(rows) == before + 1
    row = rows[-1]
    assert row["cost"] == "0.05" and row["agent"] == "claude" and row["attempt_id"] is None


def test_chat_invalid_budget_exits_2(env):
    _set_config(env, "\n[chat]\nmax_cost_usd = 0\n")
    assert env.umbra("chat", "hola", ok=False).exit_code == 2
    assert env.claude_calls() == []


def test_chat_oneshot_does_not_touch_interactive_files(env):
    env.mode("noop")
    env.umbra("chat", "hola")
    chat_dir = env.root / ".umbra" / "artifacts" / "chat"
    assert not (chat_dir / "system-prompt.md").exists()
    assert not (chat_dir / "settings.json").exists()


def test_headless_settings_never_ask(env):
    config = project.load_project(env.root)
    perms = launcher.build_settings(config, "umbra", headless=True)["permissions"]
    assert perms["ask"] == []
    assert "Bash(umbra run *)" in perms["deny"] and "Bash(umbra approve *)" in perms["deny"]
    assert "Bash(umbra status *)" in perms["allow"]
    allowed = launcher.build_settings(config, "umbra", headless=True,
                                      allow_changes=True)["permissions"]
    assert "Bash(umbra run *)" in allowed["allow"] and "Bash(umbra approve *)" in allowed["deny"]


def test_chat_json_ok(env):
    env.mode("noop")
    result = env.umbra("chat", "hola", "--json")
    out = json.loads(result.stdout)
    assert out["status"] == "ok" and out["answer"] == "hecho" and out["error"] is None
    assert Decimal(out["cost_usd"]) == Decimal("0.05") and out["commands"] == []
    assert out["session_id"]


def test_chat_json_claude_error(env):
    env.mode("error")
    result = env.umbra("chat", "hola", "--json", ok=False)
    out = json.loads(result.stdout)
    assert result.exit_code == 1 and out["status"] == "error" and "boom" in out["error"]


def test_chat_json_empty_message_is_json(env):
    result = env.umbra("chat", "  ", "--json", ok=False)
    out = json.loads(result.stdout)
    assert result.exit_code == 2 and out["status"] == "error" and out["answer"] is None
    assert out["commands"] == [] and out["cost_usd"] == "0"


def test_chat_json_without_claude_is_json(env, monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    result = env.umbra("chat", "hola", "--json", ok=False)
    assert result.exit_code == 2 and json.loads(result.stdout)["status"] == "error"


def test_ask_commands_only_from_this_session(env, monkeypatch):
    env.mode("noop")
    add_event(env.conn, None, "chat.command", "chat", command="antes", session_id="sess-fake")
    real = launcher.run_bounded

    def run(*a, **kw):
        proc = real(*a, **kw)
        for cmd, sid in (("umbra status", "sess-fake"), ("otro", "otra"),
                         ("umbra log 1", "sess-fake")):
            add_event(env.conn, None, "chat.command", "chat", command=cmd, session_id=sid)
        return proc

    monkeypatch.setattr(launcher, "run_bounded", run)
    cfg = project.load_project(env.root)
    out = launcher.ask(env.root, env.root / ".umbra", env.conn, cfg, "hola")
    assert out["commands"] == ["umbra status", "umbra log 1"]


def _last_session_file(env):
    return env.root / ".umbra" / "artifacts" / "chat" / "last-session"


def test_chat_continue_resumes_last_session(env):
    env.mode("noop")
    env.umbra("chat", "hola")
    assert _last_session_file(env).read_text().strip() == "sess-fake"
    assert launcher.last_session(env.root / ".umbra") == "sess-fake"
    env.umbra("chat", "¿y la siguiente?", "--continue")
    second = env.claude_calls()[1]
    assert _flag(second, "--resume") == "sess-fake" and "--session-id" not in second["args"]


def test_chat_continue_without_previous_starts_new(env):
    env.mode("noop")
    result = env.umbra("chat", "hola", "--continue")
    assert "no hay conversación anterior" in result.stderr
    [call] = env.claude_calls()
    assert "--session-id" in call["args"] and "--resume" not in call["args"]


def test_chat_session_option_resumes_given_id(env):
    env.mode("noop")
    env.umbra("chat", "hola", "--session", "abc")
    assert _flag(env.claude_calls()[0], "--resume") == "abc"


def test_chat_continue_and_session_together_exit_2(env):
    result = env.umbra("chat", "hola", "--continue", "--session", "x", ok=False)
    assert result.exit_code == 2 and env.claude_calls() == []


def test_chat_json_without_message_exits_2(env):
    assert env.umbra("chat", "--json", ok=False).exit_code == 2
    assert env.umbra("chat", "--continue", ok=False).exit_code == 2
    assert env.umbra("chat", "--session", "x", ok=False).exit_code == 2


def test_chat_error_does_not_overwrite_last_session(env):
    env.mode("error")
    env.umbra("chat", "hola", ok=False)
    assert not _last_session_file(env).exists()
    env.mode("noop")
    env.umbra("chat", "hola")
    env.mode("error")
    env.umbra("chat", "otra", "--session", "zzz", ok=False)
    assert _last_session_file(env).read_text().strip() == "sess-fake"
