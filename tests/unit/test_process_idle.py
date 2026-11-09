"""Corte por inactividad de los agentes: uno que avanza sigue; uno callado se corta antes."""

import sys

from umbra.adapters.base import AgentResult, AgentRun, first_id, resume_on_timeout
from umbra.blocks.process import run_bounded
from umbra.contracts.envelope import Envelope, TaskInfo
from umbra.contracts.profile import Limits, Profile

TALKS = "import time\nfor i in range(8):\n    print(i, flush=True)\n    time.sleep(0.25)\n"
SILENT = "import time\nprint('arranco', flush=True)\ntime.sleep(30)\n"


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_a_process_that_keeps_talking_is_not_cut_by_idle(tmp_path):
    proc = run_bounded(py(TALKS), tmp_path, timeout_s=20, idle_s=1)  # 2 s, nunca 1 s callado
    assert not proc.timed_out and proc.exit_code == 0 and "7" in proc.output


def test_a_silent_process_is_cut_by_idle_long_before_the_ceiling(tmp_path):
    proc = run_bounded(py(SILENT), tmp_path, timeout_s=20, idle_s=0.8)
    assert proc.timed_out and proc.idle and "arranco" in proc.output


def test_the_ceiling_still_cuts_a_process_that_talks_forever(tmp_path):
    proc = run_bounded(py(TALKS), tmp_path, timeout_s=0.8, idle_s=5)
    assert proc.timed_out and not proc.idle


def test_limits_idle_and_ceiling():
    assert Limits(max_minutes=20).idle_s() == 600  # lo menor entre max_minutes y 10
    assert Limits(max_minutes=4).idle_s() == 240
    assert Limits(max_minutes=20, idle_minutes=3).idle_s() == 180
    assert Limits(max_minutes=10).ceiling_s() == 1800  # techo: max_minutes × 3


def test_first_id_reads_the_announced_session():
    out = 'ruido\n{"type": "system", "session_id": "s-1"}\n{"type": "x"}\n'
    assert first_id(out, "session_id") == "s-1"
    assert first_id('{"type": "thread.started", "thread_id": "t-9"}', "thread_id") == "t-9"
    assert first_id("nada", "session_id") is None


def req(tmp_path):
    env = Envelope(run_id="r", stage="review", attempt_id="a", input_sha="s",
                   task=TaskInfo(number=1, title="t"))
    return AgentRun(env, Profile(name="p", agent="codex", roles=[]), tmp_path, tmp_path / "log")


def test_a_timeout_with_a_session_is_resumed_once(tmp_path):
    seen = []

    def run(r):
        seen.append(r.resume_session)
        return AgentResult(ok=False, output=None, timed_out=True, session_id="s-1",
                           error="tiempo agotado: 10 min sin señales de vida")
    first = AgentResult(ok=False, output=None, timed_out=True, session_id="s-1", error="x")
    out = resume_on_timeout(run, req(tmp_path), first)
    assert seen == ["s-1"] and out.resumed  # una sola vez
    assert "también tras retomar la sesión" in out.error


def test_a_timeout_without_a_session_is_not_resumed(tmp_path):
    first = AgentResult(ok=False, output=None, timed_out=True, error="x")
    assert resume_on_timeout(lambda r: 1 / 0, req(tmp_path), first) is first
