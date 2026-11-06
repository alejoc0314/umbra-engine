"""Explorar (spec 035, US1): zona de la tarea, tests, historia y armado del paquete con tope."""

import subprocess
from pathlib import Path

from umbra.contracts.envelope import TaskInfo
from umbra.management import explore
from umbra.routines.parts import Part


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def repo(path: Path, files: dict[str, str] | None = None, msg: str = "init") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@t")
    git(path, "config", "user.name", "t")
    if files:
        commit(path, files, msg)
    return path


def commit(path: Path, files: dict[str, str], msg: str) -> None:
    for name, text in files.items():
        f = path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", msg)


def part(root: Path, name: str = "") -> Part:
    return Part(name, root, root, {}, "", None)


def task(**kw) -> TaskInfo:
    return TaskInfo(number=kw.pop("number", 1), title=kw.pop("title", "Tarea"), **kw)


def paths(entries) -> dict[str, str]:
    return {e["path"]: e["why"] for e in entries}


def test_seeds_from_scope_text_and_identifiers(tmp_path):
    root = repo(tmp_path / "r", {
        "src/pagos/cobro.py": "def cobrar():\n    pass\n",
        "src/pagos/tarifas.py": "X = 1\n",
        "src/util/redondeo.py": "def calcular_tarifa_final():\n    pass\n",
        "otro.py": "Y = 2\n",
    })
    found = paths(explore.zone([part(root)], task(
        description="Revisa src/pagos/tarifas.py y usa calcular_tarifa_final",
        scope=["src/pagos/cobro.py"]), None))
    assert "en scope" in found["src/pagos/cobro.py"]
    assert "src/pagos/tarifas.py" in found
    assert "src/util/redondeo.py" in found
    assert "otro.py" not in found


def test_identifier_in_too_many_files_does_not_discriminate(tmp_path):
    files = {f"m{i}.py": "comun_compartido = 1\n" for i in range(explore.MAX_PER_IDENTIFIER + 1)}
    root = repo(tmp_path / "r", files)
    assert explore.zone([part(root)], task(description="toca comun_compartido"), None) == []


def test_co_change_adds_three_per_seed(tmp_path):
    root = repo(tmp_path / "r", {"a.py": "0\n", **{f"b{i}.py": "0\n" for i in range(5)}})
    for n in range(1, 4):
        commit(root, {"a.py": f"{n}\n", "b0.py": f"{n}\n", "b1.py": f"{n}\n",
                      "b2.py": f"{n}\n"}, f"cambio {n}")
    commit(root, {"a.py": "9\n", "b3.py": "9\n"}, "uno solo")
    found = paths(explore.zone([part(root)], task(scope=["a.py"]), None))
    co = [p for p, why in found.items() if "cambia junto a" in why]
    assert sorted(co) == ["b0.py", "b1.py", "b2.py"]


def test_tests_by_naming_convention(tmp_path):
    root = repo(tmp_path / "r", {
        "src/cobro.py": "0\n", "tests/test_cobro.py": "0\n",
        "web/precio.ts": "0\n", "web/precio.test.ts": "0\n",
        "js/carro.js": "0\n", "js/carro.spec.js": "0\n",
        "app/Factura.php": "0\n", "tests/FacturaTest.php": "0\n",
        "tests/test_otro.py": "0\n",
    })
    files = [{"path": p, "repo": "", "why": "en scope"} for p in
             ("src/cobro.py", "web/precio.ts", "js/carro.js", "app/Factura.php")]
    found = {t["path"]: t["covers"] for t in explore.tests_for([part(root)], files)}
    assert found == {"tests/test_cobro.py": "src/cobro.py", "web/precio.test.ts": "web/precio.ts",
                     "js/carro.spec.js": "js/carro.js", "tests/FacturaTest.php": "app/Factura.php"}


def test_history_lists_recent_commits_of_the_zone(tmp_path):
    root = repo(tmp_path / "r", {"a.py": "0\n", "b.py": "0\n"})
    commit(root, {"a.py": "1\n"}, "redondeo de tarifas")
    commit(root, {"b.py": "1\n"}, "fuera de la zona")
    hist = explore.history([part(root)], [{"path": "a.py", "repo": "", "why": "en scope"}])
    assert [h["subject"] for h in hist] == ["redondeo de tarifas", "init"]
    assert hist[0]["paths"] == ["a.py"] and len(hist[0]["sha"]) == 7


