"""`claude` falso. Modo por FAKE_CLAUDE_MODE (lista separada por comas, una entrada por llamada)."""

import json
import os
import sys
import time
from pathlib import Path

state_dir = Path(os.environ["FAKE_STATE_DIR"])
state_dir.mkdir(parents=True, exist_ok=True)
calls_file = state_dir / "claude_calls.json"


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


prompt = sys.stdin.read()
with locked(calls_file):
    calls = json.loads(calls_file.read_text()) if calls_file.exists() else []
    calls.append({"args": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd()})
    calls_file.write_text(json.dumps(calls))

modes = os.environ.get("FAKE_CLAUDE_MODE", "ok").split(",")
mode = modes[min(len(calls), len(modes)) - 1]
calc = Path("calc.py")
status, questions, findings = "done", [], []

if mode in ("ok", "slow"):  # slow: tarda lo bastante para ver dos tareas a la vez
    if mode == "slow":
        time.sleep(2)
    calc.write_text("def add(a, b):\n    return a + b\n")
elif mode == "broken":
    calc.write_text("def add(a, b):\n    return a - b\n")
elif mode == "delete_test":
    calc.write_text("def add(a, b):\n    return a + b\n")
    Path("tests/test_calc.py").unlink()
elif mode == "sleep":
    time.sleep(60)
elif mode == "blocked":
    status, questions = "blocked", ["¿Qué debe pasar con números negativos?"]
elif mode == "unmet":
    findings = [{"severity": "high", "message": "criterio no cumplido: add(2, 3) == 5"}]
elif mode == "secret":
    calc.write_text("def add(a, b):\n    return a + b\n")
    Path("config.py").write_text("AWS_KEY = 'AKIAABCDEFGHIJKLMNOP'\n")
elif mode == "append_test":  # añade un test nuevo al final de un archivo de tests existente
    calc.write_text("def add(a, b):\n    return a + b\n")
    with Path("tests/test_calc.py").open("a") as f:
        f.write("\n\ndef test_add_zero():\n    assert add(0, 0) == 0\n")
elif mode == "skip_test":  # "arregla" desactivando el test existente
    t = Path("tests/test_calc.py")
    t.write_text("import pytest\n" + t.read_text().replace(
        "def test_add", "@pytest.mark.skip\ndef test_add"))
elif mode in ("append_mul", "append_div"):  # dos tareas que tocan el mismo lugar del archivo
    extra = ("def mul(a, b):\n    return a * b\n" if mode == "append_mul"
             else "def div(a, b):\n    return a / b\n")
    calc.write_text("def add(a, b):\n    return a + b\n\n\n" + extra)
elif mode == "resolve":  # resuelve conflictos conservando ambos lados
    for path in Path(".").rglob("*.py"):
        text = path.read_text()
        if "<<<<<<< " in text:
            kept = [ln for ln in text.splitlines(keepends=True)
                    if not ln.startswith(("<<<<<<< ", "=======", ">>>>>>> "))]
            path.write_text("".join(kept))
elif mode == "bad":  # pasa los tests pero el SAST falso lo rechaza
    calc.write_text("def add(a, b):\n    return a + b  # BAD\n")
elif mode == "context":  # el cartógrafo escribe el mapa del repo
    Path("CONTEXT.md").write_text("<!-- umbra:inicio -->\n## Qué es\nUna calculadora.\n"
                                  "<!-- umbra:fin -->\n")
elif mode == "browse":  # el verificador visita la app y deja una captura fuera del workspace
    import re
    import urllib.request
    envelope = json.loads(re.search(r"```json\n(.*?)\n```", prompt, re.S).group(1))
    with urllib.request.urlopen(envelope["app_url"], timeout=5) as resp:
        seen = resp.status
    shots = Path(envelope["screenshots_dir"])
    (shots / "home.png").write_bytes(b"\x89PNG fake")
    structured_summary = f"visitado {envelope['app_url']} (HTTP {seen}); captura home.png"
elif mode in ("design", "design_code", "design_lint"):  # exporta una pantalla en design/
    Path("design/png").mkdir(parents=True, exist_ok=True)
    n = len(list(Path("design/png").glob("*.png"))) + 1
    Path(f"design/png/pantalla-{n}.png").write_bytes(b"\x89PNG fake")
    if mode == "design_code":  # y se pasa de la raya
        calc.write_text("def add(a, b):\n    return a + b\n")
    if mode == "design_lint":  # su herramienta detectó un problema (revisión automática)
        findings = [{"severity": "high", "message": "contraste 2.1:1 en el texto del boton",
                     "file": f"design/png/pantalla-{n}.png", "rule": "contraste"}]
    structured_images = [f"design/png/pantalla-{n}.png"]
elif mode == "design_options":  # tres direcciones para que la persona elija
    Path("design/direcciones").mkdir(parents=True, exist_ok=True)
    structured_options = []
    for name in ("Calida", "Nocturna", "Editorial"):
        Path(f"design/direcciones/{name}.png").write_bytes(b"\x89PNG fake")
        structured_options.append({"name": name, "images": [f"design/direcciones/{name}.png"]})
