"""Onboarding de un proyecto ya iniciado: umbra lo estudia a fondo antes de trabajar en él.

Fases (estado en `.umbra/artifacts/onboarding/estado.json`): `explorar` (reconocimiento y
línea base sin modelo, y cinco exploradores de solo lectura) → `preguntas` (lo que el código
no dice) → `redactar` (CONTEXT.md, constitución, inventario) → `revisar` (la persona aprueba o
pide cambios) → `hecho`. Nada se confirma sin la aprobación de la persona."""

import json
import re
import shutil
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from umbra.actions import commands, git
from umbra.chat.elicit import Question
from umbra.unified import config as cfg
from umbra.unified.events import add_event
from umbra.unified.store import new_id, to_cost

DIR = "artifacts/onboarding"  # notas de trabajo: ignoradas por git (lo que queda va al repo)
MAX_QUESTIONS = 8
NOTE_CHARS = 9000  # por nota, en el sobre del redactor
PLAYWRIGHT_SCRATCH = ".playwright-mcp"  # donde el MCP de Playwright deja consola e instantáneas
ARTIFACTS = ("CONTEXT.md", ".specify/memory/constitution.md", "specs/000-linea-base/")
FOCUS = {
    "arquitectura": "Arquitectura: capas y módulos, cómo se relacionan, el recorrido de una "
                    "petición o acción de punta a punta, dependencias externas, cómo arranca.",
    "dominio": "Dominio: entidades, reglas de negocio (validaciones, cálculos, estados y sus "
               "transiciones), glosario del negocio con su significado; sale de modelos, "
               "migraciones, validadores y servicios.",
    "convenciones": "Convenciones: cómo se nombra, se organiza, se testea (herramienta, dónde, "
                    "estilo), se manejan errores y logs, se escriben migraciones y APIs; con "
                    "ejemplos reales (ruta del archivo).",
    "interfaz": "Interfaz: inventario de vistas o pantallas (ruta o URL, archivo que la "
                "implementa, para qué sirve), componentes compartidos, y el sistema visual que "
                "usan: librería de UI, colores, tipografías, radios, espaciados y dónde se "
                "definen (tema, Tailwind, SCSS). Si no hay interfaz, dilo.",
    "riesgos": "Riesgos: zonas frágiles (cambian mucho y tienen pocos tests), TODO/FIXME "
               "relevantes, código muerto, dependencias desactualizadas, secretos o datos "
               "sensibles en el repo, lo que convendría no tocar sin cuidado.",
}
MARKERS = ("package.json", "composer.json", "pyproject.toml", "requirements.txt", "go.mod",
           "Cargo.toml", "pom.xml", "build.gradle", "Gemfile", "angular.json", "artisan",
           "capacitor.config.ts", "ionic.config.json", "tailwind.config.js",
           "tailwind.config.ts", "vite.config.ts", "next.config.js", "Dockerfile",
           "docker-compose.yml", "Makefile", ".gitlab-ci.yml")
AI_FILES = ("CLAUDE.md", "AGENTS.md", ".cursorrules", ".windsurfrules",
            ".github/copilot-instructions.md")
MIGRATIONS = ("database/migrations", "migrations", "prisma/schema.prisma", "alembic",
              "db/migrate")


class OnboardingError(Exception):
    pass


class OnboardQuestions(BaseModel):
    """Lo que el redactor necesita preguntar a la persona."""

    questions: list[Question] = Field(default_factory=list, max_length=MAX_QUESTIONS)
    summary: str = ""


# ---------- estado ----------
def folder(udir: Path) -> Path:
    return udir / DIR


def state(udir: Path) -> dict:
    f = folder(udir) / "estado.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"phase": "explorar", "questions": [], "answers": [], "comments": []}


def save(udir: Path, st: dict) -> None:
    folder(udir).mkdir(parents=True, exist_ok=True)
    st["updated_at"] = datetime.now(UTC).isoformat()
    (folder(udir) / "estado.json").write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                              encoding="utf-8")


def reset(udir: Path) -> None:
    f = folder(udir) / "estado.json"
    f.unlink(missing_ok=True)


