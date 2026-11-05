"""`umbra agent test` / `umbra profile test`: correr un agente contra una tarea de ejemplo."""

import subprocess
import tempfile
from pathlib import Path

from umbra.adapters import get_adapter
from umbra.adapters.base import AgentResult, AgentRun
from umbra.contracts.envelope import Envelope, TaskInfo
from umbra.contracts.profile import Limits, Profile
from umbra.unified.store import new_id

SAMPLE_BEFORE = "def total(items):\n    return sum(items)\n"
SAMPLE_AFTER = ("def total(items):\n    # TODO validar que items no sea None\n"
                "    return sum(items)\n")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def sample_repo(base: Path) -> tuple[Path, str, str]:
    repo = base / "sample"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "umbra@local")
    _git(repo, "config", "user.name", "umbra")
    (repo / "app.py").write_text(SAMPLE_BEFORE)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "app.py").write_text(SAMPLE_AFTER)
    _git(repo, "commit", "-q", "-am", "cambio")
    return repo, base_sha, _git(repo, "rev-parse", "HEAD")


def default_profile(agent: str) -> Profile:
    return Profile(name=f"test-{agent}", agent=agent, roles=["review"], actions=["read"],
                   limits=Limits(max_minutes=5))


def run_sample(profile: Profile, udir: Path | None) -> AgentResult:
    stage = profile.roles[0] if profile.roles else "review"
    adapter = get_adapter(profile.agent, udir, require_verified=False)
    with tempfile.TemporaryDirectory(prefix="umbra-agent-test-") as tmp:
        repo, base_sha, head_sha = sample_repo(Path(tmp))
        diff = _git(repo, "diff", f"{base_sha}..{head_sha}")
        envelope = Envelope(
            run_id="agent-test", stage=stage, attempt_id=new_id(), input_sha=head_sha,
            task=TaskInfo(number=0, title="Revisar la función total",
                          description="Tarea de ejemplo de umbra agent test: revisa el diff.",
                          acceptance=["total(None) no debe fallar sin explicación"]),
            diff=diff)
        req = AgentRun(envelope, profile, repo, Path(tmp) / "agent-test.log")
        return adapter.run(req)
