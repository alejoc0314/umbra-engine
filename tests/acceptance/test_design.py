"""Diseñar antes de construir (spec 026): paquetes, MCP declarado en el perfil y la etapa
Diseñar con el visto bueno de la persona."""

import json
import os
import subprocess
from pathlib import Path

from tests.acceptance.test_e2 import feature_task, run_feature
from tests.acceptance.test_telegram import poll, state
from tests.acceptance.test_watch_actions import sync_worker
from umbra import service
from umbra.unified import config as cfg

DESIGNER = """name = "designer"
agent = "claude-code"
roles = ["design"]
actions = ["read", "edit"]
allowed_paths = ["design/**"]

[mcp.lienzo]
command = "lienzo"
args = ["--no-app", "--skills-dir", "{profile_dir}/estilos", "--root", "{workspace}"]
env = { MODO = "agente" }
"""


def install_pack(name="equipo") -> Path:
    """Un paquete instalado en ~/.umbra/packs con el perfil del diseñador."""
    pack = Path(os.environ["UMBRA_HOME"]) / "packs" / name
    (pack / "profiles").mkdir(parents=True)
    (pack / "profiles" / "designer.toml").write_text(DESIGNER, encoding="utf-8")
    return pack


def flag(args, name):
    return args[args.index(name) + 1]


def test_without_designer_or_without_ui_the_stage_is_skipped(env):
    env.mode("plan_ui", "ok", "noop")  # toca la interfaz, pero el perfil no existe
    routines = env.root / ".umbra" / "routines"
    routines.mkdir(exist_ok=True)
    (routines / "feature.yaml").write_text(
        (cfg.DEFAULTS / "routines" / "feature.yaml").read_text(encoding="utf-8")
        .replace("profile: designer", "profile: nadie"), encoding="utf-8")
    feature_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    assert [s for s, _ in env.attempts()] == ["plan", "build", "review", "verify", "scan"]
    skipped = env.conn.execute("SELECT payload FROM event WHERE type = 'design.skipped'"
                               ).fetchone()
    assert "no hay diseñador" in json.loads(skipped[0])["reason"]


def test_task_without_ui_skips_the_designer_even_if_installed(env):
    install_pack()
    env.mode("noop", "ok", "noop")
    feature_task(env)
    assert run_feature(env) == "WAITING_APPROVAL"
    assert "design" not in [s for s, _ in env.attempts()]


def test_design_waits_for_approval_then_build_follows_it(env, tg):
    pack = install_pack()
    sync_worker(env)  # lo que se encola desde el teléfono corre aquí mismo
    env.mode("plan_ui", "design", "noop", "design", "noop", "ok", "noop")  # noop: el crítico
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    call = env.claude_calls()[1]  # el diseñador, con el MCP que declara su perfil
    servers = json.loads(flag(call["args"], "--mcp-config"))["mcpServers"]
    assert servers["lienzo"]["args"][2] == f"{(pack / 'profiles').as_posix()}/estilos"
    assert servers["lienzo"]["args"][4] == Path(call["cwd"]).as_posix()
    assert servers["lienzo"]["env"] == {"MODO": "agente"} and "--strict-mcp-config" in call["args"]
    assert "mcp__lienzo" in flag(call["args"], "--allowedTools")
    assert "Edit(design/**)" in flag(call["args"], "--allowedTools")
    photos = [u for u in tg.uploads if u[0] in ("sendPhoto", "sendMediaGroup")]
    assert photos  # las pantallas llegan al teléfono antes de la pregunta
    decision = tg.sent[-1]
    assert "espera tu visto bueno" in decision["text"]
    keys = [b["callback_data"] for row in decision["reply_markup"]["inline_keyboard"]
            for b in row]
    assert keys == ["dok:1@repo"]

    st = state(env)  # responder al mensaje = pedir cambios
    tg.say("mas contraste en el boton", reply_to=decision["text"])
    poll(env, tg, st)
    assert env.run()["status"] == "BLOCKED"  # segunda versión, otra vez a tu visto bueno
    assert "mas contraste en el boton" in env.claude_calls()[3]["prompt"]
    tg.tap("dok:1@repo")
    poll(env, tg, st)
    assert env.run()["status"] == "WAITING_APPROVAL"
    stages = [s for s, _ in env.attempts()]
    assert stages == ["plan", "design", "critic", "design", "critic", "build", "review",
                      "verify", "scan"]
    build = env.claude_calls()[5]["prompt"]
    assert "aprobado por la persona" in build and "design/png/pantalla-2.png" in build
    assert "design/png/pantalla-2.png" in env.claude_calls()[6]["prompt"]  # el verificador
    assert "design/png/pantalla-1.png" in json.loads(
        env.conn.execute("SELECT payload FROM event WHERE type = 'design.ready'").fetchone()[0]
    )["images"]


def test_designer_may_only_touch_the_design_folder(env):
    install_pack()
    env.mode("plan_ui", "design_code")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    ctx = service.load(env.root)
    blocked = service._blocked_payload(ctx, env.run())
    assert blocked["code"] == "design_outside" and blocked["details"]["files"] == ["calc.py"]


