"""`gh` falso: PRs en un JSON; la cabeza de cada PR se lee del remoto git real (bare local)."""

import atexit
import json
import os
import subprocess
import sys
from pathlib import Path

state_file = Path(os.environ["FAKE_STATE_DIR"]) / "gh.json"


def locked(path: Path):
    """Cerrojo entre procesos falsos a la vez (dos tareas en paralelo): archivo O_EXCL."""
    import contextlib
    import time

    @contextlib.contextmanager
    def ctx():
        lock = path.with_suffix(".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(500):
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                time.sleep(0.01)
        else:
            fd = None
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)
                lock.unlink(missing_ok=True)
    return ctx()


_lock = locked(state_file)
_lock.__enter__()  # todo el comando bajo cerrojo: el estado se lee y se escribe entero
atexit.register(_lock.__exit__, None, None, None)
state = json.loads(state_file.read_text()) if state_file.exists() else {"prs": []}


def save():
    state_file.write_text(json.dumps(state))


def opt(name, default=None):
    args = sys.argv
    return args[args.index(name) + 1] if name in args else default


def remote_sha(branch):
    out = subprocess.run(["git", "ls-remote", "origin", f"refs/heads/{branch}"],
                         capture_output=True, text=True).stdout.split()
    return out[0] if out else None


def repo():
    """El repo de la carpeta actual, como `gh`: su remoto origin."""
    return subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                          text=True).stdout.strip()


def refresh(pr):
    if pr["state"] == "OPEN":
        pr["headRefOid"] = remote_sha(pr["head"]) or pr["headRefOid"]
    return pr


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def merge_tree(pr):
    """Como GitHub: ¿la cabeza del PR se fusiona limpia sobre la base actual del remoto?"""
    git("fetch", "-q", "origin", pr["base"])
    return git("merge-tree", "--write-tree", f"refs/remotes/origin/{pr['base']}",
               pr["headRefOid"])


def mergeable(pr):
    if pr["state"] != "OPEN":
        return "UNKNOWN"
    return "MERGEABLE" if merge_tree(pr).returncode == 0 else "CONFLICTING"


def public(pr, fields):
    data = {k: pr.get(k) for k in fields.split(",")}
    if "mergeable" in data:
        data["mergeable"] = mergeable(pr)
    return data


args = sys.argv[1:]
if args[:2] == ["pr", "list"]:
    prs = [refresh(p) for p in state["prs"]
           if p["head"] == opt("--head") and p.get("repo", repo()) == repo()]
    save()
    print(json.dumps([public(p, opt("--json")) for p in prs]))
elif args[:2] == ["pr", "create"]:
    n = len(state["prs"]) + 1
    pr = {"number": n, "url": f"https://github.test/pr/{n}", "state": "OPEN",
          "head": opt("--head"), "base": opt("--base"), "title": opt("--title"),
          "body": opt("--body"), "repo": repo(),
          "headRefOid": remote_sha(opt("--head")), "mergeCommit": None}
    state["prs"].append(pr)
    save()
    if os.environ.get("FAKE_GH_CREATE_FAIL"):
        print("error: timeout", file=sys.stderr)
        sys.exit(1)
    print(pr["url"])
elif args[:2] == ["pr", "view"]:
    pr = refresh(state["prs"][int(args[2]) - 1])
    save()
    print(json.dumps(public(pr, opt("--json"))))
elif args[:2] == ["pr", "merge"]:
    pr = refresh(state["prs"][int(args[2]) - 1])
    if pr["headRefOid"] != opt("--match-head-commit"):
        print("head changed", file=sys.stderr)
        sys.exit(1)
    if (fail := os.environ.get("FAKE_GH_MERGE_FAIL")) and fail in pr.get("repo", ""):
        print("error: timeout", file=sys.stderr)
        sys.exit(1)
    result = merge_tree(pr)
    if result.returncode != 0:
        print("Pull request is not mergeable: the merge commit cannot be cleanly created.",
              file=sys.stderr)
        sys.exit(1)
    # integra de verdad en la base del remoto, como haría GitHub
    base = f"refs/remotes/origin/{pr['base']}"
    commit = git("commit-tree", result.stdout.split()[0], "-p", base, "-p", pr["headRefOid"],
                 "-m", f"Merge PR #{pr['number']}").stdout.strip()
    git("push", "-q", "origin", f"{commit}:refs/heads/{pr['base']}")
    pr["state"], pr["mergeCommit"] = "MERGED", {"oid": commit}
    save()
elif args[:2] == ["repo", "create"]:  # repo privado «en GitHub»: un bare local + push
    remotes = Path(os.environ["FAKE_STATE_DIR"]) / "remotes"
    remotes.mkdir(parents=True, exist_ok=True)
    bare = remotes / f"{args[2]}.git"
    git("init", "-q", "--bare", "-b", "main", str(bare))
    git("remote", "add", "origin", str(bare))
    if "--push" in args:
        git("push", "-q", "-u", "origin", "HEAD")
    print(f"https://github.test/{args[2]}")
elif args[:2] == ["pr", "edit"]:
    state["prs"][int(args[2]) - 1]["body"] = opt("--body")
    save()
elif args[:2] == ["pr", "close"]:
    state["prs"][int(args[2]) - 1]["state"] = "CLOSED"
    save()
else:
    print(f"fake gh: comando no soportado {args}", file=sys.stderr)
    sys.exit(2)
