import json

import pytest

from tests.conftest import git
from umbra import service
from umbra.management import planning

SPEC = """# Demo

### User Story 1 - Uno (Priority: P1)

Texto uno. FR-001

**Acceptance Scenarios**:

1. **Given** a, **When** b, **Then** c

### User Story 2 - Dos (Priority: P2)

Texto dos. FR-002

**Acceptance Scenarios**:

1. **Given** d, **When** e, **Then** f

### User Story 3 - Tres (Priority: P3)

Texto tres.

**Acceptance Scenarios**:

1. **Given** g, **When** h, **Then** i
"""
TASKS = "- [ ] T001 [US1] Editar `calc.py`\n- [ ] T002 [US2] Algo\n- [ ] T003 [US3] Otro\n"


@pytest.fixture
def spec_dir(env):
    d = env.root / "specs" / "001-demo"
    d.mkdir(parents=True)
    (d / "spec.md").write_text(SPEC, encoding="utf-8")
    (d / "tasks.md").write_text(TASKS, encoding="utf-8")
    return d


def rows(env):
    return [dict(r) for r in env.conn.execute(
        "SELECT t.*, (SELECT group_concat(d.number) FROM dependency x JOIN task d"
        " ON d.id = x.depends_on_id WHERE x.task_id = t.id) AS deps FROM task t ORDER BY number")]


def test_crea_tres_tareas_encadenadas_y_no_duplica(env, spec_dir):
    out = json.loads(env.umbra("spec", "tasks", "specs/001-demo", "--json").output)
    assert out["created"] == [1, 2, 3]
    r = rows(env)
    assert [t["status"] for t in r] == ["draft"] * 3
    assert [t["deps"] for t in r] == [None, "1", "2"]
    assert [t["story"] for t in r] == ["US1", "US2", "US3"]
    assert json.loads(r[0]["scope"]) == ["calc.py"]
    assert json.loads(r[0]["requirements"]) == ["FR-001"]
    assert r[0]["title"] == "Historia 1: Uno"
    again = json.loads(env.umbra("spec", "tasks", "specs/001-demo", "--json").output)
    assert again["created"] == [] and len(rows(env)) == 3


def test_sin_historias_falla_y_no_inserta(env, spec_dir):
    (spec_dir / "spec.md").write_text("# Nada\n", encoding="utf-8")
    res = env.umbra("spec", "tasks", "specs/001-demo", ok=False)
    assert res.exit_code != 0 and "umbra plan" in res.output.replace("\n", " ")
    assert rows(env) == []


def test_todo_o_nada(env, spec_dir, monkeypatch):
    def boom(*a, **k):
        raise planning.PlanningError("ciclo")

    monkeypatch.setattr(planning, "insert_proposals", boom)
    with pytest.raises(service.OpError):
        service.spec_tasks(service.load(env.root), spec_dir)
    assert rows(env) == []


def test_spec_se_copia_al_worktree_y_entra_en_el_commit(env, spec_dir):
    env.umbra("spec", "tasks", "specs/001-demo")
    env.umbra("task", "accept", "1")
    env.mode("ok")
    env.umbra("run", "1", "--foreground", ok=False)  # puede detenerse en la aprobación
    run = env.run(1)
    shown = git(env.root, "log", run["branch"], "--name-only", "--format=").stdout
    assert "specs/001-demo/spec.md" in shown


def test_copia_al_worktree_omite_enlaces_simbolicos(env, spec_dir, tmp_path):
    secreto = tmp_path / "secreto.txt"
    secreto.write_text("no debe salir", encoding="utf-8")
    try:
        (spec_dir / "enlace.txt").symlink_to(secreto)
    except (OSError, NotImplementedError):
        pytest.skip("el sistema no permite crear enlaces simbólicos")
    env.umbra("spec", "tasks", "specs/001-demo")
    env.umbra("task", "accept", "1")
    env.mode("ok")
    env.umbra("run", "1", "--foreground", ok=False)
    run = env.run(1)
    shown = git(env.root, "log", run["branch"], "--name-only", "--format=").stdout
    assert "specs/001-demo/spec.md" in shown
    assert "enlace.txt" not in shown


def test_todo_o_nada_tambien_revierte_la_spec(env, spec_dir, monkeypatch):
    llamadas = []
    real = planning.now

    def now_falla():
        llamadas.append(1)
        if len(llamadas) > 1:  # la spec ya se guardó; falla al insertar la primera tarea
            raise RuntimeError("fallo a mitad")
        return real()

    monkeypatch.setattr(planning, "now", now_falla)
    with pytest.raises(RuntimeError):
        service.spec_tasks(service.load(env.root), spec_dir)
    assert rows(env) == []
    assert env.conn.execute("SELECT COUNT(*) FROM spec").fetchone()[0] == 0


def test_rechaza_carpeta_fuera_del_repositorio(env, tmp_path):
    fuera = tmp_path / "externa"
    fuera.mkdir()
    (fuera / "spec.md").write_text(SPEC, encoding="utf-8")
    res = env.umbra("spec", "tasks", str(fuera), ok=False)
    assert res.exit_code != 0 and "dentro del repositorio" in res.output.replace("\n", " ")
    assert rows(env) == []


def test_copia_spec_con_carpeta_ya_versionada(env, spec_dir):
    (spec_dir / "plan.md").write_text("plan", encoding="utf-8")
    git(env.root, "add", "specs/001-demo/plan.md")
    git(env.root, "commit", "-q", "-m", "plan")
    git(env.root, "push", "-q", "origin", "main")
    env.umbra("spec", "tasks", "specs/001-demo")
    env.umbra("task", "accept", "1")
    env.mode("ok")
    env.umbra("run", "1", "--foreground", ok=False)
    run = env.run(1)
    shown = git(env.root, "log", run["branch"], "--name-only", "--format=").stdout
    assert "specs/001-demo/spec.md" in shown


def test_rechaza_spec_en_la_raiz_del_repositorio(env):
    (env.root / "spec.md").write_text(SPEC, encoding="utf-8")
    res = env.umbra("spec", "tasks", ".", ok=False)
    assert res.exit_code != 0 and "raíz" in res.output
    assert rows(env) == []