elif mode == "critique":  # el crítico ve algo roto
    findings = [{"severity": "high", "message": "el texto del boton se corta",
                 "file": "design/png/pantalla-1.png", "rule": "tipografia"}]
elif mode == "explore":  # un explorador del onboarding: nota + dudas
    structured_summary = "## Hallazgos\n\nUna calculadora en calc.py con tests en tests/."
    questions = ["Para quien es la calculadora?"]
elif mode in ("onboard_write", "onboard_stray"):  # el redactor deja los artefactos
    Path(".specify/memory").mkdir(parents=True, exist_ok=True)
    Path("specs/000-linea-base").mkdir(parents=True, exist_ok=True)
    Path("CONTEXT.md").write_text("<!-- umbra:inicio -->\n## Que es\nCalculadora.\n"
                                  "<!-- umbra:fin -->\n")
    Path(".specify/memory/constitution.md").write_text(
        "# Repo Constitution\n\n## Core Principles\n\n### 1. Tests\n\nToda funcion MUST tener "
        "test.\n- **Estado**: asi se hace hoy\n- **Evidencia**: tests/test_calc.py\n")
    Path("specs/000-linea-base/inventario.md").write_text("# Inventario\n\n- add: calc.py\n")
    if mode == "onboard_stray":  # y se pasa de la raya
        calc.write_text("def add(a, b):\n    return 42\n")
    structured_summary = "Calculadora; principio clave: todo con test."
elif mode in ("replicate", "replicate_stray"):  # visita la app y deja la réplica en design/
    import re
    import urllib.request
    envelope = json.loads(re.search(r"```json\n(.*?)\n```", prompt, re.S).group(1))
    with urllib.request.urlopen(envelope["app_url"], timeout=5) as resp:
        seen = resp.status
    Path("design/actual").mkdir(parents=True, exist_ok=True)
    Path("design/actual/inicio.png").write_bytes(b"\x89PNG fake")
    Path("design/actual/indice.md").write_text("| Vista | Ruta |\n| Inicio | / |\n")
    Path("design/sistema.md").write_text("# Sistema\n\nPrimario #001E62\n")
    if mode == "replicate_stray":
        calc.write_text("def add(a, b):\n    return 42\n")
    structured_images = ["design/actual/inicio.png"]
    structured_summary = f"1 vista (HTTP {seen})"
elif mode in ("amend", "amend_stray"):  # el redactor enmienda la constitución
    c = Path(".specify/memory/constitution.md")
    c.write_text(c.read_text() + "\n### 2. Contratos\n\nToda API MUST tener test de contrato.\n")
    if mode == "amend_stray":
        Path("CONTEXT.md").write_text("cambiado\n")
    structured_summary = "Nuevo principio 2 (MINOR, 1.1.0)."
elif mode in ("cross", "cross_broken", "cross_stray", "cross_one"):  # tarea entre repos (033)
    repos = sorted(d for d in Path(".").iterdir() if (d / "calc.py").is_file())
    for d in repos[1:] if mode == "cross_one" else repos:  # cross_one: solo el último
        broken = mode == "cross_broken" and d == repos[-1]
        (d / "calc.py").write_text("def add(a, b):\n    return a %s b\n" % ("-" if broken else "+"))
    if mode == "cross_stray":
        Path("notas.txt").write_text("fuera de los repos")
elif mode == "touch":  # una etapa de solo lectura que escribe
    Path("intruso.txt").write_text("x")
elif mode == "error":
    print(json.dumps({"type": "result", "is_error": True, "result": "boom", "session_id": "s"}))
    sys.exit(1)
# "noop": no cambia nada

structured = {"status": status, "summary": globals().get("structured_summary", f"modo {mode}"),
              "questions": questions, "findings": findings,
              "images": globals().get("structured_images", []),
              "options": globals().get("structured_options", [])}
if mode == "plan_ui":  # el planificador ve que la tarea toca la interfaz
    structured["needs_design"] = True


def task(title, deps):
    return {"title": title, "description": f"hacer {title}", "acceptance": [f"{title} listo"],
            "scope": ["calc.py"], "priority": 2, "depends_on": deps}


if mode == "propose":
    structured = {"tasks": [task("modelo", []), task("api", [0]), task("docs", [1])],
                  "questions": []}
elif mode == "propose_cycle":
    structured = {"tasks": [task("a", [1]), task("b", [0])], "questions": []}
elif mode == "propose_questions":
    structured = {"tasks": [], "questions": ["¿Qué base de datos?"]}
elif mode == "onboard_questions":
    structured = {"questions": [
        {"question": "Quien usa la app?", "options": ["Clientes", "Equipo interno"],
         "recommended": 1},
        {"question": "Que no se toca?", "options": ["Las migraciones", "Nada en especial"]}],
        "summary": "dos dudas"}

print(json.dumps({"type": "system", "subtype": "init", "session_id": "sess-fake"}))
print(json.dumps({
    "type": "result", "subtype": "success", "is_error": False, "session_id": "sess-fake",
    "total_cost_usd": 0.05, "result": "hecho",
    "structured_output": structured,
    "usage": {"input_tokens": 100, "output_tokens": 20},
    "modelUsage": {"claude-sonnet-5-5": {}},
}))
