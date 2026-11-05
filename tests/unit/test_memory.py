"""Memoria de decisiones: normalizar, renderizar y reconstruir `.umbra/aprendido.md`."""

import pytest

from umbra.management import memory
from umbra.unified import store
from umbra.unified.events import add_event


@pytest.fixture
def conn(tmp_path):
    return store.open_store(tmp_path / ".umbra")


def seed_run(conn, number):
    tid, rid = store.new_id(), store.new_id()
    conn.execute(
        "INSERT INTO task (id, number, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (tid, number, f"t{number}", store.now(), store.now()))
    conn.execute(
        "INSERT INTO run (id, task_id, routine, status, idempotency_key, created_at, updated_at)"
        " VALUES (?, ?, 'quick', 'BLOCKED', ?, ?, ?)",
        (rid, tid, f"k{number}", store.now(), store.now()))
    return rid


def test_normalize_ignores_case_location_spaces_and_final_punctuation():
    assert memory.normalize("Falta  Validar entradas (calc.py:3).") == "falta validar entradas"
    assert memory.normalize("  falta validar entradas  ") == "falta validar entradas"
    assert memory.normalize("¿Falta validar?") == "¿falta validar"


def test_render_keeps_section_order_and_marks_empty_sections():
    text = memory.render({"waived": [], "deferred": [], "answers": [], "allowed": []})
    assert text.index("## Revisión: no pedir") < text.index("## Para después") \
        < text.index("## Respuestas dadas") < text.index("## Rutas autorizadas")
    assert "generado" in text.lower()
    full = memory.render({
        "waived": [{"text": "falta validar entradas", "task": 1, "date": "2026-11-04",
                    "reason": "no aplica"}],
        "deferred": [], "answers": [], "allowed": []})
    assert "- falta validar entradas (tarea 1, 2026-11-04, no aplica)" in full


def test_rebuild_is_deterministic_and_reads_every_decision(conn, tmp_path):
    rid = seed_run(conn, 1)
    add_event(conn, rid, "finding.decided", "cli", decision="waived", reason="no aplica",
              message="falta validar entradas", task=None)
    add_event(conn, rid, "finding.decided", "cli", decision="deferred", reason="luego",
              message="faltan tests de bordes", task=7)
    add_event(conn, rid, "run.blocked", "worker", stage="build", code="agent_questions",
              reason="el agente necesita aclaraciones: ¿Qué pasa con negativos?",
              details={"questions": ["¿Qué pasa con negativos?"]})
    add_event(conn, rid, "task.answered", "cli", answer="Se suman igual.")
    add_event(conn, rid, "policy.allowed", "cli", number=1, paths=["tests/test_calc.py"])
    udir = tmp_path / ".umbra"
    path = memory.rebuild(conn, udir)
    first = path.read_text(encoding="utf-8")
    assert "- falta validar entradas (tarea 1," in first and "no aplica)" in first
    assert "- faltan tests de bordes (tarea 1," in first and "luego, tarea 7)" in first
    assert "¿Qué pasa con negativos?" in first and "Se suman igual." in first
    assert "tests/test_calc.py (tarea 1," in first
    path.unlink()
    assert memory.rebuild(conn, udir).read_text(encoding="utf-8") == first


def test_decided_messages_are_normalized_across_the_repo(conn):
    rid = seed_run(conn, 1)
    aid = store.new_id()
    conn.execute("INSERT INTO attempt (id, run_id, stage, attempt_no, status, started_at)"
                 " VALUES (?, ?, 'review', 1, 'findings', ?)", (aid, rid, store.now()))
    for status, message in (("waived", "Falta validar entradas (calc.py:3)."),
                            ("deferred", "Faltan tests de bordes"), ("open", "Otra cosa")):
        conn.execute("INSERT INTO finding (id, attempt_id, severity, message, status)"
                     " VALUES (?, ?, 'high', ?, ?)", (store.new_id(), aid, message, status))
    assert memory.decided_messages(conn) == {"falta validar entradas", "faltan tests de bordes"}


def test_load_cuts_on_whole_lines_and_is_empty_without_file(tmp_path):
    assert memory.load(tmp_path) == ""
    (tmp_path / "aprendido.md").write_text("linea uno\nlinea dos\nlinea tres\n", encoding="utf-8")
    assert memory.load(tmp_path, limit=15) == "linea uno\n"
    assert memory.load(tmp_path) == "linea uno\nlinea dos\nlinea tres\n"


def test_project_notes_joins_context_and_learned(tmp_path):
    assert memory.project_notes(tmp_path, tmp_path / ".umbra") is None
    (tmp_path / ".umbra").mkdir()
    (tmp_path / ".umbra" / "aprendido.md").write_text("- algo\n", encoding="utf-8")
    (tmp_path / "CONTEXT.md").write_text("# Mapa\n", encoding="utf-8")
    notes = memory.project_notes(tmp_path, tmp_path / ".umbra")
    assert "Mapa del repositorio" in notes and "Aprendido en este repo" in notes
    assert "# Mapa" in notes and "- algo" in notes
