"""Crítica, revisiones automáticas, direcciones y gusto (spec 027)."""

from tests.acceptance.test_design import install_pack
from tests.acceptance.test_e2 import feature_task, run_feature
from tests.acceptance.test_telegram import poll, state
from tests.acceptance.test_watch_actions import sync_worker
from umbra import service
from umbra.management import taste


def blocked(env):
    return service._blocked_payload(service.load(env.root), env.run())


def test_critic_sends_the_design_back_until_it_is_clean(env):
    install_pack()
    env.mode("plan_ui", "design", "critique", "design", "noop")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    assert [s for s, _ in env.attempts()] == ["plan", "design", "critic", "design", "critic"]
    critic = env.claude_calls()[2]
    assert "design/png/pantalla-1.png" in critic["prompt"]  # mira las pantallas del diseñador
    assert "Edit" not in critic["args"][critic["args"].index("--allowedTools") + 1]
    assert "el texto del boton se corta" in env.claude_calls()[3]["prompt"]
    payload = blocked(env)
    assert payload["code"] == "design_review" and payload["details"]["pending"] == []
    assert env.conn.execute("SELECT COUNT(*) FROM finding").fetchone()[0] == 0  # no van a código


def test_the_designers_own_checks_count_too(env):
    install_pack()
    env.mode("plan_ui", "design_lint", "noop", "design", "noop")
    feature_task(env)
    run_feature(env)
    assert "contraste 2.1:1" in env.claude_calls()[3]["prompt"]


def test_after_the_cycles_the_person_decides_with_what_is_pending(env, tg):
    install_pack()
    env.mode("plan_ui", "design", "critique", "design", "critique", "design", "critique")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    assert [s for s, _ in env.attempts()].count("design") == 3  # max_fix_cycles = 2
    payload = blocked(env)
    assert payload["code"] == "design_review"
    assert "el texto del boton se corta" in payload["details"]["pending"][0]
    assert "El crítico todavía ve" in tg.sent[-1]["text"]


def test_directions_are_chosen_by_the_person_and_shape_the_taste(env, tg):
    install_pack()
    sync_worker(env)
    env.mode("plan_ui", "design_options", "design", "noop", "design", "noop", "ok", "noop")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    # sin dirección visual aún, el sobre del diseñador le pide proponer varias
    assert "direcciones claramente distintas" in env.claude_calls()[1]["prompt"]
    payload = blocked(env)
    assert payload["code"] == "design_choice"
    assert [o["name"] for o in payload["details"]["options"]] == ["Calida", "Nocturna",
                                                                  "Editorial"]
    albums = [u for u in tg.uploads if u[0] in ("sendPhoto", "sendMediaGroup")]
    assert len(albums) == 3  # una foto (o álbum) por dirección
    keys = [b["callback_data"] for row in tg.sent[-1]["reply_markup"]["inline_keyboard"]
            for b in row]
    assert keys == ["dpick:1:1@repo", "dpick:1:2@repo", "dpick:1:3@repo"]

    st = state(env)
    tg.tap("dpick:1:2@repo")
    poll(env, tg, st)
    assert "Nocturna" in tg.sent[-2]["text"] or "Nocturna" in tg.sent[-1]["text"]
    designer = env.claude_calls()[2]["prompt"]
    assert "Nocturna" in designer and "direcciones claramente distintas" not in designer
    assert "Elegiste la direcci" in designer  # el gusto ya viaja en el sobre del diseñador
    assert blocked(env)["code"] == "design_review"
    decision = next(m for m in reversed(tg.sent) if "espera tu visto bueno" in m["text"])
    tg.say("menos sombras", reply_to=decision["text"])
    poll(env, tg, st)
    tg.tap("dok:1@repo")
    poll(env, tg, st)
    assert env.run()["status"] == "WAITING_APPROVAL"
    likes = taste.load()
    assert "«Nocturna» frente a «Calida», «Editorial»" in likes
    assert "Pediste en «Sumar correctamente»: menos sombras" in likes
    assert "tras 1 ronda(s) de cambios" in likes
    tg.say("/gusto")
    poll(env, tg, st)
    assert "Nocturna" in tg.sent[-1]["text"]


def test_cli_picks_a_direction_and_shows_the_taste(env):
    install_pack()
    sync_worker(env)
    env.mode("plan_ui", "design_options", "design", "noop")
    feature_task(env)
    run_feature(env)
    no = env.umbra("design", "elegir", "1", "7", ok=False)
    assert no.exit_code != 0 and "entre 1 y 3" in no.output
    assert "Editorial" in env.umbra("design", "elegir", "1", "3").output
    assert blocked(env)["code"] == "design_review"
    assert "Editorial" in env.umbra("design", "gusto").output
