# Implementation Plan: E4 — Integración abierta de agentes

**Branch**: `005-e4-open-integration` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

## Summary

Registro de agentes por manifiesto (`agents/<nombre>/agent.toml` en `~/.umbra/` o `.umbra/`),
adaptador `script` con protocolo JSON por stdin/stdout, verificación con sello
(`verified.json` con el sha256 del manifiesto), `get_adapter(nombre, udir)` que consulta el
registro, y comandos `agent` y `profile`.

## Research (decisiones)

| Tema | Decisión |
| --- | --- |
| Manifiesto | `name`, `adapter = "script"`, `command = [...]` con marcador `{agent_dir}`, `description` |
| Protocolo script | stdin: `{"envelope", "profile", "instructions", "output_schema", "allowed_commands"}`; stdout: última línea JSON `{"output": {...}, "session_id"?, "cost"?, "input_tokens"?, "output_tokens"?}` |
| Verificación | `umbra agent test` crea un repo git temporal con un cambio de ejemplo, ejecuta el agente con un sobre de etapa `review` y valida la salida; guarda `verified.json` con el sha256 del manifiesto |
| Integrados | `claude-code` y `codex` no requieren sello (los cubre la suite); sí `umbra agent test` opcional |
| Aplicación | El motor rechaza (`FAILED`) agentes registrados sin sello vigente |

## Constitution Check

IV: el núcleo resuelve por nombre y el sello hace cumplir "MUST pasar `umbra agent test`".
X: sin plugins dinámicos de Python; un ejecutable con JSON basta. Sin violaciones.