def test_cli_approves_and_asks_changes(env):
    install_pack()
    sync_worker(env)
    env.mode("plan_ui", "design", "noop", "design", "noop", "ok", "noop")
    feature_task(env)
    run_feature(env)
    out = env.umbra("design", "cambios", "1", "menos texto").output
    assert "cambios pedidos" in out
    assert env.run()["status"] == "BLOCKED"
    env.umbra("design", "ok", "1")
    assert env.run()["status"] == "WAITING_APPROVAL"
    assert "Maquetado sobre el diseño" in env.umbra("evidence", "1").output
    no = env.umbra("design", "ok", "1", ok=False)
    assert no.exit_code != 0 and "no tiene un diseño esperando" in no.output


def test_packs_add_profiles_and_playbooks_after_the_project(env, tmp_path):
    pack = install_pack()
    (pack / "playbooks" / "flutter").mkdir(parents=True)
    (pack / "playbooks" / "flutter" / "playbook.toml").write_text('test = "flutter test"\n')
    udir = env.root / ".umbra"
    assert cfg.load_profile(udir, "designer").source.parent == pack / "profiles"
    (udir / "profiles").mkdir(exist_ok=True)
    (udir / "profiles" / "designer.toml").write_text(DESIGNER.replace("lienzo", "otro"))
    assert cfg.load_profile(udir, "designer").source.parent == udir / "profiles"  # el proyecto gana
    out = env.umbra("pack", "list").output
    assert "equipo" in out and "designer" in out and "flutter" in out
    from umbra.management import packs, playbooks
    assert "flutter" in playbooks.available()
    assert packs.name_from("git@github.com:equipo/umbra-equipo.git") == "umbra-equipo"
    source = tmp_path / "origen"
    source.mkdir()
    os.system(f'git init -q "{source}" && git -C "{source}" commit -q --allow-empty -m x')
    what, dest = packs.sync(source.as_posix(), "nuevo")
    assert what == "clonado" and (dest / ".git").is_dir()
    assert packs.sync(source.as_posix(), "nuevo")[0] == "actualizado"


def test_standard_designer_renders_mockups_and_takes_your_tool_and_guides(env):
    guide = env.root.parent / "guia-equipo.md"
    guide.write_text("Usa la libreria del equipo: botones de 48 px.\n", encoding="utf-8")
    cfg_file = env.root / ".umbra" / "project.toml"
    cfg_file.write_text(cfg_file.read_text(encoding="utf-8") + (
        f'\n[design]\nguides = ["{guide.as_posix()}", "no-existe.md"]\n\n'
        '[design.mcp.lienzo]\ncommand = "lienzo"\nargs = ["--sin-ventana"]\n'), encoding="utf-8")
    env.mode("plan_ui", "design", "noop")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    designer, critic = env.claude_calls()[1], env.claude_calls()[2]
    servers = json.loads(flag(designer["args"], "--mcp-config"))["mcpServers"]
    assert servers["lienzo"] == {"command": "lienzo", "args": ["--sin-ventana"]}  # tu herramienta
    shots = servers["playwright"]["args"]  # y el navegador para las maquetas HTML
    assert "--allow-unrestricted-file-access" in shots
    assert flag(shots, "--output-dir") == f"{Path(designer['cwd']).as_posix()}/design/png"
    assert ("--browser" in shots) == (os.name == "nt")  # Edge en Windows
    assert "--model" in designer["args"] and flag(designer["args"], "--model") == "claude-opus-5-5"
    for call in (designer, critic):
        assert "botones de 48 px" in call["prompt"]  # la guía viaja al diseñador y al crítico


def test_starter_file_is_copied_once_into_design(env):
    starter = env.root.parent / "kit.lienzo"
    starter.write_text('{"kit": 1}', encoding="utf-8")
    cfg_file = env.root / ".umbra" / "project.toml"
    cfg_file.write_text(cfg_file.read_text(encoding="utf-8")
                        + f'\n[design]\nstarter = "{starter.as_posix()}"\n', encoding="utf-8")
    sync_worker(env)
    env.mode("plan_ui", "design", "noop", "design", "noop")
    feature_task(env)
    assert run_feature(env) == "BLOCKED"
    wt = Path(env.run()["worktree"])
    copy = wt / "design" / "repo.lienzo"
    assert copy.read_text(encoding="utf-8") == '{"kit": 1}'
    assert "design/repo.lienzo" in subprocess.run(["git", "ls-files"], cwd=wt, capture_output=True,
                                                  text=True).stdout  # va con el diseño
    copy.write_text('{"kit": 1, "pantallas": 2}', encoding="utf-8")  # el diseñador trabajó encima
    env.umbra("design", "cambios", "1", "otra vuelta")
    assert copy.read_text(encoding="utf-8") == '{"kit": 1, "pantallas": 2}'  # no se pisa
    assert env.conn.execute("SELECT COUNT(*) FROM event WHERE type = 'design.starter'"
                            ).fetchone()[0] == 1
