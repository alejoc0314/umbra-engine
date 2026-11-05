---

description: "Tareas de memoria de decisiones y mapa del repositorio"
---

# Tasks: Memoria de decisiones y mapa del repositorio

**Input**: [spec.md](spec.md), [plan.md](plan.md)

> **Para `umbra spec tasks`**: una tarea de umbra por fase (Fase 1 … Fase 4), en este orden, cada
> una dependiente de la anterior. Cada fase se puede mezclar sola: deja `uv run pytest -q` y
> `uv run ruff check .` en verde.

Reglas para todas las fases: las pruebas no usan red ni modelos (constitution); usan los
agentes falsos de `tests/fakes/` con el fixture `env` de `tests/acceptance/conftest.py`
(`env.umbra(...)`, `env.mode(...)` para el `claude` falso, `env.codex_mode(...)` para el Codex
falso: `high:<mensaje>` y `medium:<mensaje>` producen un hallazgo con ese texto). Los mensajes a
la persona van en español y en lenguaje llano. Sin dependencias nuevas. Cada fase añade su línea
al final de «## Sin publicar» en `CHANGELOG.md` solo si cambia algo visible para quien usa umbra.

## Format: `[ID] [P?] [Story] Description`

---

## Fase 1: Lo aprendido se escribe y se reconstruye (US1)

**Objetivo**: `.umbra/aprendido.md` existe, se regenera desde los eventos y se puede ver.

- [ ] T001 [US1] Crear `src/umbra/management/memory.py` con: `normalize(text) -> str`
  (minúsculas, quita ` (archivo:línea)`, colapsa espacios, quita puntuación final);
  `entries(conn) -> dict[str, list[dict]]` que lee los eventos `finding.decided` (payload:
  `decision`, `reason`, `message`, `task`, `actor`), `task.answered` (payload `answer`, con la
  pregunta tomada del último `run.blocked` de esa ejecución con `code = agent_questions`) y
  `policy.allowed` (payload `paths`, `number`) con su `created_at`, agrupados en las secciones
  `waived`, `deferred`, `answers`, `allowed`; `render(entries) -> str` con el formato del
  plan.md (`## Revisión: no pedir`, `## Para después`, `## Respuestas dadas`,
  `## Rutas autorizadas`, una línea `- <texto> (tarea N, AAAA-MM-DD, motivo)` por entrada, más
  recientes primero); `rebuild(conn, udir) -> Path` que escribe `udir / "aprendido.md"`;
  `load(udir, limit=4000) -> str` que devuelve el texto acotado (recorta por líneas completas) o
  `""` si no existe; `decided_messages(conn) -> set[str]` con los textos normalizados de los
  hallazgos `waived` y `deferred`.
- [ ] T002 [US1] Llamar a `memory.rebuild(ctx.conn, ctx.udir)` al final de
  `service.decide_findings`, `service.answer` y `service.allow_paths` en `src/umbra/service.py`
  (nunca debe lanzar: envolver en `try/except OSError` y registrar evento `memory.failed`).
- [ ] T003 [US1] Comandos `umbra memory show` (imprime `aprendido.md` o «umbra aún no ha
  aprendido nada en este repo») y `umbra memory rebuild` en un módulo nuevo
  `src/umbra/cli/memory.py`, registrados en `src/umbra/cli/main.py` como `app.add_typer(memory.app,
  name="memory")`; ambos con `--json`.
- [ ] T004 [US1] Pruebas en `tests/unit/test_memory.py` (normalize, render, rebuild idéntico
  desde eventos sembrados con `add_event`) y en `tests/acceptance/test_memory.py`: tras
  `env.umbra("finding", "waive", "1", "-m", "no aplica")` sobre una tarea frenada por el Codex
  falso (`env.codex_mode("high:falta validar entradas", ...)` con rutina `feature`), existe
  `.umbra/aprendido.md` con esa línea y `umbra memory show` la imprime.

**Checkpoint**: lo aprendido se ve y se reconstruye.

---

## Fase 2: Los agentes reciben lo aprendido y no repiten lo decidido (US1)

- [ ] T005 [US1] En `src/umbra/contracts/envelope.py`, campo `project_notes: str | None = None`
  en `Envelope` (texto con dos bloques: «Mapa del repositorio» = `CONTEXT.md` de la raíz acotado
  a 6 000 caracteres si existe, y «Aprendido en este repo» = `memory.load(udir)`); en
  `src/umbra/routines/engine.py`, `Engine.agent_attempt` lo rellena con una función
  `project_notes(root, udir) -> str | None` de `memory.py`; `adapters/base.render_prompt` lo
  incluye antes del JSON del sobre con la frase «Contexto del proyecto y decisiones ya tomadas por
  la persona responsable (respétalas):».
