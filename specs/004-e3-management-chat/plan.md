# Implementation Plan: E3 — Management y conversación

**Branch**: `004-e3-management-chat` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

## Summary

`umbra plan` guarda la spec (versión + hash) y llama al perfil `planner` con un contrato de
propuestas; las tareas y dependencias se crean en una transacción tras validar el DAG.
`umbra task edit/accept/drop/deps` con control optimista. `umbra chat` lanza `claude`
interactivo con `--append-system-prompt-file` y `--settings` generados, más un hook
`PostToolUse` que registra cada comando con origen `chat`.

## Research (decisiones)

| Tema | Decisión |
| --- | --- |
| Contrato de propuestas | `PlanOutput {tasks: [{title, description, acceptance, scope, priority, depends_on: [índice]}], questions}`. Los adaptadores reciben el modelo de salida en `AgentRun.output_model` |
| Dónde corre el planificador | En la raíz del repo, con el perfil `planner` (sin Edit/Write; Codex en `read-only`) |
| Ciclos | `management/dag.py` (Kahn, O(V+E)) sobre las tareas existentes más las propuestas antes de insertar |
| Permisos del chat | `allow`: consultas y `exec` de comandos `safe`; `ask`: comandos que cambian estado y `exec` del resto; `deny`: approve, reject, `git push`, `gh pr merge`, Edit/Write en `.umbra/` y CI. En Claude Code, `deny` > `ask` > `allow` |
| Invocación de umbra desde el chat | `umbra` si está en el PATH; si no, `"<python>" -m umbra.cli.main` (las reglas usan el mismo prefijo) |
| Registro del chat | Hook `PostToolUse` (matcher `Bash`) → `umbra _hook chat-event` lee el JSON por stdin |

## Constitution Check

| Principio | Cumplimiento |
| --- | --- |
| II | El chat solo ejecuta comandos de umbra; no hay acción exclusiva del chat |
| III | Las propuestas se validan y quedan en borrador; un humano las acepta |
| VII | `approve` denegado en el chat y además exige TTY |
| IX | umbra no toca credenciales: usa el `claude` del usuario |

Sin violaciones.
