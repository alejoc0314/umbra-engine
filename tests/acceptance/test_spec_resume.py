import json

from umbra import service
from umbra.blocks import lease
from umbra.cli.spec_screen import SpecApp
from umbra.cli.watch import PickOne
from umbra.unified.store import new_id, now

from .test_spec_conversation import SPEC, install_flow, pick, review, run, until

EDITED = SPEC.replace("Texto uno.", "Texto uno, reescrito.")


def _clarify_session(env):
    """Cierra la pantalla con la conversación detenida en `clarify` (pregunta sin responder)."""
    async def scenario(pilot, app):
        # esperar a que la pregunta termine de montarse: cerrar antes rompe PickOne.on_mount
        await until(pilot, lambda: isinstance(app.screen, PickOne)
                    and app.screen.query("#options"), "pregunta")

    run(env, scenario)
    row = env.conn.execute("SELECT * FROM conversation").fetchone()
    assert row["phase"] == "clarify"
    return row


def _resume(env, row, scenario):
    import asyncio
    exe = install_flow(env)

    async def go():
        app = SpecApp(service.load(), row["idea"], exe=exe, conv_id=row["id"])
        async with app.run_test() as pilot:
            await scenario(pilot, app)
        return app

    return asyncio.run(go())


def _tasks(env, spec=SPEC):
    folder = env.root / "specs" / "001-x"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "spec.md").write_text(spec, encoding="utf-8")
    env.umbra("spec", "tasks", "specs/001-x")
    return folder


def _row(env, n):
    return dict(env.conn.execute("SELECT * FROM task WHERE number = ?", (n,)).fetchone())


def test_resume_vuelve_a_la_misma_fase_con_su_historial(env):
    row = _clarify_session(env)
    seen = {}

    async def scenario(pilot, app):
        await until(pilot, lambda: app.lines, "historial")
        seen["lines"] = list(app.lines)
        await until(pilot, lambda: not app.query_one("#entry").disabled, "entrada")

    _resume(env, row, scenario)
    assert seen["lines"][0] == "Tú: una idea" and len(seen["lines"]) > 1
    assert env.conn.execute("SELECT phase FROM conversation").fetchone()["phase"] == "clarify"
    assert (env.root / ".umbra" / "artifacts" / f"{row['id']}.jsonl").is_file()


def test_resume_retoma_con_el_session_id(env):
    row = _clarify_session(env)

    async def scenario(pilot, app):
        await until(pilot, lambda: not app.query_one("#entry").disabled, "entrada")
        await pilot.press(*"1000", "enter")
        await until(pilot, lambda: len(env.claude_calls()) > 1, "turno")

    _resume(env, row, scenario)
    last = env.claude_calls()[-1]
    assert last["args"][last["args"].index("--resume") + 1] == row["session_id"]


def test_resume_en_revision_reabre_el_punto_de_control(env):
    async def scenario(pilot, app):
        await until(pilot, lambda: isinstance(app.screen, PickOne), "pregunta")
        await pick(pilot, app, 0)
        await review(pilot, app, env, "spec_review")

    run(env, scenario)
    row = env.conn.execute("SELECT * FROM conversation").fetchone()

    async def again(pilot, app):
        await review(pilot, app, env, "spec_review")

    _resume(env, row, again)


def test_resume_elige_ultima_abierta_por_numero_y_ruta(env):
    old = new_id()
    ts = now()
    env.conn.execute(
        "INSERT INTO conversation (id, idea, spec_dir, phase, origin, created_at, updated_at)"
        " VALUES (?, 'a', 'specs/001-x', 'plan', 'spec', ?, ?)", (old, ts, ts))
    done = new_id()
    env.conn.execute(
        "INSERT INTO conversation (id, idea, spec_dir, phase, origin, created_at, updated_at)"
        " VALUES (?, 'b', 'specs/002-y', 'done', 'spec', ?, '9999')", (done, ts))
    ctx = service.load()
    assert service.spec_resume_target(ctx, None)["id"] == old
    assert service.spec_resume_target(ctx, "001")["id"] == old
    assert service.spec_resume_target(ctx, "specs/001-x")["id"] == old
    for ref in ("002", "specs/002-y", "009"):
        try:
            service.spec_resume_target(ctx, ref)
        except service.OpError as e:
            assert e.code == 2
        else:
            raise AssertionError(ref)


def test_con_el_lease_ocupado_la_segunda_pantalla_explica(env):
    row = _clarify_session(env)
    assert lease.acquire(env.conn, f"spec:{row['id']}", "otra-persona@1")
    result = env.umbra("spec", "resume", ok=False)
    assert result.exit_code != 0
    assert "otra-persona@1" in result.output and "otra pantalla" in result.output


def test_historia_editada_marca_la_tarea_desalineada(env):
    folder = _tasks(env)
    ctx = service.load()
    assert service.misaligned(ctx, folder) == []
    (folder / "spec.md").write_text(EDITED, encoding="utf-8")
    stale = service.misaligned(ctx, folder)
    assert [(m["number"], m["story"], m["updatable"]) for m in stale] == [(1, "US1", True)]


def test_actualizar_con_yes_aplica(env):
    folder = _tasks(env)
    (folder / "spec.md").write_text(EDITED, encoding="utf-8")
    result = env.umbra("spec", "tasks", "specs/001-x", "--yes", "--json")
    assert json.loads(result.output)["updated"] == [1]
    assert "reescrito" in _row(env, 1)["description"]
    assert service.misaligned(service.load(), folder) == []


def test_rechazar_la_actualizacion_no_cambia_nada(env):
    folder = _tasks(env)
    (folder / "spec.md").write_text(EDITED, encoding="utf-8")
    before = _row(env, 1)
    result = env.umbra("spec", "tasks", "specs/001-x", input="n\n")
    assert result.exit_code == 0 and _row(env, 1) == before
    env.umbra("spec", "tasks", "specs/001-x", input="y\n")
    assert "reescrito" in _row(env, 1)["description"]


def test_tarea_en_ejecucion_no_se_modifica(env):
    folder = _tasks(env)
    task = _row(env, 1)
    env.conn.execute(
        "INSERT INTO run (id, task_id, routine, status, base_sha, branch, idempotency_key,"
        " created_at, updated_at) VALUES (?, ?, 'quick', 'RUNNING', 'x', 'b', 'k', ?, ?)",
        (new_id(), task["id"], now(), now()))
    env.conn.execute("UPDATE task SET status = 'dropped' WHERE number = 2")
    (folder / "spec.md").write_text(
        EDITED.replace("Texto dos.", "Texto dos, nuevo."), encoding="utf-8")
    before = {n: _row(env, n) for n in (1, 2)}
    result = env.umbra("spec", "tasks", "specs/001-x", "--yes", "--json")
    data = json.loads(result.output)
    assert data["updated"] == [] and sorted(s["number"] for s in data["skipped"]) == [1, 2]
    assert {n: _row(env, n) for n in (1, 2)} == before


def test_confirmacion_muestra_que_cambia_aunque_el_titulo_sea_igual(env):
    folder = _tasks(env)
    (folder / "spec.md").write_text(EDITED, encoding="utf-8")
    stale = service.misaligned(service.load(), folder)[0]
    assert stale["title"] == stale["new_title"]
    assert "description" in stale["changes"]
    out = env.umbra("spec", "tasks", "specs/001-x", input="n\n").output
    assert "description" in out and "reescrito" in out
    data = json.loads(env.umbra("spec", "tasks", "specs/001-x", "--json").output)
    assert "description" in data["misaligned"][0]["changes"]
