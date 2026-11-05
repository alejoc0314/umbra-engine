# Feature Specification: E5 — Endurecimiento y vista en vivo

**Feature Branch**: `006-e5-hardening`
**Created**: 2026-10-29
**Status**: Draft
**Input**: Entrega E5 de `docs/design.md`: `umbra watch`, Docker opcional, escaneo de secretos y
SAST como etapa, aviso por configuración de agentes del repo, métricas y guía de uso.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver el motor en vivo (Priority: P1)

`umbra watch` muestra en la terminal las tareas, la ejecución seleccionada con sus etapas
(duración y costo) y el registro de eventos, actualizado sin recargar.

### User Story 2 - Escanear antes de integrar (Priority: P1)

Una etapa `scan` sin agente revisa el diff: un secreto confirmado bloquea siempre; los comandos
SAST registrados que fallan producen hallazgos que devuelven la tarea a BUILD como en REVIEW.

**Acceptance Scenarios**:

1. **Given** un diff que añade una clave privada o un token, **Then** la ejecución queda
   `BLOCKED` con un hallazgo `critical`, sin PR.
2. **Given** un comando SAST registrado que termina con código distinto de 0, **Then** se
   registra un hallazgo `high` con su salida y la tarea vuelve a BUILD.

### User Story 3 - Aislar comandos del proyecto (Priority: P2)

Con `[blocks] isolation = "docker"`, los comandos registrados (tests, lint, SAST) corren en un
contenedor efímero sin red por defecto, con límites de CPU, memoria y procesos.

### User Story 4 - Avisar sobre configuración de agentes del repo (Priority: P2)

Si el repo trae `.claude/settings.json` o `.mcp.json`, `umbra run` se niega hasta que el
proyecto declare `[policy] trust_repo_agent_config = true` o se pase `--trust-repo-config`,
porque Claude Code en modo `-p` los carga sin pedir confianza.

### User Story 5 - Medir (Priority: P2)

`umbra metrics` muestra por tarea y en total: tiempo hasta PR, tiempo hasta merge, costo,
ciclos de corrección, aceptación inicial y costo por entrega.

## Requirements *(mandatory)*

- **FR-001**: `umbra watch` MUST leer el almacén y refrescarse periódicamente, sin escribir.
- **FR-002**: La etapa `scan` MUST bloquear cualquier secreto confirmado y nunca permitir
  autoexcepción del agente.
- **FR-003**: Los comandos SAST MUST configurarse en `[scan] commands`.
- **FR-004**: `isolation = "docker"` MUST aplicar a los comandos registrados con red deshabilitada
  por defecto y límites de recursos.
- **FR-005**: `umbra run` MUST negarse ante configuración de agentes del repo no confiada.
- **FR-006**: `umbra metrics` MUST calcularse solo con datos del almacén, con `--json`.
- **FR-007**: MUST existir una guía de uso de punta a punta.

## Success Criteria *(mandatory)*

- **SC-001**: Todas las pruebas de aceptación pasan.
- **SC-002**: Un secreto añadido por un agente nunca llega a un PR.

## Assumptions

- Los agentes (Claude Code, Codex) siguen ejecutándose en el host con sus logins; el
  contenedor aplica a los comandos del proyecto, que es donde corre código del repositorio.
- El escáner de secretos integrado es un conjunto de patrones de alta precisión; herramientas
  más completas (gitleaks, semgrep) se registran como comandos.
