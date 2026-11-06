"""Tareas que cruzan repos (spec 033): un worktree por repo, un PR por repo, una aprobación."""

import json
import sys
from pathlib import Path

from tests.acceptance.test_verify_browser import free_port, port_open
from tests.acceptance.test_workspace import SPEC, remote_file, spec
from tests.conftest import git
from umbra import service


def add_cross(ws, *extra):
    ws.umbra("task", "add", "Sumar en los dos", "-a", "add(2, 3) == 5", "--repo", "api",
             "--repo", "web", *extra)


def parts(ws, number=1):
    return {r["repo"]: dict(r) for r in ws.conn.execute(
        "SELECT * FROM run_part WHERE run_id = ?", (ws.run(number)["id"],))}


def test_a_task_across_repos_ships_one_pr_per_repo_and_merges_in_order(ws):
    add_cross(ws)
    ws.mode("cross")
    ws.umbra("run", "1", "--foreground")
    run = ws.run(1)
    assert run["status"] == "WAITING_APPROVAL", ws.umbra("explain", "1").output
    folder = Path(run["worktree"])
    # el agente trabajó en una carpeta con un worktree de cada repo, en la misma rama
    build = ws.claude_calls()[0]
    assert Path(build["cwd"]).resolve() == folder.resolve()
    assert "Tarea entre repos" in build["prompt"] and "`api/`" in build["prompt"]
    for name in ("api", "web"):
        assert git(folder / name, "branch", "--show-current").stdout.strip() == run["branch"]
    # una parte por repo, cada una con su último commit evaluado
    ps = parts(ws)
    assert list(ps) == ["api", "web"] and all(p["head_sha"] for p in ps.values())
    tests = [json.loads(r[0]) for r in ws.conn.execute(
        "SELECT payload FROM event WHERE type = 'evidence.tests'")]
    assert [(t["repo"], t["exit_code"]) for t in tests] == [("api", 0), ("web", 0)]
    # un PR por repo, cada uno enlaza al otro
    prs = ws.prs()
    assert [Path(p["repo"]).name for p in prs] == ["api.git", "web.git"]
    for pr in prs:
        assert "PRs de esta tarea" in pr["body"]
        assert all(other["url"] in pr["body"] for other in prs)
    # el diff de la tarea, con el repo delante de cada archivo
    numstat, patch = service.run_diff(service.load(ws.root), run)
    assert "api/calc.py" in numstat and "web/calc.py" in numstat
    assert "b/web/calc.py" in patch
    report = service.evidence(service.load(ws.root), 1)["report"]
    assert report["pr"] == " · ".join(f"{n}: {p['url']}" for n, p in zip(("api", "web"), prs,
                                                                         strict=True))
    rows = json.loads(ws.umbra("task", "list", "--json").output)
    assert rows[0]["title"] == "api + web · Sumar en los dos"

    ws.umbra("approve", "1", input="y\n")
    assert ws.run(1)["status"] == "SUCCEEDED"
    for name in ("api", "web"):
        assert "return a + b" in remote_file(ws, name, "main", "calc.py")
        assert "return a + b" in (ws.root / name / "calc.py").read_text()  # base local al día
    assert not folder.exists()


def test_failing_tests_in_one_repo_fail_the_task(ws):
    add_cross(ws)
    ws.mode("cross_broken")  # api queda bien; web, mal
    ws.umbra("run", "1", "--foreground")
    assert ws.run(1)["status"] == "BLOCKED"
    blocked = json.loads(ws.conn.execute("SELECT payload FROM event WHERE type = 'run.blocked'"
                                         ).fetchone()[0])
    assert blocked["code"] == "tests_failing" and blocked["details"]["repo"] == "web"
    last_build = ws.claude_calls()[-1]["prompt"]
    assert "En web:" in last_build


def test_files_outside_the_repos_are_dropped(ws):
    add_cross(ws)
    ws.mode("cross_stray")
    ws.umbra("run", "1", "--foreground")
    run = ws.run(1)
    assert run["status"] == "WAITING_APPROVAL"
    assert not (Path(run["worktree"]) / "notas.txt").exists()
    stray = json.loads(ws.conn.execute("SELECT payload FROM event WHERE type = 'out_of_scope'"
                                       ).fetchone()[0])
    assert stray["files"] == ["notas.txt"]