def note(udir: Path, name: str) -> str:
    f = folder(udir) / f"{name}.md"
    return f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""


# ---------- reconocimiento (sin modelo) ----------
def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def recon(root: Path) -> str:
    """Lo que el repo declara, sin modelo: stack, scripts, CI, docs, instrucciones para IA,
    entorno, migraciones, tamaño por lenguaje e historia de git."""
    files = git.run(root, "ls-files").splitlines()
    out = ["# Reconocimiento", ""]
    found = [m for m in MARKERS if (root / m).exists()]
    ci = [f for f in files if f.startswith(".github/workflows/")]
    out += ["## Stack y herramientas", "", ", ".join(found) or "(ningún marcador conocido)"]
    if ci:
        out.append("CI: " + ", ".join(ci))
    scripts = {}
    for name in ("package.json", "composer.json"):
        scripts |= {f"{name}: {k}": v for k, v in (_json(root / name).get("scripts") or {}).items()
                    if isinstance(v, str)}
    if (root / "Makefile").is_file():
        text = (root / "Makefile").read_text(encoding="utf-8", errors="replace")
        scripts |= {f"make {t}": "" for t in re.findall(r"^([\w-]+):", text, re.M)}
    if scripts:
        out += ["", "## Comandos que declara el proyecto", ""]
        out += [f"- `{k}`" + (f": `{v}`" if v else "") for k, v in list(scripts.items())[:40]]
    docs = [f for f in files if f.lower().endswith(".md") and not f.startswith(("specs/",
                                                                                   ".specify/"))]
    if docs:
        out += ["", f"## Documentación ({len(docs)} archivos .md)", ""]
        out += [f"- {d}" for d in docs[:25]]
    ai = [f for f in AI_FILES if (root / f).is_file()]
    ai += [f for f in files if f.startswith(".cursor/rules/")]
    if ai:
        out += ["", "## Instrucciones para IA que ya existen (aprovecharlas)", ""]
        out += [f"- {f}" for f in ai]
    env = next((root / n for n in (".env.example", ".env.sample", ".env.dist")
                if (root / n).is_file()), None)
    if env:
        keys = re.findall(r"^\s*([A-Z][A-Z0-9_]+)\s*=", env.read_text(encoding="utf-8",
                                                                      errors="replace"), re.M)
        out += ["", f"## Variables de entorno ({env.name})", "", ", ".join(keys[:60])]
    mig = [m for m in MIGRATIONS if (root / m).exists()]
    if mig:
        out += ["", "## Datos", "", "Migraciones o esquema en: " + ", ".join(mig)]
    lines: Counter = Counter()
    for f in files:
        p = root / f
        ext = p.suffix.lower() or p.name
        try:
            if p.stat().st_size < 1_000_000:
                lines[ext] += p.read_bytes().count(b"\n")
        except OSError:
            continue
    out += ["", "## Tamaño (líneas por tipo de archivo)", "",
            ", ".join(f"{e} {n}" for e, n in lines.most_common(10)) or "(vacío)"]
    out += ["", "## Historia", ""] + _history(root)
    return "\n".join(out) + "\n"


def _history(root: Path) -> list[str]:
    if not git.head_or_none(root):
        return ["(sin commits)"]
    dates = git.run(root, "log", "--format=%as").splitlines()
    authors = set(git.run(root, "log", "--format=%an").splitlines())
    out = [f"{len(dates)} commits desde {dates[-1]} hasta {dates[0]}; {len(authors)} autores."]
    hot = Counter(f for f in git.run(root, "log", "--since=180 days ago", "--name-only",
                                     "--format=").splitlines() if f)
    if hot:
        out.append("Lo que más cambió en 6 meses: "
                   + ", ".join(f"{f} ({n})" for f, n in hot.most_common(10)))
    return out


