import shutil
import sys
from decimal import Decimal

import pytest

from tests.unit.test_stream import fake_claude
from umbra import service
from umbra.chat import elicit
from umbra.chat.stream import Stream
from umbra.unified.store import open_store

D = Decimal


@pytest.fixture
def conn(tmp_path):
    udir = tmp_path / ".umbra"
    udir.mkdir()
    return open_store(udir)


def run_flow(tmp_path, monkeypatch, conn, effects=None, max_cost=D(5)):  # noqa: B008
    exe = fake_claude(tmp_path, monkeypatch, effects=effects)
    cid = elicit.new_conversation(conn, "una idea")
    results = []
    with Stream(tmp_path, exe=exe) as s:
        results.append(elicit.run_turn(
            conn, tmp_path, cid, s, elicit.phase_message("specify", "una idea"), max_cost))
        elicit.advance(conn, cid)  # → clarify
        results.append(elicit.run_turn(
            conn, tmp_path, cid, s, elicit.phase_message("clarify"), max_cost))
        elicit.advance(conn, cid)  # → spec_review
    return cid, results


def test_recorrido_specify_a_spec_review(tmp_path, monkeypatch, conn):
    cid, (r1, r2) = run_flow(tmp_path, monkeypatch, conn)
    row = conn.execute("SELECT * FROM conversation WHERE id = ?", (cid,)).fetchone()
    assert row["phase"] == "spec_review" and row["session_id"] == "sess-1"
    assert r1.cost == D("0.10") and r2.cost == D("0.15")  # acumulado − cost_seen
    assert D(row["cost_seen"]) == D("0.25")
    assert elicit.spent(conn, cid) == D("0.25")
    assert r2.question and r2.question.options == ["10", "1000"] and r2.question.recommended == 0
    assert "umbra-question" not in r2.text


def test_phase_settings_por_fase():
    spec = elicit.phase_settings("specify", "ps")["permissions"]["allow"]
    assert "PowerShell(.specify/scripts/**)" in spec and "Write(specs/*/spec.md)" in spec
    assert "Write(.specify/feature.json)" in spec and "Read" in spec
    plan_sh = elicit.phase_settings("plan", "sh")["permissions"]["allow"]
    assert "Bash(.specify/scripts/**)" in plan_sh
    assert "Write(specs/*/contracts/*)" in elicit.phase_settings("plan")["permissions"]["allow"]
    assert "Write(specs/*/tasks.md)" in elicit.phase_settings("tasks")["permissions"]["allow"]
    review = elicit.phase_settings("spec_review")["permissions"]["allow"]
    assert not [a for a in review if a.startswith(("Write(specs", "Edit(specs"))]


def test_transiciones():
    assert elicit.next_phase("spec_review", "approve") == "plan"
    assert elicit.next_phase("plan_review", "changes") == "plan"
    assert elicit.next_phase("plan", "discard") == "discarded"
    with pytest.raises(ValueError):
        elicit.next_phase("specify", "approve")
    assert elicit.phase_message("tasks") == "/speckit-tasks"
    assert elicit.phase_message("plan", comment="más corto") == "Cambios pedidos: más corto"


def block(payload):
    return f"Hola\n```umbra-question\n{payload}\n```\n"


def test_parse_question():
    text, q = elicit.parse_question(block('{"question": "¿A?", "options": ["a", "b"], '
                                         '"recommended": 1}'))
    assert q.recommended == 1 and text == "Hola"
    for bad in ('{"question": "x", "options": ["a"]}',
                '{"question": "x", "options": ["a","b","c","d","e","f"]}',
                '{"question": "x", "options": ["a","b"], "recommended": 2}',
                "{roto"):
        full = block(bad)
        assert elicit.parse_question(full) == (full, None)
    first = block('{"question": "1", "options": ["a", "b"]}')
    last = block('{"question": "2", "options": ["a", "b"]}')
    assert elicit.parse_question(first + last)[1].question == "2"
    assert elicit.parse_question("sin bloque") == ("sin bloque", None)


def test_costo_por_diferencia():
    assert elicit.turn_cost(D("0.25"), D("0.10")) == D("0.15")
    assert elicit.turn_cost(D("0.05"), D("0.10")) == 0


def test_archivo_de_otra_fase_se_borra_y_avisa(tmp_path, monkeypatch, conn):
    (tmp_path / "specs" / "001-x").mkdir(parents=True)
    effects = {"1": {"specs/001-x/spec.md": "ok", "specs/001-x/plan.md": "intruso"}}
    _, (r1, _) = run_flow(tmp_path, monkeypatch, conn, effects)
    assert (tmp_path / "specs/001-x/spec.md").exists()
    assert not (tmp_path / "specs/001-x/plan.md").exists()
    assert any("plan.md" in w for w in r1.warnings)


def test_superar_el_limite_pausa(tmp_path, monkeypatch, conn):
    cid, (r1, r2) = run_flow(tmp_path, monkeypatch, conn, max_cost=D("0.10"))
    assert r1.paused and "pausa" in r1.warnings[-1]
    assert r2.paused and r2.cost == 0  # no se envió: ya estaba en pausa
    assert elicit.over_budget(conn, cid, D("0.10"))


def test_max_cost_usd():
    assert elicit.max_cost_usd({}) == 5
    assert elicit.max_cost_usd({"spec": {"max_cost_usd": 2.5}}) == D("2.5")
    for bad in (0, -1, "mucho"):
        with pytest.raises(ValueError):
            elicit.max_cost_usd({"spec": {"max_cost_usd": bad}})


def test_preflight(tmp_path, monkeypatch):
    ctx = service.Ctx(tmp_path, tmp_path / ".umbra", None, {})
    monkeypatch.setenv("PATH", str(tmp_path / "vacio"))
    with pytest.raises(service.OpError, match="claude login"):
        service.preflight(ctx)

    exe = fake_claude(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    assert shutil.which("claude") and exe
    with pytest.raises(service.OpError, match="uv tool install specify-cli"):
        service.preflight(ctx)  # claude sí, specify no

    shim = tmp_path / "bin" / ("specify.cmd" if sys.platform == "win32" else "specify")
    shim.write_text("@exit 0\n" if shim.suffix == ".cmd" else "#!/bin/sh\nexit 0\n")
    shim.chmod(0o755)
    with pytest.raises(service.OpError, match="specify init --here"):
        service.preflight(ctx)  # sin confirmación
    with pytest.raises(service.OpError, match="falló"):
        service.preflight(ctx, confirm=lambda _: True)  # el falso no crea .specify/
    (tmp_path / ".specify").mkdir()
    service.preflight(ctx)