def test_a_repo_without_changes_gets_no_pr(ws):
    api = ws.root / "api"  # el back ya suma: la tarea solo necesita cambiar el front
    (api / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    git(api, "commit", "-qam", "ya suma")
    git(api, "push", "-q", "origin", "main")
    add_cross(ws)
    ws.mode("cross_one")  # solo cambia web
    ws.umbra("run", "1", "--foreground")
    assert ws.run(1)["status"] == "WAITING_APPROVAL"
    assert [Path(p["repo"]).name for p in ws.prs()] == ["web.git"]
    ws.umbra("approve", "1", input="y\n")
    assert "return a + b" in remote_file(ws, "web", "main", "calc.py")
    assert git(api, "rev-parse", "HEAD").stdout == git(api, "rev-parse", "origin/main").stdout


def test_a_new_commit_in_any_repo_invalidates_the_approval(ws):
    add_cross(ws)
    ws.mode("cross")
    ws.umbra("run", "1", "--foreground")
    web = Path(ws.run(1)["worktree"]) / "web"
    (web / "extra.py").write_text("x = 1\n")
    git(web, "add", "-A")
    git(web, "commit", "-qm", "a mano")
    result = ws.umbra("approve", "1", input="y\n", ok=False)
    assert "commits posteriores" in result.output
    assert "return 0" in remote_file(ws, "api", "main", "calc.py")  # nada se integró


def test_a_failed_merge_halfway_resumes_with_what_is_missing(ws):
    add_cross(ws)
    ws.mode("cross")
    ws.umbra("run", "1", "--foreground")
    ws.monkeypatch.setenv("FAKE_GH_MERGE_FAIL", "web.git")
    result = ws.umbra("approve", "1", input="y\n", ok=False)
    assert "integrado en api; falta web" in result.output
    assert ws.run(1)["status"] == "WAITING_APPROVAL"
    api_main = remote_file(ws, "api", "main", "calc.py")
    assert "return a + b" in api_main
    ws.monkeypatch.delenv("FAKE_GH_MERGE_FAIL")
    before = git(ws.root / "api", "rev-parse", "origin/main").stdout
    ws.umbra("approve", "1", input="y\n")
    assert ws.run(1)["status"] == "SUCCEEDED"
    assert git(ws.root / "api", "rev-parse", "origin/main").stdout == before  # api, una vez
    assert "return a + b" in remote_file(ws, "web", "main", "calc.py")


def test_cancelling_closes_every_pr_and_worktree(ws):
    add_cross(ws)
    ws.mode("cross")
    ws.umbra("run", "1", "--foreground")
    folder = Path(ws.run(1)["worktree"])
    ws.umbra("reject", "1", "-m", "no era esto", input="y\n")
    assert [p["state"] for p in ws.prs()] == ["CLOSED", "CLOSED"]
    assert not folder.exists()


def test_a_story_across_repos_integrates_in_both_spec_branches(ws):
    spec(ws, SPEC.replace("**Repo**: api", "**Repo**: api, web"))
    ws.umbra("spec", "tasks", "specs/001-pagos")
    assert json.loads(ws.conn.execute("SELECT repos FROM task WHERE number = 1").fetchone()[0]
                      ) == ["api", "web"]
    from tests.acceptance.test_watch_actions import sync_worker
    sync_worker(ws)
    ws.mode("cross", "append_mul")  # la historia 2 (web) añade mul sobre lo de la 1
    ws.umbra("night", "--spec", "specs/001-pagos")
    assert ws.run(1)["status"] == ws.run(2)["status"] == "SUCCEEDED"
    for name in ("api", "web"):
        assert "return a + b" in remote_file(ws, name, "spec/001-pagos", "calc.py")
    pr = service.spec_pr(service.load(ws.root), "specs/001-pagos")
    assert [p["repo"] for p in pr["repos"]] == ["api", "web"]


# ---------- VERIFY de extremo a extremo ----------
DEV = """import http.server, os, sys
port, name, state = int(sys.argv[1]), sys.argv[2], sys.argv[3]
with open(os.path.join(state, f"{name}-env.txt"), "w") as f:
    f.write(os.environ.get("UMBRA_URL_API", ""))
http.server.ThreadingHTTPServer(("127.0.0.1", port), http.server.SimpleHTTPRequestHandler
                                ).serve_forever()
"""


def with_devs(ws, tmp_path):
    script = tmp_path / "devserver.py"
    script.write_text(DEV)
    ws.state.mkdir(parents=True, exist_ok=True)
    urls = {}
    for name in ("api", "web"):
        port = free_port()
        urls[name] = f"http://127.0.0.1:{port}"
        cfg = ws.root / name / ".umbra" / "project.toml"
        cfg.write_text(cfg.read_text().replace(
            "[commands]\n",
            f"[commands]\ndev = {{ run = '\"{sys.executable}\" \"{script}\" {port} {name} "
            f"\"{ws.state}\"', background = true, url = \"{urls[name]}\" }}\n"))
    return urls


def test_verify_starts_every_repo_and_the_front_points_to_the_back(ws, tmp_path):
    urls = with_devs(ws, tmp_path)
    add_cross(ws)
    ws.mode("noop", "cross", "noop")  # plan, build, verify (revisa el Codex falso)
    ws.umbra("run", "1", "--routine", "feature", "--foreground")
    assert ws.run(1)["status"] == "WAITING_APPROVAL", ws.umbra("explain", "1").output
    assert (ws.state / "web-env.txt").read_text() == urls["api"]  # el front, al back de la tarea
    assert (ws.state / "api-env.txt").read_text() == ""
    started = [json.loads(r[0]) for r in ws.conn.execute(
        "SELECT payload FROM event WHERE type = 'dev.started' ORDER BY id")]
    assert [s["repo"] for s in started] == ["api", "web"]
    assert urls["web"] in ws.claude_calls()[-1]["prompt"]  # el navegador abre el front
    assert not port_open(urls["api"]) and not port_open(urls["web"])
