"""Lectura determinista de una spec de Spec Kit (spec.md y tasks.md). Sin I/O."""

import hashlib
import re
from dataclasses import dataclass, field

_HEAD = re.compile(
    r"^###\s+(?:User Story|Historia(?: de usuario)?)\s+(\d+)\s*[-–—:]\s*(.+?)"
    r"\s*\((?:Priority|Prioridad):\s*P(\d+)\)\s*$", re.I)
_END = re.compile(r"^#{1,3}\s")
_SCEN = re.compile(r"^\*\*(?:Acceptance Scenarios|Escenarios de aceptaci[oó]n)\*\*", re.I)
_REQ_LINE = re.compile(r"^\*\*Requisitos\*\*\s*:\s*(.*)$", re.I)
_REPO_LINE = re.compile(r"^\*\*Repos?\*\*\s*:\s*(.*)$", re.I)  # espacio: dónde se hace
_LABEL = re.compile(r"^\*\*[^*]+\*\*\s*:")
_ITEM =re.compile(r"^\d+\.\s+(.*)$")
_FR = re.compile(r"FR-\d+")
_STEP = re.compile(r"^\s*-\s*\[[ xX]\]\s*T\d+\b.*?\[(US\d+)\]")
_TICKS = re.compile(r"`([^`\n]+)`")
_EXTS = (".py", ".md", ".toml", ".json", ".yml", ".yaml", ".txt", ".ts", ".js", ".sh")


@dataclass
class Story:
    id: str
    title: str
    priority: int
    text: str
    story_hash: str
    scenarios: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)


def _unique(items) -> list[str]:
    return list(dict.fromkeys(items))


def parse_stories(spec_md: str) -> list[Story]:
    lines = spec_md.replace("\r\n", "\n").split("\n")
    stories, i = [], 0
    while i < len(lines):
        m = _HEAD.match(lines[i].strip())
        i += 1
        if not m:
            continue
        j = i
        while j < len(lines) and not _END.match(lines[j]):
            j += 1
        section = lines[i - 1:j]
        text = "\n".join(section).strip()
        scenarios, in_scen, declared, repos = [], False, [], []
        for line in section[1:]:
            s = line.strip()
            if _SCEN.match(s):
                in_scen = True
            elif _LABEL.match(s):
                in_scen = False
                if r := _REQ_LINE.match(s):
                    declared = _FR.findall(r.group(1))
                elif r := _REPO_LINE.match(s):
                    repos = _unique(x.strip(" `") for x in r.group(1).split(",") if x.strip(" `"))
            elif in_scen and (it := _ITEM.match(s)):
                scenarios.append(it.group(1))
            elif in_scen and s and scenarios:
                scenarios[-1] += " " + s
        stories.append(Story(
            id=f"US{m.group(1)}", title=m.group(2).strip(), priority=min(int(m.group(3)), 3),
            text=text, story_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            scenarios=scenarios, requirements=_unique(declared or _FR.findall(text)),
            repos=repos))
        i = j
    return stories


def story_about(text: str) -> str:
    """El relato de la historia (lo que va antes de «Why this priority», escenarios, etc.)."""
    blocks = [b.strip() for b in text.split("\n\n")[1:]]  # el primero es el encabezado
    told = []
    for b in blocks:
        if b.startswith(("**", "#", "---")):
            break
        told.append(" ".join(b.split()))
    return "\n\n".join(told)


def parse_steps(tasks_md: str) -> dict[str, list[str]]:
    steps: dict[str, list[str]] = {}
    for line in tasks_md.replace("\r\n", "\n").split("\n"):
        if m := _STEP.match(line):
            steps.setdefault(m.group(1), []).append(line.strip())
    return steps


def step_paths(steps: list[str]) -> list[str]:
    """Rutas citadas entre comillas invertidas en los pasos (no comandos)."""
    found = (t.strip() for s in steps for t in _TICKS.findall(s))
    return _unique(p for p in found if " " not in p and ("/" in p or p.endswith(_EXTS)))
