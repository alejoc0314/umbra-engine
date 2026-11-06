"""Lecciones (spec 035): almacén global, clave de proyecto, secretos y cosecha de tropiezos."""

import shutil

import pytest

from tests.conftest import git
from umbra.contracts.envelope import LessonDraft
from umbra.management import lessons
from umbra.unified import config as cfg


def committed(repo):
    (repo / "a.txt").write_text("a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return repo


# ---------- base (T008) ----------
def test_project_key_survives_copying_the_repo(git_repo, tmp_path):
    committed(git_repo)
    key = lessons.project_key([git_repo])
    copy = tmp_path / "otra" / "copia"
    shutil.copytree(git_repo, copy)
    assert lessons.project_key([copy]) == key
    assert not key.startswith("path:")


def test_space_key_is_the_hash_of_its_sorted_repo_keys(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for r, name in ((a, "a.txt"), (b, "b.txt")):
        r.mkdir()
        git(r, "init", "-q", "-b", "main")
        git(r, "config", "user.email", "t@u.l")
        git(r, "config", "user.name", "t")
        (r / name).write_text(name)
        git(r, "add", "-A")
        git(r, "commit", "-q", "-m", name)
    space = lessons.project_key([a, b])
    assert space == lessons.project_key([b, a])
    assert space not in (lessons.project_key([a]), lessons.project_key([b]))


def test_repo_without_commits_uses_its_path(git_repo):
    key = lessons.project_key([git_repo])
    assert key.startswith("path:")
    assert key == lessons.project_key([git_repo])


def test_redact_hides_secrets():
    token = "ghp_" + "a" * 36
    text = lessons.redact(f"no subas {token} al repo")
    assert token not in text and "«oculto»" in text


def test_zone_ok():
    assert lessons.zone_ok("src/**")
    assert lessons.zone_ok("calc.py")
    assert not lessons.zone_ok("/etc/passwd")
    assert not lessons.zone_ok("C:/x")
    assert not lessons.zone_ok("../fuera/**")
    assert not lessons.zone_ok("src/../../x")


def test_schema_is_created_once(tmp_path):
    first = lessons.open_db()
    first.close()
    db = lessons.open_db()
    assert (cfg.umbra_home() / "lessons.db").is_file()
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"lesson", "lesson_origin", "lesson_history", "lesson_meta"} <= tables
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


# ---------- cosecha (T025) ----------
def origin(event_id, kind="review_rejected", detail="falta validar entradas"):
    return {"kind": kind, "task": 1, "run_id": "r1", "stage": "review", "detail": detail,
            "event_id": event_id}


def test_deterministic_draft_drops_location_and_uses_folders():
    d = lessons.draft("[high] falta validar entradas (src/api/a.py:12)",
                      ["src/api/a.py", "src/api/b.py", "calc.py"])
    assert d.text == "falta validar entradas"
    assert ":12" not in d.text
    assert d.zone == ["src/api/**", "calc.py"]


def test_lesson_draft_validation():
    assert lessons.validate(LessonDraft(text=""), set()) is None
    assert lessons.validate(LessonDraft(text="x", zone=["../x"]), set()) is None
    assert lessons.validate(LessonDraft(text="x", zone=["/abs"]), set()) is None
    assert lessons.validate(LessonDraft(text="x", same_as=9), {1}) is None
    ok = lessons.validate(LessonDraft(text="Valida entradas", zone=["src/**"],
                                      conflicts_with=[1, 9]), {1})
    assert ok is not None and ok.conflicts_with == [1]
    assert lessons.validate(LessonDraft(skip=True), set()).skip


def test_duplicate_text_adds_an_origin():
    db = lessons.open_db()
    d = LessonDraft(text="Falta validar entradas.", zone=["calc.py"])
    assert lessons.record(db, "k", d, [origin(1)], "calc") == 1
    again = LessonDraft(text="falta   VALIDAR entradas", zone=["calc.py"])
    assert lessons.record(db, "k", again, [origin(2)], "calc") is None
    assert db.execute("SELECT COUNT(*) FROM lesson").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM lesson_origin WHERE number = 1").fetchone()[0] == 2
    row = db.execute("SELECT status FROM lesson WHERE number = 1").fetchone()
    assert row["status"] == "proposed"
    actions = [r[0] for r in db.execute("SELECT action FROM lesson_history ORDER BY rowid")]
    assert actions == ["proposed", "merged_origin"]
    assert {r[0] for r in db.execute("SELECT channel FROM lesson_history")} == {"engine"}


def test_same_as_a_discarded_lesson_only_adds_the_origin():
    db = lessons.open_db()
    lessons.record(db, "k", LessonDraft(text="Regla vieja", zone=[]), [origin(1)], "calc")
    db.execute("UPDATE lesson SET status = 'discarded'")
    other = LessonDraft(text="Otra forma de decirlo", zone=["calc.py"], same_as=1)
    assert lessons.record(db, "k", other, [origin(2)], "calc") is None
    rows = db.execute("SELECT status, text FROM lesson").fetchall()
    assert [(r["status"], r["text"]) for r in rows] == [("discarded", "Regla vieja")]
    assert db.execute("SELECT COUNT(*) FROM lesson_origin").fetchone()[0] == 2


def test_harvesting_twice_does_not_duplicate():
    db = lessons.open_db()
    d = LessonDraft(text="Valida entradas", zone=["calc.py"])
    assert lessons.record(db, "k", d, [origin(1)], "calc") == 1
    assert lessons.record(db, "k", d, [origin(1)], "calc") is None
    assert db.execute("SELECT COUNT(*) FROM lesson_origin").fetchone()[0] == 1
    assert lessons.record(db, "k", LessonDraft(text="Otra regla"), [origin(3)], "calc") == 2


def test_secrets_never_reach_the_store():
    db = lessons.open_db()
    token = "ghp_" + "b" * 36
    lessons.record(db, "k", LessonDraft(text=f"no uses {token}"),
                   [origin(1, detail=f"token {token}")], "calc")
    assert token not in db.execute("SELECT text FROM lesson").fetchone()[0]
    assert token not in db.execute("SELECT detail FROM lesson_origin").fetchone()[0]


@pytest.mark.parametrize("value, expected", [
    ({}, {"enabled": True, "writer": "lesson-writer"}),
    ({"lessons": {"enabled": False, "writer": ""}}, {"enabled": False, "writer": ""}),
    ({"lessons": {"enabled": "sí", "writer": 3}}, {"enabled": True, "writer": "lesson-writer"}),
])
def test_lessons_settings(value, expected):
    assert cfg.lessons_settings(value) == expected


# ---------- cosecha con redactor (ruta por defecto) ----------
class FakeEngine:
    """Lo mínimo de `Engine` que usa `harvest`, con un redactor falso sin red."""

    def __init__(self, root, reply):
        import sqlite3
        from pathlib import Path

        self.root, self.home, self.space, self.project = root, Path(root), None, {}
        self.reply, self.calls, self.events, self.finished = reply, [], [], []
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            "CREATE TABLE task (id INTEGER PRIMARY KEY, number INTEGER);"
            "CREATE TABLE run (id TEXT PRIMARY KEY, task_id INTEGER, worktree TEXT);"
            "CREATE TABLE event (id INTEGER PRIMARY KEY, run_id TEXT, type TEXT, payload TEXT,"
            " created_at TEXT);"
            "CREATE TABLE run_file (run_id TEXT, repo TEXT, path TEXT);"
            "CREATE TABLE operation (operation_key TEXT PRIMARY KEY, kind TEXT, status TEXT,"
            " external_ref TEXT);"
            "INSERT INTO task VALUES (1, 1);"
            "INSERT INTO run VALUES ('r1', 1, NULL);")

    def rejected(self, message="[high] falta validar entradas (src/api/a.py:12)"):
        import json

        self.conn.execute(
            "INSERT INTO event (run_id, type, payload, created_at) VALUES ('r1',"
            " 'stage.rework', ?, '2026-11-06T00:00:00Z')",
            (json.dumps({"stage": "review", "feedback": [message]}),))

    def run_row(self, run_id):
        return self.conn.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()

    def profile(self, name):
        return name

    def agent_attempt(self, run, stage, profile, wt, **kw):
        from types import SimpleNamespace

        self.calls.append({"stage": stage, "profile": profile, **kw})
        if isinstance(self.reply, Exception):
            raise self.reply
        ok, output = self.reply
        return f"a{len(self.calls)}", SimpleNamespace(ok=ok, output=output)

    def finish_attempt(self, attempt_id, status):
        self.finished.append((attempt_id, status))

    def operation(self, key):
        return self.conn.execute("SELECT * FROM operation WHERE operation_key = ?",
                                 (key,)).fetchone()

    def record_operation(self, key, kind, status, ref):
        self.conn.execute("INSERT OR REPLACE INTO operation VALUES (?, ?, ?, ?)",
                          (key, kind, status, ref))

    def event(self, run_id, type_, **payload):
        self.events.append((type_, payload))


