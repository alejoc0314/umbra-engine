"""Política de diff: protege los tests existentes y las rutas protegidas.

Añadir tests nuevos (aunque sea dentro de un archivo de tests que ya existía) está permitido.
Se bloquea lo que puede debilitar la red de seguridad: borrar un archivo de tests, quitar o
cambiar líneas existentes, o añadir saltos (skip/xfail/only) que desactivan tests.
"""

import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

DEFAULT_PROTECTED = (".umbra/", ".github/workflows/")
_TEST_NAME = re.compile(r"(^test_.*|.*_test\.[^.]+$|.*\.(test|spec)\.[^.]+$)")
# saltos y focos que desactivan tests en Python, JS/TS, PHP y Java
SKIP_MARKERS = re.compile(
    r"(pytest\.mark\.(skip|skipif|xfail)|pytest\.skip\(|@unittest\.skip|unittest\.skip"
    r"|\b(it|test|describe)\.(skip|only)\(|\bx(it|describe|test)\(|\bf(it|describe)\("
    r"|markTestSkipped|markTestIncomplete|@group\s+skip|@Disabled\b|@Ignore\b)")


@dataclass
class Violation:
    code: str  # protected_path | test_deleted | test_changed | test_skipped
    path: str
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


_IMPORT = re.compile(r"^\s*(from\s+\S+\s+import\b|import\b|use\b|require\b|const\s.*require\()")
_TOKENS = re.compile(r"[A-Za-z_$][\w$]*")


def weakening_removals(removed: list[str], added: list[str]) -> list[str]:
    """Líneas quitadas que de verdad se pierden. Un import ampliado (otra línea añadida conserva
    todos sus nombres, p. ej. `import add` → `import add, mean`) no cuenta; las líneas en
    blanco tampoco."""
    lost = []
    for line in removed:
        if not line.strip():
            continue
        if _IMPORT.match(line):
            names = set(_TOKENS.findall(line))
            if any(_IMPORT.match(a) and names <= set(_TOKENS.findall(a)) for a in added):
                continue
        lost.append(line)
    return lost


def is_test_file(path: str) -> bool:
    p = PurePosixPath(path)
    in_test_dir = bool({"tests", "test", "__tests__"} & set(p.parts[:-1]))
    return in_test_dir or bool(_TEST_NAME.match(p.name))


def check_diff(changes: list[tuple[str, str]], protected=DEFAULT_PROTECTED,
               test_edits: dict[str, tuple[list[str], list[str]]] | None = None,
               allowed: tuple[str, ...] | list[str] = ()) -> list[Violation]:
    """changes: (estado git A/M/D, ruta). test_edits: ruta → (líneas quitadas, añadidas) de los
    tests modificados. Sin esa información, toda modificación de un test se bloquea.
    allowed: rutas (o prefijos) que la persona autorizó cambiar en esta tarea."""
    violations = []
    for status, path in changes:
        if any(path == a or path.startswith(a) for a in allowed):
            continue  # autorizado por la persona para esta tarea
        if any(path.startswith(p) for p in protected):
            violations.append(Violation("protected_path", path,
                                        f"ruta protegida modificada: {path}"))
        elif not is_test_file(path) or status[0] not in "DM":
            continue
        elif status[0] == "D":
            violations.append(Violation("test_deleted", path,
                                        f"test existente borrado: {path}"))
        elif test_edits is None or path not in test_edits:
            violations.append(Violation("test_changed", path,
                                        f"test existente modificado: {path}"))
        else:
            removed, added = test_edits[path]
            if lost := weakening_removals(removed, added):
                violations.append(Violation(
                    "test_changed", path,
                    f"test existente modificado: {path} ({len(lost)} líneas quitadas o cambiadas,"
                    f" p. ej. `{lost[0].strip()}`)"))
            elif match := SKIP_MARKERS.search("\n".join(added)):
                violations.append(Violation(
                    "test_skipped", path,
                    f"test existente desactivado: {path} (se añadió `{match.group(0)}`)"))
    return violations