def test_package_never_exceeds_the_cap_and_counts_omitted(tmp_path):
    files = [{"path": f"src/m{i}.py", "repo": "", "why": "en scope"} for i in range(5)]
    hist = [{"sha": f"{i:07d}", "date": "2026-10-30", "subject": "x" * 60, "paths": ["src/m0.py"]}
            for i in range(40)]
    md, summary = explore.build_package(files, [], [], hist, [], max_chars=700)
    assert len(md) <= 700 and summary["chars"] == len(md) <= summary["max_chars"]
    omitted = {o["kind"]: o for o in summary["omitted"]}
    assert omitted["history"]["count"] > 0 and omitted["history"]["why"] == "tope"
    assert "# Zona de la tarea" in md and "Omitido por tope" in md
    assert all(line in md for line in ("- src/m0.py — en scope",))


def test_empty_repo_still_builds_package_with_notes(tmp_path):
    root = repo(tmp_path / "vacio")
    md, summary = explore.explore(None, [part(root)], task(description="algo"), {})
    assert md and summary["files"] == []
    assert any("historia" in n for n in summary["notes"])
    assert any("tests" in n for n in summary["notes"])


def test_space_paths_carry_the_repo_prefix(tmp_path):
    front = repo(tmp_path / "esp" / "front", {"src/vista.ts": "0\n", "src/vista.test.ts": "0\n"})
    back = repo(tmp_path / "esp" / "back", {"api.py": "0\n"})
    md, summary = explore.explore(None, [part(front, "front"), part(back, "back")],
                                  task(scope=["front/src/vista.ts"]), {})
    assert summary["files"][0] == {"path": "front/src/vista.ts", "repo": "front",
                                   "why": "en scope"}
    assert summary["tests"][0]["path"] == "front/src/vista.test.ts"
    assert "front/src/vista.ts" in md


def test_previous_tasks_touching_the_zone(tmp_path):
    from umbra.unified.store import open_store
    conn = open_store(tmp_path / ".umbra")
    for n, (status, title) in enumerate([("SUCCEEDED", "Cobro"), ("BLOCKED", "Otra")], 1):
        conn.execute("INSERT INTO task (id, number, title, created_at, updated_at)"
                     " VALUES (?, ?, ?, '', '')", (f"t{n}", n, title))
        conn.execute("INSERT INTO run (id, task_id, routine, status, idempotency_key,"
                     " created_at, updated_at) VALUES (?, ?, 'quick', ?, ?, ?, ?)",
                     (f"r{n}", f"t{n}", status, f"k{n}", f"2026-11-0{n}", f"2026-11-0{n}"))
    conn.execute("INSERT INTO run_file (run_id, repo, path) VALUES ('r1', '', 'src/a.py')")
    conn.execute("INSERT INTO run_file (run_id, repo, path) VALUES ('r2', '', 'src/b.py')")
    conn.execute("INSERT INTO attempt (id, run_id, stage, attempt_no, status, started_at)"
                 " VALUES ('a1', 'r1', 'review', 1, 'findings', '')")
    conn.execute("INSERT INTO finding (id, attempt_id, severity, message)"
                 " VALUES ('f1', 'a1', 'high', 'no redondear antes de sumar')")
    conn.execute("INSERT INTO finding (id, attempt_id, severity, message)"
                 " VALUES ('f2', 'a1', 'low', 'estilo')")
    prev = explore.previous_tasks(conn, [], [{"path": "src/a.py", "repo": "", "why": ""}])
    assert prev == [{"number": 1, "title": "Cobro", "outcome": "SUCCEEDED",
                     "findings": ["no redondear antes de sumar"]}]


def test_explore_runs_in_feature_but_quick_stays_minimal():
    import yaml

    import umbra

    routines = Path(umbra.__file__).parent / "defaults" / "routines"

    def stages(name: str) -> list[str]:
        data = yaml.safe_load((routines / f"{name}.yaml").read_text(encoding="utf-8"))
        return [s["name"] for s in data["stages"]]

    assert stages("feature")[0] == "explore"
    assert stages("quick") == ["build", "ship"]  # la rutina rápida no explora
