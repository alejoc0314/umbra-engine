import json

from umbra.chat import launcher


def _capture(env, monkeypatch, *args):
    """Ejecuta `umbra chat` y devuelve (permisos, prompt) que recibió claude."""
    seen = {}
    real = launcher.run_bounded

    def run(cmd, *a, **kw):
        def flag(name):
            return cmd[cmd.index(name) + 1]
        with open(flag("--settings"), encoding="utf-8") as f:
            seen["perms"] = json.load(f)["permissions"]
        with open(flag("--append-system-prompt-file"), encoding="utf-8") as f:
            seen["prompt"] = f.read()
        return real(cmd, *a, **kw)

    monkeypatch.setattr(launcher, "run_bounded", run)
    env.mode("noop")
    env.umbra("chat", "arranca la tarea 3", *args)
    return seen["perms"], seen["prompt"]


def test_chat_without_allow_changes_denies_run(env, monkeypatch):
    perms, prompt = _capture(env, monkeypatch)
    assert "Bash(umbra run *)" in perms["deny"] and "Bash(umbra run *)" not in perms["allow"]
    assert perms["ask"] == [] and "Bash(umbra approve *)" in perms["deny"]
    assert "nadie puede contestarte" in prompt and "bloqueados" in prompt


def test_chat_allow_changes_allows_run_but_not_forbidden(env, monkeypatch):
    perms, prompt = _capture(env, monkeypatch, "--allow-changes")
    assert "Bash(umbra run *)" in perms["allow"] and "Bash(umbra run *)" not in perms["deny"]
    assert "Bash(umbra approve *)" in perms["deny"]
    assert "Puedes ejecutar comandos que cambian estado" in prompt


def test_chat_allow_changes_without_message_exits_2(env):
    result = env.umbra("chat", "--allow-changes", ok=False)
    assert result.exit_code == 2 and env.claude_calls() == []