def stored():
    db = lessons.open_db()
    try:
        return ([(r["number"], r["text"], r["zone"], r["status"])
                 for r in db.execute("SELECT * FROM lesson ORDER BY number")],
                db.execute("SELECT COUNT(*) FROM lesson_origin").fetchone()[0])
    finally:
        db.close()


def test_harvest_uses_the_writer_draft_and_is_idempotent(git_repo):
    eng = FakeEngine(committed(git_repo), (True, LessonDraft(
        text="Valida   las entradas de la API", zone=["src/api/**"])))
    eng.rejected()
    assert lessons.harvest(eng, ["r1"]) == 1
    call = eng.calls[0]
    assert (call["stage"], call["profile"]) == ("lesson", "lesson-writer")
    assert call["output_model"] is LessonDraft
    assert any("falta validar entradas" in f for f in call["feedback"])
    assert call["previous"][0].file == "src/api/a.py"
    assert "- ninguna" in call["extra_notes"]
    assert eng.finished == [("a1", "done")]
    rows, origins = stored()
    assert rows == [(1, "Valida las entradas de la API", '["src/api/**"]', "proposed")]
    assert origins == 1
    assert eng.events[-1] == ("lessons.proposed", {"proposed": 1, "lessons": ["L1"]})

    assert lessons.harvest(eng, ["r1"]) == 0
    assert len(eng.calls) == 1
    assert stored() == (rows, 1)