# ---------- línea base (sin modelo) ----------
def baseline(conn, root: Path, udir: Path, config: dict) -> str:
    """Tests y lint registrados, sobre el código tal como está, antes de que umbra toque nada."""
    head = git.head_or_none(root)
    out = ["# Línea base", "", f"Medida sobre el commit {head[:10] if head else '(ninguno)'}, "
           "antes de que umbra cambie nada.", ""]
    for name in ("test", "lint"):
        if name not in commands.registered(config):
            out.append(f"- **{name}**: no hay comando registrado en `.umbra/project.toml`.")
            continue
        res = commands.run_registered(conn, config, name, root, udir, tested_sha=head)
        ok = res["exit_code"] == 0
        out.append(f"- **{name}** (`{res['command']}`): "
                   + ("pasa." if ok else f"FALLA con exit {res['exit_code']}"
                      + (" (tiempo agotado)" if res["timed_out"] else "") + "."))
        if not ok:
            tail = "\n".join(res["output"].strip().splitlines()[-40:])
            out += ["", "```", tail, "```", ""]
    return "\n".join(out) + "\n"


# ---------- agentes ----------
def agent(root: Path, udir: Path, profile_name: str, title: str, description: str,
          feedback: list[str], output_model: type[BaseModel] | None = None,
          app_url: str | None = None, mcp: dict | None = None):
    """Un agente fuera de una tarea (como el cartógrafo). Devuelve (resultado, invocación).
    `app_url` le da la app levantada (con la acción `browse`); `mcp`, servidores extra."""
    from umbra.adapters import get_adapter
    from umbra.adapters.base import AgentRun
    from umbra.contracts.envelope import Envelope, StageOutput, TaskInfo
    from umbra.contracts.profile import McpServer
    profile = cfg.load_profile(udir, profile_name)
    for name, server in (mcp or {}).items():
        profile.mcp[name] = McpServer(**server)
    invocation = new_id()
    envelope = Envelope(run_id=f"onboarding-{invocation[:8]}", stage="onboarding",
                        attempt_id=invocation, input_sha=git.head_or_none(root) or "",
                        task=TaskInfo(number=0, title=title, description=description),
                        feedback=feedback, app_url=app_url)
    req = AgentRun(envelope, profile, root,
                   udir / "artifacts" / f"{invocation}-onboarding.jsonl",
                   output_model=output_model or StageOutput)
    scratch = root / PLAYWRIGHT_SCRATCH  # registros e instantáneas del navegador: no son trabajo
    existed = scratch.exists()
    try:
        return get_adapter(profile.agent, udir).run(req), invocation
    finally:
        if app_url and not existed:
            shutil.rmtree(scratch, ignore_errors=True)


def record_usage(conn, result, invocation: str, agent_name: str = "claude-code") -> None:
    conn.execute(
        "INSERT INTO usage (id, agent, model, input_tokens, output_tokens, cost, estimated,"
        " invocation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (new_id(), agent_name, result.model, result.input_tokens, result.output_tokens,
         to_cost(result.cost), int(result.estimated), invocation))


