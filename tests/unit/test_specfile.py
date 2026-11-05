from umbra.management.specfile import parse_steps, parse_stories, step_paths

EN = """# Spec

### User Story 1 - Crear cosas (Priority: P1)

Texto uno. Cubre FR-001 y FR-002, también FR-001.

**Acceptance Scenarios**:

1. **Given** a, **When** b,
   **Then** c
2. **Given** d, **When** e, **Then** f

### Edge Cases

otra cosa
"""

ES = """### Historia 2 - Ver cosas (Prioridad: P4)

Texto dos.

**Escenarios de aceptación**:

1. **Dado** x, **Cuando** y, **Entonces** z

**Requisitos**: FR-007, FR-008
"""


def test_english_story_with_scenarios_and_cited_requirements():
    [s] = parse_stories(EN)
    assert (s.id, s.title, s.priority) == ("US1", "Crear cosas", 1)
    assert s.scenarios == ["**Given** a, **When** b, **Then** c",
                           "**Given** d, **When** e, **Then** f"]
    assert s.requirements == ["FR-001", "FR-002"]
    assert "Edge Cases" not in s.text


def test_spanish_story_declared_requirements_and_priority_cap():
    [s] = parse_stories(ES.replace("\n", "\r\n"))
    assert (s.id, s.priority) == ("US2", 3)
    assert s.requirements == ["FR-007", "FR-008"]
    assert len(s.scenarios) == 1


def test_hash_stable_and_sensitive():
    a = parse_stories(EN)[0].story_hash
    assert a == parse_stories(EN)[0].story_hash
    assert a != parse_stories(EN.replace("Texto uno", "Texto UNO"))[0].story_hash


def test_no_stories():
    assert parse_stories("# Solo una spec\n\ntexto") == []


def test_steps_grouped_and_paths():
    md = ("- [ ] T001 [US1] Crear `src/a.py` y `uv run pytest`\n"
          "- [x] T002 [P] [US2] Editar `b.md`\n- [ ] T003 sin historia\n")
    steps = parse_steps(md)
    assert set(steps) == {"US1", "US2"}
    assert step_paths(steps["US1"]) == ["src/a.py"]
    assert step_paths(steps["US2"]) == ["b.md"]