def test_harvest_with_skip_proposes_nothing(git_repo):
    eng = FakeEngine(committed(git_repo), (True, LessonDraft(skip=True)))
    eng.rejected()
    assert lessons.harvest(eng, ["r1"]) == 0
    assert stored() == ([], 0)
    assert eng.events[-1] == ("lessons.proposed", {"proposed": 0, "lessons": []})
    assert lessons.harvest(eng, ["r1"]) == 0
    assert len(eng.calls) == 1


def test_harvest_with_same_as_adds_the_origin_to_the_existing_lesson(git_repo):
    eng = FakeEngine(committed(git_repo), None)
    db = lessons.open_db()
    key = lessons.project_key([git_repo])
    lessons.record(db, key, LessonDraft(text="Regla previa", zone=["src/api/**"]),
                   [{**origin(99), "run_id": "otra"}], "repo")
    db.close()
    eng.reply = (True, LessonDraft(text="Dicho de otra forma", zone=["src/api/**"], same_as=1))
    eng.rejected()
    assert lessons.harvest(eng, ["r1"]) == 0
    assert "L1 (proposed): Regla previa" in eng.calls[0]["extra_notes"]
    assert stored() == ([(1, "Regla previa", '["src/api/**"]', "proposed")], 2)


def test_harvest_with_unknown_same_as_falls_back_to_the_draft(git_repo):
    eng = FakeEngine(committed(git_repo), (True, LessonDraft(text="x", same_as=7)))
    eng.rejected()
    assert lessons.harvest(eng, ["r1"]) == 1
    assert stored() == ([(1, "falta validar entradas", '["src/api/**"]', "proposed")], 1)


@pytest.mark.parametrize("reply", [
    RuntimeError("el redactor se colgó"),
    (False, None),
    (True, "no es un LessonDraft"),
    (True, LessonDraft(text="fuera", zone=["../otro/**"])),
])
def test_harvest_with_a_failing_writer_keeps_the_deterministic_draft(git_repo, reply):
    eng = FakeEngine(committed(git_repo), reply)
    eng.rejected()
    assert lessons.harvest(eng, ["r1"]) == 1
    assert stored() == ([(1, "falta validar entradas", '["src/api/**"]', "proposed")], 1)
    assert lessons.harvest(eng, ["r1"]) == 0
    assert stored()[1] == 1


# ---------- decisiones de la persona (T032) ----------
def proposed(db, text="Valida entradas", zone=("src/api/**",), event_id=1, conflicts=()):
    d = LessonDraft(text=text, zone=list(zone), conflicts_with=list(conflicts))
    return lessons.record(db, "k", d, [origin(event_id)], "calc")


def test_parse_number_accepts_l_prefix():
    assert lessons.parse_number("L7") == 7
    assert lessons.parse_number("l7") == 7
    assert lessons.parse_number("7") == 7
    with pytest.raises(lessons.LessonError):
        lessons.parse_number("siete")