- [ ] T006 [US1] En `Engine.judge` y `Engine.finding_rounds` (`src/umbra/routines/engine.py`),
  excluir de los bloqueantes los hallazgos cuyo `memory.normalize(message)` esté en
  `memory.decided_messages(conn)` (hoy solo se excluyen los decididos en la misma ejecución);
  registrar en el evento `review.result` cuántos se ignoraron por memoria (`remembered=N`).
- [ ] T007 [US1] En `src/umbra/defaults/profiles/reviewer-strict.md` y `builder-tdd.md`, una
  línea: «El sobre puede traer `project_notes`: decisiones ya tomadas por la persona; no las
  vuelvas a pedir ni a preguntar.»
- [ ] T008 [US1] Pruebas en `tests/acceptance/test_memory.py`: (a) tarea 1 frenada por el
  hallazgo «falta validar entradas», `finding waive`, `retry`; tarea 2 con el mismo Codex falso
  repitiendo el hallazgo llega a `WAITING_APPROVAL` sin frenarse y el evento `review.result` trae
  `remembered: 1`; (b) el prompt del constructor (`env.claude_calls()`) contiene «Aprendido en
  este repo» y la respuesta dada con `umbra task answer`.

**Checkpoint**: una decisión vale para todas las tareas del repo.

---

## Fase 3: El mapa del repositorio (US2)

- [ ] T009 [US2] Campo `allowed_paths: list[str] = []` en `src/umbra/contracts/profile.py`; en
  `src/umbra/adapters/claude_code.allowed_tools`, si el perfil tiene `edit` y `allowed_paths`, en
  vez de `Edit`/`Write` genéricos emitir `Edit(<ruta>)` y `Write(<ruta>)` por cada ruta. Perfil
  `src/umbra/defaults/profiles/cartographer.toml` (`agent = "claude-code"`, `roles = ["context"]`,
  `model = "claude-sonnet-5-5"`, `actions = ["read", "search", "edit"]`, `allowed_paths =
  ["CONTEXT.md"]`, `output = "stage-output/v1"`, límites 5 min / 1 USD) e instrucciones
  `cartographer.md`: escribir `CONTEXT.md` con secciones fijas (Qué es, Cómo está organizado,
  Cómo se corre y se prueba, Convenciones, Dónde mirar para…) entre marcas `<!-- umbra:inicio -->`
  y `<!-- umbra:fin -->`, conservando lo que haya fuera de las marcas; en español; sin inventar.
- [ ] T010 [US2] `service.context_build(ctx, origin="cli") -> dict` en `src/umbra/service.py`:
  ejecuta el perfil `cartographer` sobre `ctx.root` (como hace `planning.propose`: `AgentRun`
  con un `Envelope` de etapa `context`, registra `usage`), comprueba con
  `git.changed_files(root, "HEAD")`/`git status --porcelain` que solo cambió `CONTEXT.md`
  (si tocó otra cosa: restaurar con `git checkout -- <ruta>` y fallar con `OpError`), y hace
  `git commit` de `CONTEXT.md` con «umbra: CONTEXT.md al día» solo si cambió; evento
  `context.updated` (o `context.failed`). Comando `umbra context build` en
  `src/umbra/cli/memory.py` (grupo `context`).
- [ ] T011 [US2] Tras integrar (`service.approve` en `src/umbra/service.py`, después del merge y
  del `fast_forward`): si la copia local quedó al día, llamar `context_build` en un hilo
  (`threading.Thread(daemon=True)`) para no frenar la respuesta; el resultado queda como evento.
  Con `[context] auto = false` en `project.toml` no se hace.
- [ ] T012 [US2] Modo `context` en `tests/fakes/claude.py`: escribe un `CONTEXT.md` de ejemplo
  con las marcas y responde `done`. Pruebas en `tests/acceptance/test_context.py`: `umbra context
  build` crea y commitea `CONTEXT.md` (y no commitea otros cambios); con `CONTEXT.md` presente, el
  prompt de cualquier etapa contiene «Mapa del repositorio»; con `trust` de un agente que escribe
  otro archivo (modo `touch`), `context build` falla y restaura.

**Checkpoint**: los agentes arrancan con el mapa.

---

## Fase 4: Verlo desde watch y documentar (US3)

- [ ] T013 [US3] En `src/umbra/cli/watch.py` y `watch_data.py`: panel derecho `memory` (tecla
  `m`, añadida a `PANELS`/`PANEL_KEYS`) que muestra `aprendido.md` (o el aviso de que no hay nada)
  en un `Static` dentro de `VerticalScroll#memory` del `ContentSwitcher#right`; el `Loader` lo
  lee solo cuando ese panel está activo (`want == "memory"`), con caché por `mtime`.
- [ ] T014 [US3] `docs/usage.md`: sección «Lo que umbra aprende» (aprendido.md, CONTEXT.md,
  `m`, `umbra memory`, `umbra context build`, `[context] auto`); `CHANGELOG.md` en «Sin
  publicar».
- [ ] T015 `uv run pytest -q` y `uv run ruff check .` en verde; instantáneas de watch sin cambios
  (no se toca la pantalla principal).
