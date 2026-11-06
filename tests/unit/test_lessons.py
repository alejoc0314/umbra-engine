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