def test_approve_discard_retire_transitions():
    db = lessons.open_db()
    a, b = proposed(db), proposed(db, "Otra regla", event_id=2)
    out = lessons.approve(db, "k", a, actor="ana", channel="cli")
    assert out["status"] == "approved"
    assert lessons.discard(db, "k", b, reason="no aplica", actor="ana", channel="watch")[
        "status"] == "discarded"
    with pytest.raises(lessons.LessonError):
        lessons.retire(db, "k", b, actor="ana", channel="cli")  # descartada: no se retira
    assert lessons.retire(db, "k", a, actor="ana", channel="cli")["status"] == "retired"
    assert lessons.approve(db, "k", a, actor="ana", channel="cli")["status"] == "approved"
    with pytest.raises(lessons.LessonError):
        lessons.approve(db, "k", 99, actor="ana", channel="cli")
    hist = [(r["action"], r["actor"], r["channel"]) for r in db.execute(
        "SELECT action, actor, channel FROM lesson_history WHERE number = ? ORDER BY rowid",
        (a,))]
    assert hist[1:] == [("approved", "ana", "cli"), ("retired", "ana", "cli"),
                        ("approved", "ana", "cli")]


def test_retiring_a_proposal_is_not_valid():
    db = lessons.open_db()
    n = proposed(db)
    with pytest.raises(lessons.LessonError, match="propuesta"):
        lessons.retire(db, "k", n, actor="ana", channel="cli")


def test_approve_with_edited_text_keeps_the_original_in_history():
    db = lessons.open_db()
    n = proposed(db, "Texto original")
    out = lessons.approve(db, "k", n, text="Texto editado", zone=["src/**"], actor="ana",
                          channel="cli")
    assert out["text"] == "Texto editado" and out["zone"] == ["src/**"]
    shown = lessons.show(db, "k", n)
    approved = [h for h in shown["history"] if h["action"] == "approved"][0]
    assert "Texto original" in approved["before"]
    with pytest.raises(lessons.LessonError):
        lessons.approve(db, "k", proposed(db, "x", event_id=5), zone=["../fuera"],
                        actor="ana", channel="cli")


def test_applicable_only_approved_specific_first_and_without_conflicts():
    db = lessons.open_db()
    wide = proposed(db, "Todo el proyecto", zone=())
    api = proposed(db, "Solo api", event_id=2)
    other = proposed(db, "Otra zona", zone=("docs/**",), event_id=3)
    pending = proposed(db, "Pendiente", event_id=4)
    for n in (wide, api, other):
        lessons.approve(db, "k", n, actor="ana", channel="cli")
    got = [x["id"] for x in lessons.applicable(db, "k", ["src/api/a.py"])]
    assert got == [api, wide]
    assert pending not in got
    lessons.retire(db, "k", api, actor="ana", channel="cli")
    assert [x["id"] for x in lessons.applicable(db, "k", ["src\\api\\a.py"])] == [wide]
    clash = proposed(db, "Choca", zone=(), event_id=6, conflicts=[wide])
    lessons.approve(db, "k", clash, actor="ana", channel="cli")
    assert lessons.applicable(db, "k", ["src/api/a.py"]) == []
    assert lessons.show(db, "k", wide)["conflicts"] == [f"L{clash}"]
    lessons.resolve_conflict(db, "k", wide, clash, actor="ana", channel="cli")
    assert {x["id"] for x in lessons.applicable(db, "k", ["x.py"])} == {wide, clash}


def test_stale_when_no_file_matches_the_zone():
    assert lessons.stale(["src/api/**"], ["docs/a.md"])
    assert not lessons.stale(["src/api/**"], ["src/api/a.py"])
    assert not lessons.stale([], ["a.py"])


def test_list_puts_proposals_first_and_hides_closed_by_default():
    db = lessons.open_db()
    a, b, c = proposed(db), proposed(db, "B", event_id=2), proposed(db, "C", event_id=3)
    lessons.approve(db, "k", a, actor="ana", channel="cli")
    lessons.discard(db, "k", c, actor="ana", channel="cli")
    assert [x["id"] for x in lessons.list_(db, "k")] == [f"L{b}", f"L{a}"]
    assert len(lessons.list_(db, "k", all_=True)) == 3
    assert [x["id"] for x in lessons.list_(db, "k", status="discarded")] == [f"L{c}"]
    item = lessons.list_(db, "k")[0]
    assert set(item) >= {"id", "status", "text", "zone", "origins", "stale", "conflicts",
                         "updated_at"}
