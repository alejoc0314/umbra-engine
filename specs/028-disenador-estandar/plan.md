# Implementation Plan: Diseñador estándar

**Branch**: `028-disenador-estandar` | **Spec**: [spec.md](spec.md)

## Summary

- `defaults/profiles/designer.toml|md`: Claude Code con `claude-opus-5-5`, acciones
  `read, search, edit, render`, `allowed_paths = ["design/**"]`. Las instrucciones explican
  cómo diseñar con una herramienta conectada o, sin ella, en HTML/CSS fotografiado con
  Playwright; crear o respetar `design/sistema.md`; la vara de calidad; y qué devolver.
- `contracts/profile.ACTIONS` gana `render`. `claude_code.playwright_server(dir, files)` añade
  `--browser msedge` en Windows y `--allow-unrestricted-file-access` con `files`; `render`
  monta ese servidor con `--output-dir <workspace>/design/png`.
- `Engine.design` suma `[design.mcp.*]` (configuración ya combinada: proyecto + `local.toml`)
  a `profile.mcp`; `Engine.design_guides()` lee `[design] guides` (con `~` o relativas al
  proyecto, 12 000 caracteres por guía) y `agent_attempt` las pone, con el gusto, en las notas
  de `design` y `critic`.

## Constitution Check

IV (agentes y herramientas intercambiables: el diseñador no se ata a ninguna) · III (la persona
decide qué herramienta y qué guías). Sin enmienda.

## Pruebas

`tests/acceptance/test_design.py`: diseñador estándar con `[design]` en el proyecto (Opus,
herramienta declarada, navegador con archivos locales, guías en diseñador y crítico); la prueba
de «sin diseñador» usa un perfil inexistente.
