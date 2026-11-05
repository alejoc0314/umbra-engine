import subprocess
import sys
import time

import pytest

from umbra.blocks.process import background_kwargs

CHILD = (
    "import ctypes, sys;"
    "h = ctypes.windll.kernel32.GetConsoleWindow();"
    "v = bool(h) and bool(ctypes.windll.user32.IsWindowVisible(h));"
    "open(sys.argv[1], 'w').write(f'{h} {v}')"
)


@pytest.mark.skipif(sys.platform != "win32", reason="ventanas de consola: solo Windows")
def test_background_children_get_no_visible_window(tmp_path):
    """Regresión: con DETACHED_PROCESS, cada agente que lanzaba el worker abría una ventana."""
    out = tmp_path / "window.txt"
    worker_like = f"import subprocess, sys; subprocess.run([sys.executable, '-c', {CHILD!r}, " \
                  f"sys.argv[1]])"
    subprocess.Popen([sys.executable, "-c", worker_like, str(out)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **background_kwargs())
    for _ in range(100):
        time.sleep(0.1)
        if out.exists() and out.read_text():
            break
    hwnd, visible = out.read_text().split()
    assert visible == "False" and hwnd == "0"


def test_background_flags_never_detach_without_console():
    kwargs = background_kwargs()
    if sys.platform == "win32":
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert not kwargs["creationflags"] & subprocess.DETACHED_PROCESS
    else:
        assert kwargs == {"start_new_session": True}
