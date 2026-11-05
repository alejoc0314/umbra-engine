# Implementation Plan: Sistemas de diseño y réplica del diseño actual

**Branch**: `031-sistemas-y-replica` | **Spec**: [spec.md](spec.md)

## Summary

- `management/design_systems.py`: `catalog()` (de `~/.umbra/design/*/sistema.toml` y
  `~/.umbra/packs/*/design/*/sistema.toml`: `nombre`, `descripcion`, `guias`, `starter`),
  `resolved(config)` (guías del sistema + las de `[design] guides`, y el `starter` del sistema si
  el proyecto no define uno), `needs_choice(config)`, `set_system(root, nombre)` (escribe
  `[design] system` en `.umbra/project.toml` sin perder lo demás).
- `Engine.design_guides`/`design_starter` usan `resolved`; además pasan al diseñador
  `specs/000-linea-base/vistas.md` y `design/actual/indice.md` si existen. `designer.md`:
  reconstruir editable la vista `Actual · X` antes de cambiarla.
- Elegir: `umbra spec new` pregunta antes de abrir la conversación; en Telegram, `/spec` envía
  botones `ds:<sistema>` y arranca la spec al elegir; el onboarding añade la pregunta del
  sistema al principio de sus preguntas. `umbra design sistema [nombre]`, `umbra design
  sistemas`, `/sistema [nombre]`.
- Réplica (`management/replica.py`): requiere `dev`; levanta la app, corre el agente
  `replicator` (Sonnet; `read`, `edit` en `design/**`, `browse`, más `[design.mcp.*]`) con el
  inventario, `[design.replica]` (usuario y clave desde una variable de entorno) y las guías;
  restaura lo que no sea `design/`; `accept` hace commit, `discard` restaura. CLI
  `umbra design replicar [-y]`; Telegram `/replicar` con fotos y botones `dr:approve|discard`, y
  oferta al aprobar el onboarding.

## Constitution Check

III (la persona elige el sistema y aprueba la réplica) · IV (agnóstico: la herramienta es la que
cada uno conecte; sin ella, capturas e índice en `design/`) · V (agentes acotados; la clave de
prueba se documenta como riesgo). Sin enmienda.

## Pruebas

`tests/acceptance/test_design_systems.py`: catálogo, elección por CLI y Telegram, guías y archivo
base del sistema en el sobre, pregunta del onboarding, réplica con `dev` falso (aprobar,
descartar, fuera de `design/`).
