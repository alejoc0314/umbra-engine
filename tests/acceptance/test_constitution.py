"""La constitución en el ciclo y las specs retroactivas (spec 030)."""

from tests.acceptance.test_telegram import poll, state
from tests.acceptance.test_telegram_console import texts, wait
from tests.conftest import git
from umbra.chat import elicit

CONSTITUTION = "# Repo Constitution\n\n### 1. Tests\n\nToda funcion MUST tener test.\n"


def with_constitution(env, commit=True):
    c = env.root / ".specify" / "memory" / "constitution.md"
    c.parent.mkdir(parents=True, exist_ok=True)
    c.write_text(CONSTITUTION, encoding="utf-8")
    base = env.root / "specs" / "000-linea-base"
    base.mkdir(parents=True, exist_ok=True)
    (base / "linea-base.md").write_text("- test: FALLA test_viejo (ya fallaba)\n", encoding="utf-8")
    if commit:
        git(env.root, "add", ".specify", "specs")
        git(env.root, "commit", "-q", "-m", "constitucion")
    return c


def test_every_agent_gets_the_constitution_and_the_baseline(env):
    with_constitution(env)
    env.mode("ok")
    env.umbra("task", "add", "Sumar", "-a", "add(2, 3) == 5")
    env.umbra("run", "1", "--foreground")
    prompt = env.claude_calls()[0]["prompt"]
    assert "Toda funcion MUST tener test" in prompt and "ya fallaba" in prompt


def test_specs_document_how_it_works_today_after_onboarding(tmp_path):
    assert elicit.phase_message("specify", "pagos", root=tmp_path) == "/speckit-specify pagos"
    (tmp_path / "specs" / "000-linea-base").mkdir(parents=True)
    msg = elicit.phase_message("specify", "pagos", root=tmp_path)
    assert msg.startswith("/speckit-specify pagos") and "Cómo funciona hoy" in msg
    assert elicit.phase_message("plan", "pagos", root=tmp_path) == "/speckit-plan"


def test_amend_from_the_terminal_approve_and_discard(env):
    c = with_constitution(env)
    env.mode("amend", "amend")
    out = env.umbra("constitucion", "enmendar", "las APIs llevan test de contrato",
                    input="y\n").output
    assert "+### 2. Contratos" in out and "Enmienda aprobada" in out
    assert "enmienda de la constituci" in git(env.root, "log", "-1", "--format=%s").stdout
    assert "Contratos" in c.read_text(encoding="utf-8")
    out = env.umbra("constitucion", "enmendar", "otra vez", input="n\n").output
    assert "descartada" in out and c.read_text(encoding="utf-8").count("Contratos") == 1
    assert "Toda funcion MUST" in env.umbra("constitucion", "ver").output


def test_amend_may_only_touch_the_constitution(env):
    with_constitution(env)
    (env.root / "CONTEXT.md").write_text("original\n", encoding="utf-8")
    git(env.root, "add", "CONTEXT.md")
    git(env.root, "commit", "-q", "-m", "ctx")
    env.mode("amend_stray")
    result = env.umbra("constitucion", "enmendar", "algo", ok=False)
    assert result.exit_code != 0 and "CONTEXT.md" in result.output
    assert (env.root / "CONTEXT.md").read_text(encoding="utf-8") == "original\n"


def test_without_constitution_umbra_says_how_to_get_one(env):
    out = env.umbra("constitucion", "ver", ok=False).output
    assert "umbra onboard" in out


def test_amend_from_the_phone(env, tg):
    with_constitution(env)
    env.mode("amend")
    st = state(env)
    tg.say("/constitucion")
    poll(env, tg, st)
    assert tg.uploads[-1][0] == "sendDocument"
    tg.say("/enmendar las APIs llevan test de contrato")
    poll(env, tg, st)
    wait(lambda: any("Enmienda propuesta" in t for t in texts(tg)))
    keys = [b["callback_data"] for row in tg.sent[-1]["reply_markup"]["inline_keyboard"]
            for b in row]
    assert keys == ["ce:approve@repo", "ce:discard@repo"]
    tg.tap("ce:approve@repo")
    poll(env, tg, st)
    assert "Enmienda aprobada" in tg.sent[-1]["text"]
    assert "enmienda de la constituci" in git(env.root, "log", "-1", "--format=%s").stdout
