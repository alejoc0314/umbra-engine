"""CONTEXT.md (cartógrafo), revisor de respaldo y el panel «Aprendido» de watch (spec 015)."""

import asyncio
import json

from tests.conftest import git
from umbra import service
from umbra.cli.watch import WatchApp


def feature(env):
    env.plain_routine()  # sin escalada ni árbitro: aquí los hallazgos deben detener
    cfg = env.root / ".umbra" / "project.toml"
    cfg.write_text(cfg.read_text().replace('default_routine = "quick"',
                                           'default_routine = "feature"'))
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")


def test_context_build_writes_and_commits_only_context_md(env):
    env.mode("context")
    before = git(env.root, "rev-parse", "HEAD").stdout.strip()
    out = json.loads(env.umbra("context", "build", "--json").output)
    assert out["changed"] is True
    assert (env.root / "CONTEXT.md").read_text().startswith("<!-- umbra:inicio -->")
    assert git(env.root, "rev-parse", "HEAD").stdout.strip() != before
    assert git(env.root, "status", "--porcelain", "--untracked-files=no").stdout == ""
    call = env.claude_calls()[-1]
    tools = call["args"][call["args"].index("--allowedTools") + 1]
    assert "Edit(CONTEXT.md)" in tools and "Edit," not in tools  # solo ese archivo
    env.mode("noop")  # sin cambios: no hay commit nuevo
    head = git(env.root, "rev-parse", "HEAD").stdout.strip()
    assert json.loads(env.umbra("context", "build", "--json").output)["changed"] is False
    assert git(env.root, "rev-parse", "HEAD").stdout.strip() == head


def test_context_build_restores_anything_else_the_agent_touched(env):
    env.mode("touch")  # escribe intruso.txt
    result = env.umbra("context", "build", ok=False)
    assert "intruso.txt" in result.output
    assert not (env.root / "intruso.txt").exists()
    assert env.conn.execute("SELECT COUNT(*) FROM event WHERE type = 'context.failed'"
                            ).fetchone()[0] == 1


def test_agents_receive_the_repo_map_in_their_envelope(env):
    (env.root / "CONTEXT.md").write_text(
        "<!-- umbra:inicio -->\n## Qué es\nCalc.\n<!-- umbra:fin -->\n")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    prompt = env.claude_calls()[-1]["prompt"]
    assert "Mapa del repositorio" in prompt and "Calc." in prompt


def test_review_falls_back_to_claude_when_codex_fails(env):
    cfg = env.root / ".umbra" / "project.toml"  # la rutina feature por defecto (con respaldo)
    cfg.write_text(cfg.read_text().replace('default_routine = "quick"',
                                           'default_routine = "feature"'))
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.codex_mode("error")
    env.mode("noop", "ok", "noop", "ok", "noop")  # plan, build, review (Claude), verify, resumen
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "WAITING_APPROVAL"
    attempts = env.attempts()
    assert ("review", "error") in attempts and ("review", "done") in attempts
    agents = [r[0] for r in env.conn.execute(
        "SELECT agent FROM attempt WHERE stage = 'review' ORDER BY started_at")]
    assert agents == ["codex", "claude-code"]
    event = json.loads(env.conn.execute("SELECT payload FROM event WHERE type = 'stage.fallback'"
                                        ).fetchone()[0])
    assert event["profile"] == "reviewer-claude"
    assert "en su lugar" in env.umbra("log", "1").output


def test_watch_m_shows_what_umbra_learned(env):
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    (env.root / ".umbra" / "aprendido.md").write_text("# Aprendido\n\n- no validar x\n",
                                                      encoding="utf-8")

    async def scenario():
        app = WatchApp(env.root / ".umbra", interval=0.2)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("m")
            for _ in range(30):
                await pilot.pause(0.1)
                if app.tab == "memory" and app._shown_extra.get("memory"):
                    break
            assert app.tab == "memory"
            assert "no validar x" in app._shown_extra["memory"][1]
            await pilot.press("q")

    asyncio.run(scenario())


def test_memory_is_rebuilt_after_each_decision(env):
    feature(env)
    env.codex_mode("high:falta validar entradas")
    env.mode("noop", "ok", "ok", "ok", "ok", "noop")
    env.umbra("run", "1", "--foreground")
    assert env.run()["status"] == "BLOCKED"
    env.umbra("finding", "waive", "1", "-m", "no aplica aquí")
    learned = (env.root / ".umbra" / "aprendido.md").read_text(encoding="utf-8")
    assert "falta validar entradas" in learned and "no aplica aquí" in learned
    assert service.load().conn is not None
