import io

from rich.console import Console

from umbra.cli.explain import renderable
from umbra.contracts.plan import PlanOutput, ProposedTask
from umbra.management.planning import insert_proposals
from umbra.management.specfile import parse_stories, story_about
from umbra.unified.explain import explain_number

TECH = "Crear `src/x.py` con `parse_question` y eventos TurnEnd"
PLAIN = "Permite que umbra converse con el asistente y reconozca sus preguntas."


def text_of(exp, **kw) -> str:
    c = Console(file=io.StringIO(), width=120, color_system=None, record=True)
    c.print(renderable(exp, **kw))
    return c.export_text()


def test_situation_speaks_plainly_and_keeps_the_technical_view(env):
    env.umbra("task", "add", "Motor", "-d", TECH, "--about", PLAIN, "-a", "a", "-a", "b")
    task = env.conn.execute("SELECT * FROM task WHERE number = 1").fetchone()
    exp = explain_number(env.conn, env.root / ".umbra", task)

    plain = text_of(exp, compact=True)  # el panel Situación de watch
    assert PLAIN in plain and "parse_question" not in plain
    assert "Se comprobará con 2 criterios" in plain

    technical = text_of(exp, compact=True, technical=True)  # tecla t
    assert "parse_question" in technical and "• a" in technical

    full = text_of(exp)  # umbra explain: todo, con lo técnico aparte
    assert PLAIN in full and "Indicaciones técnicas para el agente" in full
    assert "parse_question" in full


def test_without_about_the_description_is_shown_as_before(env):
    env.umbra("task", "add", "Vieja", "-d", TECH, "-a", "a")
    task = env.conn.execute("SELECT * FROM task WHERE number = 1").fetchone()
    assert "parse_question" in text_of(explain_number(env.conn, env.root / ".umbra", task),
                                       compact=True)


def test_about_can_be_edited(env):
    env.umbra("task", "add", "Motor", "-d", TECH)
    env.umbra("task", "edit", "1", "--about", PLAIN)
    assert env.conn.execute("SELECT about FROM task").fetchone()[0] == PLAIN


def test_proposed_tasks_keep_their_plain_explanation(env):
    conn = env.conn
    plan = PlanOutput(tasks=[ProposedTask(title="t", about=PLAIN, description=TECH,
                                          acceptance=["a"], scope=[], priority=2,
                                          depends_on=[])], questions=[])
    insert_proposals(conn, None, plan)
    assert conn.execute("SELECT about, description FROM task").fetchone()[:] == (PLAIN, TECH)


def test_story_about_is_the_story_narrative():
    spec = """### User Story 1 - Exportar (Priority: P1)

Quien factura descarga sus facturas en PDF
para enviarlas sin salir de la app.

**Why this priority**: es lo que más piden.

**Acceptance Scenarios**:

1. **Given** una factura, **When** exporta, **Then** obtiene un PDF.
"""
    story = parse_stories(spec)[0]
    assert story_about(story.text) == ("Quien factura descarga sus facturas en PDF para "
                                       "enviarlas sin salir de la app.")