def explore(conn, root: Path, udir: Path, origin: str = "cli") -> dict[str, str]:
    """Cinco exploradores de solo lectura en paralelo; cada nota queda en `<foco>.md`. Uno que
    falla no detiene a los demás. Devuelve foco → «ok» o el error."""
    context = [note(udir, "reconocimiento"), note(udir, "linea-base")]
    results: dict[str, tuple] = {}

    def run(focus: str, what: str) -> None:
        try:
            results[focus] = agent(root, udir, "explorer", f"Explorar: {focus}", what, context)
        except Exception as e:  # ponytail: un explorador roto no tumba el onboarding
            results[focus] = (e, None)

    threads = [threading.Thread(target=run, args=item) for item in FOCUS.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    status = {}
    for focus in FOCUS:
        result, invocation = results[focus]
        if isinstance(result, Exception) or not result.ok:
            error = str(result) if isinstance(result, Exception) else result.error
            status[focus] = error or "falló"
            continue
        record_usage(conn, result, invocation)
        body = result.output.summary.strip()
        doubts = result.output.questions
        if doubts:
            body += "\n\n## Dudas que el código no resuelve\n\n" + "\n".join(f"- {q}"
                                                                          for q in doubts)
        (folder(udir) / f"{focus}.md").write_text(f"# {focus.capitalize()}\n\n{body}\n",
                                                  encoding="utf-8")
        status[focus] = "ok"
    add_event(conn, None, "onboarding.explored", origin, status=status)
    return status


def _material(udir: Path, st: dict) -> list[str]:
    blocks = [note(udir, "reconocimiento"), note(udir, "linea-base")]
    blocks += [note(udir, f)[:NOTE_CHARS] for f in FOCUS if note(udir, f)]
    if st.get("answers"):
        blocks.append("# Respuestas de la persona\n\n" + "\n".join(
            f"- {q['question']} → {a}" for q, a in zip(st["questions"], st["answers"],
                                                       strict=False)))
    return [b for b in blocks if b]


def ask(conn, root: Path, udir: Path, st: dict) -> list[dict]:
    result, invocation = agent(
        root, udir, "onboarder", "Preguntas del onboarding",
        f"Con lo explorado, decide qué necesitas preguntar a la persona (máximo "
        f"{MAX_QUESTIONS}) sobre lo que el código no dice. Devuelve `questions`.",
        _material(udir, st), OnboardQuestions)
    if not result.ok:
        raise OnboardingError(result.error or "el redactor no pudo preparar las preguntas")
    record_usage(conn, result, invocation)
    return [q.model_dump() for q in result.output.questions[:MAX_QUESTIONS]]


def write(conn, root: Path, udir: Path, st: dict, origin: str = "cli") -> str:
    """El redactor escribe los artefactos; si toca otra cosa, se restaura y falla."""
    before = _dirty(root)
    feedback = _material(udir, st)
    if st.get("comments"):
        feedback.append("# Cambios que pidió la persona a tu última redacción\n\n"
                        + "\n".join(f"- {c}" for c in st["comments"]))
    result, invocation = agent(root, udir, "onboarder", "Redactar el onboarding",
                               "Escribe o actualiza CONTEXT.md, "
                               ".specify/memory/constitution.md y specs/000-linea-base/ con "
                               "todo lo aprendido y las respuestas de la persona.", feedback)
    others = sorted(p for p in _dirty(root) - before if not p.startswith(ARTIFACTS))
    if others:
        for path in others:
            if git.ok(root, "ls-files", "--error-unmatch", path):
                git.ok(root, "checkout", "--", path)
            else:
                (root / path).unlink(missing_ok=True)
        add_event(conn, None, "onboarding.failed", origin, error=f"tocó {', '.join(others)}")
        raise OnboardingError(f"el redactor tocó archivos que no debía: {', '.join(others)}")
    if not result.ok:
        raise OnboardingError(result.error or "el redactor falló")
    record_usage(conn, result, invocation)
    return result.output.summary


def _dirty(root: Path) -> set[str]:
    """Rutas con cambios sin confirmar (modificadas o nuevas)."""
    head = git.head_or_none(root)
    changed = git.run(root, "diff", "--name-only", "HEAD").splitlines() if head else []
    new = git.run(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return {p.strip() for p in (*changed, *new) if p.strip()}


def written(root: Path) -> list[str]:
    """Los artefactos que existen, para mostrarlos y confirmarlos."""
    out = [a for a in ARTIFACTS[:2] if (root / a).is_file()]
    base = root / ARTIFACTS[2]
    if base.is_dir():
        out += sorted(p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file())
    return out


def approve(conn, root: Path, origin: str = "cli") -> str | None:
    """Confirma los artefactos en la rama actual (sin push). Devuelve el commit o None."""
    files = written(root)
    if not files:
        raise OnboardingError("no hay nada redactado que aprobar")
    if ".umbra/project.toml" in _dirty(root):  # p. ej. el sistema de diseño elegido
        files.append(".umbra/project.toml")
    git.run(root, "add", "--", *files)
    if not git.run(root, "diff", "--cached", "--name-only", "--", *files):
        return None
    git.run(root, "commit", "--no-verify", "-q", "-m", "umbra: onboarding", "--", *files)
    sha = git.head(root)
    add_event(conn, None, "onboarding.approved", origin, files=files, sha=sha)
    return sha
