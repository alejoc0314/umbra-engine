# Feature Specification: `umbra new` con playbooks y `watch --all`

**Feature Branch**: `021-umbra-new`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "`umbra new cliente-x --stack laravel` crea el repo (local +
GitHub), el CI, el `project.toml` con tests/lint/dev, perfiles y rutinas del equipo, el
`CONTEXT.md` inicial y abre la primera conversación de spec. 30 minutos hasta la primera
tarea. Y con 3 a 5 repos activos, `umbra watch --all`."

## Contexto

Arrancar un cliente nuevo hoy son pasos sueltos: crear el repo, el andamiaje del stack, el
CI, las convenciones para los agentes, `umbra init` y ajustar comandos. Un playbook por stack
lo deja en un comando. Y con varios repos activos, hace falta un sitio desde el que ver cuál te
necesita y entrar en él.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Un proyecto nuevo en un comando (Priority: P1)

`umbra new <nombre> --stack <playbook>` crea la carpeta con git, ejecuta el andamiaje del
playbook, copia sus archivos (CI, `AGENTS.md`), escribe `.umbra/project.toml` con sus comandos
y rutina, hace el primer commit, crea el repo privado en GitHub y publica, genera `CONTEXT.md`
con el cartógrafo y, con `--idea`, abre la primera conversación de spec.

**Acceptance Scenarios**:

1. **Given** un playbook `python`, **When** `umbra new demo --stack python`, **Then** el repo
   queda con CI, `AGENTS.md`, `project.toml`, `CONTEXT.md`, remoto y un commit limpio, y su
   primera tarea llega a «Espera tu aprobación».
2. **Given** `--no-remote --no-context`, **Then** no se crea repo remoto ni se llama a ningún
   agente.
3. **Given** una carpeta no vacía o un stack sin playbook, **Then** umbra lo dice y no toca nada.

---

### User Story 2 - Playbooks del equipo (Priority: P2)

Los playbooks de umbra (`python`, `node`, `laravel`) se pueden pisar o ampliar con los del
equipo en `~/.umbra/playbooks/<stack>/`; `umbra playbook sync <repo>` los trae o actualiza y
`umbra playbook list` muestra los disponibles.

---

### User Story 3 - Todos los repos en una pantalla (Priority: P2)

`umbra watch --all` lista los repos con umbra (los registran `umbra init` y `umbra new`): cuántas
tareas te necesitan, cuántas en marcha y el gasto; Enter entra en el `watch` de ese repo y `P`
vuelve a la lista. `umbra projects` es la misma lista en la terminal.

### Edge Cases

- El andamiaje manda: los archivos del playbook solo se copian si no existen ya.
- Un repo que ya no existe sale del índice solo.
- Si GitHub o el cartógrafo fallan, el proyecto queda creado igual y se informa.

## Requirements *(mandatory)*

- **FR-001**: `umbra new` MUST crear el repo completo descrito en la historia 1.
- **FR-002**: Los playbooks MUST cargarse de `~/.umbra/playbooks` con prioridad sobre los de
  umbra; `playbook sync` MUST clonar o actualizar un repo git ahí.
- **FR-003**: `umbra init` y `umbra new` MUST registrar el repo en `~/.umbra/projects.json`.
- **FR-004**: `umbra watch --all` y `umbra projects` MUST mostrar los repos con sus conteos.
- **FR-005**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios.

## Success Criteria *(mandatory)*

- **SC-001**: Con los falsos (`gh repo create`, cartógrafo y constructor) y un playbook sin red,
  `umbra new demo --stack python` deja un repo listo cuya primera tarea llega a «Espera tu
  aprobación».
- **SC-002**: Todas las pruebas anteriores pasan.
