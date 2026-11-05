# Feature Specification: Diseñador estándar

**Feature Branch**: `028-disenador-estandar`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Creemos el perfil del diseñador de forma estandarizada para todos,
pero sin atarlo a una herramienta específica: que cada quien lo conecte a lo que quiera (Figma,
Pencil u otra); nosotros lo conectamos con nuestra herramienta."

## Contexto

Con las specs 026 y 027, Diseñar solo corría si alguien instalaba un perfil `designer`. Para
que sirva a cualquiera que use umbra, el diseñador debe venir incluido y funcionar sin ninguna
herramienta de diseño. Quien tenga una herramienta con servidor MCP debe poder conectarla sin
reescribir el perfil.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Diseñar sin instalar nada (Priority: P1)

Una tarea de interfaz pasa por Diseñar con el diseñador que trae umbra. Diseña en HTML/CSS,
fotografía cada pantalla con el navegador en `design/png/` y deja `design/sistema.md` la
primera vez.

**Acceptance Scenarios**:

1. **Given** un proyecto sin configuración de diseño, **When** una tarea de interfaz corre
   `feature`, **Then** el diseñador estándar recibe un navegador que puede abrir archivos
   locales y guarda las capturas en `design/png/`.

---

### User Story 2 - Conectar mi herramienta y mis guías (Priority: P1)

En `[design]` (en `~/.umbra/local.toml` o en el proyecto), la persona declara servidores MCP y
guías. El diseñador los recibe sin tocar su perfil; el crítico también lee las guías.

**Acceptance Scenarios**:

1. **Given** `[design.mcp.lienzo]` y `guides = [...]`, **Then** el diseñador arranca con
   `lienzo` además del navegador, y las guías llegan en el sobre del diseñador y del crítico.
2. **Given** una guía que no existe, **Then** se ignora sin error.

### Edge Cases

- Windows sin Google Chrome: el navegador es Edge (también en Verificar).
- Quien quiera otro diseñador completo pone su `designer.toml` en el proyecto, en `~/.umbra` o
  en un paquete, que tienen prioridad sobre el de umbra.

## Requirements *(mandatory)*

- **FR-001**: umbra MUST incluir el perfil `designer` (Opus, solo `design/`, acción `render`).
- **FR-002**: La acción `render` MUST dar al agente Playwright con acceso a archivos locales y
  capturas en `design/png/`.
- **FR-003**: `[design] guides` y `[design.mcp.<nombre>]` MUST llegar al diseñador; las guías
  también al crítico.
- **FR-004**: En Windows, Playwright MUST usar Edge.
- **FR-006**: `[design] starter` MUST copiarse una sola vez a `design/<proyecto>.<ext>` antes de
  diseñar, si design/ aún no tiene un archivo de ese tipo.
- **FR-005**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Con agentes falsos y un `project.toml` con `[design]`, el diseñador arranca con
  Opus, la herramienta declarada y el navegador; la guía aparece en el sobre del diseñador y
  del crítico.
- **SC-002**: Todas las pruebas anteriores pasan.
