# Implementation Plan: Paquetes, MCP en el perfil y la etapa Diseñar

**Branch**: `026-paquetes-y-diseno` | **Spec**: [spec.md](spec.md)

## Summary

- **Paquetes**: `config.packs()` = carpetas de `~/.umbra/packs/`; `_search`/`list_names` buscan
  en proyecto > `~/.umbra` > paquetes > defaults; `playbooks.available` igual.
  `management/packs.py` (`sync` con el `git_sync` de playbooks, `installed`), CLI
  `umbra pack sync|list`.
- **MCP**: `Profile.mcp: dict[str, McpServer]`. `claude_code.mcp_servers(req)` une Playwright
  (con `browse` y app) y los del perfil, resolviendo `{profile_dir}` y `{workspace}`; un solo
  `--mcp-config` + `--strict-mcp-config` + `mcp__<nombre>` en `--allowedTools`.
- **Diseñar**: `StageOutput.needs_design` (planificador) e `images` (diseñador); `plan.ready`
  guarda `needs_design`. `Engine.design`: salta sin interfaz o sin perfil; intento `design` con
  la petición de cambios de la persona; rutas fuera de `design/` → `design_outside`; commit;
  sin pantallas → `design_empty`; artefactos `design`; `design.ready`; `BLOCKED design_review`
  (o `design.approved` automático). `Envelope.design` = pantallas aprobadas para build/verify;
  `render_prompt` pide maquetar fiel y comparar.
- **Decidir**: `service.design_approve` (evento + reintento desde la etapa siguiente) y
  `design_changes` (evento + reintento desde `design`); CLI `umbra design ok|cambios`; `watch`
  (`a` aprueba, `r` pide cambios); Telegram: fotos antes de la decisión, botón `dok:N`,
  responder → `dchg:N:texto`. `explain`: etapa, motivos y narración.

## Constitution Check

III (la persona decide el diseño, como decide la integración) · IV (los agentes siguen siendo
intercambiables: el diseñador es un perfil más; lo privado llega por paquetes, no por código) ·
VI (Verificar compara con lo aprobado). Sin enmienda.

## Pruebas

`tests/acceptance/test_design.py`: salto sin diseñador/sin interfaz, flujo completo con
Telegram, límite a `design/`, CLI y paquetes. El `claude` falso gana los modos `plan_ui`,
`design` y `design_code`.
