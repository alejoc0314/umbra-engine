import asyncio
import json

from umbra import service
from umbra.blocks import notify
from umbra.cli.watch import WatchApp


def feature(env, title="Sumar"):
    env.umbra("task", "add", title, "-d", "add debe sumar", "-a", "add(2, 3) == 5")


def run_feature(env, n=1):
    env.plain_routine()  # sin escalada ni árbitro: aquí los hallazgos deben detener
    env.umbra("run", str(n), "-r", "feature", "--foreground")
    return env.run(n)["status"]


def config(env, old, new):
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace(old, new))


# ---------- costo honesto ----------
def test_codex_shows_unpriced_tokens_instead_of_zero_dollars(env):
    env.mode("noop", "ok", "noop")
    feature(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    status = env.umbra("status").output  # $… + 60 tokens
    assert "60 tokens" in status and "sin precio" not in status
    raw = env.umbra("evidence", "1", "--raw").output
    assert "60 tokens" in raw and "$0.00" not in raw and "sin precio" not in raw
    shown = env.umbra("evidence", "1").output
    assert "60 tokens" in shown and "sin precio" not in shown
    assert json.loads(env.umbra("metrics", "--json").output)["summary"]["unpriced_tokens"] == 60


# ---------- avisos ----------
def test_desktop_alert_when_a_task_needs_you(env, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda title, body: sent.append((title, body)))
    config(env, "desktop = false", "desktop = true")
    env.mode("noop", "ok", "noop")
    feature(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    assert sent == [("umbra · tarea 1", "Sumar: espera tu aprobación.")]


def test_alerts_off_by_config(env, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda *a: sent.append(a))
    env.mode("noop", "ok", "noop")
    feature(env)
    run_feature(env)
    assert sent == []


def test_notify_never_fires_under_pytest(monkeypatch):
    launched = []
    monkeypatch.setattr(notify.subprocess, "Popen", lambda *a, **k: launched.append(a))
    notify.send("t", "b")
    assert launched == []


def test_windows_toast_escapes_text():
    cmd = notify.command("umbra · tarea 1", "a <b> & 'c'", platform="win32")
    assert "a &lt;b&gt; &amp; &#x27;c&#x27;" in cmd[-1]  # el texto no puede romper el XML


# ---------- piloto automático ----------
def test_autopilot_starts_the_next_accepted_task_after_merge(env, monkeypatch):
    config(env, "[autopilot]\nenabled = false", "[autopilot]\nenabled = true")
    env.mode("noop", "ok", "noop")
    feature(env)
    feature(env, "Restar")
    env.umbra("task", "deps", "2", "--on", "1")
    assert run_feature(env) == "WAITING_APPROVAL"
    monkeypatch.setattr(service, "dispatch", lambda root, foreground: None)  # solo encolar
    out = env.umbra("approve", "1", input="y\n").output
    assert "la tarea 2 arrancó sola" in out
    second = env.run(2)
    assert second["status"] == "QUEUED"
    origin = env.conn.execute("SELECT origin FROM event WHERE run_id = ? AND type = 'run.queued'",
                              (second["id"],)).fetchone()[0]
    assert origin == "autopilot"


def test_autopilot_leaves_stopped_tasks_and_drafts_alone(env, monkeypatch):
    config(env, "[autopilot]\nenabled = false", "[autopilot]\nenabled = true")
    env.mode("noop", "ok", "noop")
    feature(env)
    env.umbra("task", "add", "Borrador", "--draft")
    assert run_feature(env) == "WAITING_APPROVAL"
    monkeypatch.setattr(service, "dispatch", lambda root, foreground: None)
    assert "arrancó sola" not in env.umbra("approve", "1", input="y\n").output


# ---------- decidir sobre hallazgos ----------
def blocked_by_review(env):
    env.mode("noop", "ok", "ok", "ok", "noop")
    env.codex_mode("high:no valida negativos", "high:no valida negativos",
                   "high:no valida negativos", "clean")
    feature(env)
    assert run_feature(env) == "BLOCKED"


def test_waived_finding_lets_the_task_continue_without_another_review(env):
    blocked_by_review(env)
    listed = env.umbra("finding", "list", "1").output
    assert "no valida negativos" in listed
    out = env.umbra("finding", "waive", "1", "-m", "fuera de alcance").output
    assert "seguirá desde verify" in out
    env.umbra("retry", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    assert [s for s, _ in env.attempts()][-2:] == ["verify", "scan"]
    assert len(env.codex_calls()) == 3  # no se volvió a revisar
    decided = env.conn.execute("SELECT payload FROM event WHERE type = 'finding.decided'"
                               ).fetchone()[0]
    assert json.loads(decided)["reason"] == "fuera de alcance"


def test_reviewer_is_told_what_was_waived(env):
    blocked_by_review(env)
    env.umbra("finding", "waive", "1", "-m", "no aplica")
    env.umbra("retry", "1", "--from", "review", "--foreground")
    prompt = env.codex_calls()[3]["prompt"]
    assert "sobre estos hallazgos; no los vuelvas a reportar" in prompt
    assert '"findings": []' in prompt  # sus repeticiones de rondas anteriores tampoco cuentan


def test_deferred_finding_becomes_a_draft_task(env):
    blocked_by_review(env)
    out = env.umbra("finding", "defer", "1").output
    assert "Tareas en borrador con lo pendiente: 2" in out
    task = env.conn.execute("SELECT title, status, about FROM task WHERE number = 2").fetchone()
    assert task["status"] == "draft" and "no valida negativos" in task["title"]
    assert service.pending_findings(service.load(env.root), 1) == []


def test_findings_decisions_need_a_person(env, monkeypatch):
    blocked_by_review(env)
    monkeypatch.setattr(service, "interactive", lambda: False)
    result = env.umbra("finding", "waive", "1", "-m", "x", ok=False)
    assert result.exit_code == 3


def test_nothing_to_decide_when_not_blocked_by_findings(env):
    feature(env)
    assert env.umbra("finding", "waive", "1", "-m", "x", ok=False).exit_code != 0


def test_watch_decides_a_finding_with_h(env):
    blocked_by_review(env)

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.2)
        async with app.run_test() as pilot:
            await pilot.pause(0.3)
            await pilot.press("h")
            await pilot.pause(0.2)
            await pilot.press("enter")  # el único hallazgo
            await pilot.pause(0.2)
            await pilot.press("enter")  # «No aplica»
            await pilot.pause(0.2)
            await pilot.press("enter")  # motivo por defecto
            await pilot.pause(1.0)
            await pilot.press("q")

    asyncio.run(scenario())
    status = env.conn.execute("SELECT status FROM finding WHERE message LIKE '%negativos%'"
                              " ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    assert status == "waived"


def test_cost_shows_tokens_without_price_label(env):
    env.mode("noop", "ok", "noop")
    feature(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    for out in (env.umbra("status").output, env.umbra("evidence", "1", "--raw").output,
                env.umbra("evidence", "1").output):
        assert "60 tokens" in out and "sin precio" not in out and "$0.00" not in out
