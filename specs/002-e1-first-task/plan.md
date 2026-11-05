# Implementation Plan: E1 — Primera tarea real (BUILD → SHIP)

**Branch**: `002-e1-first-task` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

## Summary

Se añaden contratos (sobre y perfil), el adaptador de Claude Code, bloques acotados (proceso con
timeout y kill del árbol, worktree, lease), acciones (git, gh, comandos registrados, política de
diff), el motor de rutinas con checkpoints y un worker desacoplado. CLI: `task add/list`, `run`,
`log`, `evidence`, `approve`, `reject`, `exec`.

## Technical Context

**Language/Version**: Python >= 3.12 · **Dependencies**: las de E0 · **Storage**: esquema v1
**Testing**: pytest con `claude` y `gh` falsos (scripts Python en `tests/fakes/` puestos en PATH)
y un remoto git bare local · **Platform**: Windows y POSIX

## Research (decisiones)

| Tema | Decisión | Motivo |
| --- | --- | --- |
| Invocación de Claude | `claude -p --output-format stream-json --verbose --append-system-prompt-file F --model M --permission-mode acceptEdits --allowedTools ... --max-budget-usd X --json-schema S`; prompt por stdin | Verificado en `claude --help` 2.1.312; stdin evita límites de línea de comandos en Windows |
| Resultado de Claude | Última línea `{"type":"result"}`: `is_error`, `session_id`, `total_cost_usd`, `structured_output`, `usage` | docs headless |
| Permisos del builder | `read`→Read,Glob,Grep · `edit`→Edit,Write,MultiEdit · `run_tests`→`Bash(<cmd>)` y `Bash(<cmd> *)` de los comandos registrados. Lo demás queda denegado (modo manual de `-p`) | Principio V; el agente no puede hacer git push |
| Timeout | `subprocess.Popen` en nuevo grupo de procesos; al vencer: `taskkill /T /F` (Windows) o `os.killpg` (POSIX) | El agente lanza hijos |
| Worker | `python -m umbra.cli.main _worker --root R`, `DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP` en Windows, `start_new_session` en POSIX; log en `.umbra/artifacts/worker.log` | Sobrevive al cierre de la terminal |
| Lease | Fila `lease('worker')` con owner, token creciente y expiración (TTL 60 s, renovación cada 20 s en hilo). Antes de cada efecto externo se verifica el token (fencing) | Principio VIII, portable |
| Checkpoint | `run.stage` ∈ setup, build, verify_tests, policy, commit, push, pr, waiting; cada paso es idempotente y se re-ejecuta al retomar | Simplicidad: re-ejecutar un paso idempotente = reanudar |
| Merge | `gh pr merge N --squash --match-head-commit SHA`, luego `gh pr view N --json state,mergeCommit` | El proveedor rechaza si la cabeza cambió |
| Tests de política | Un archivo es test si su ruta contiene `tests/` o `test/`, o su nombre coincide con `test_*`, `*_test.*`, `*.test.*`, `*.spec.*` | Cubre Python, JS y PHP |

## Constitution Check

| Principio | Cumplimiento |
| --- | --- |
| III | Transiciones solo en `engine.py`; la salida del agente se valida pero no decide |
| IV | El motor usa `get_adapter(profile.agent)`; nada fuera de `adapters/` nombra a Claude |
| V | Cada intento tiene timeout, `--max-budget-usd` y herramientas del perfil |
| VI | Tests ejecutados por el motor, no por el texto del agente |
| VII | `approve` exige TTY, SHA vigente y confirma merge antes de `SUCCEEDED` |
| VIII | `operation` para push/PR/merge; búsqueda de PR existente; lease con fencing |
| IX | Worktree por tarea; `policy.check_diff` |

Sin violaciones.

## Project Structure

```text
src/umbra/
├── contracts/   envelope.py, profile.py, routine.py
├── adapters/    base.py, claude_code.py, __init__.py (registro)
├── blocks/      process.py, worktree.py, lease.py
├── actions/     git.py, gh.py, commands.py, policy.py
├── routines/    engine.py, worker.py, loader.py
├── unified/     events.py, profiles.py (resolución de perfiles)
└── cli/         routines.py, management.py (task add/list)
defaults/        profiles/builder.toml, builder.md · routines/quick.yaml
sandbox/         calc.py + tests/test_calc.py (objetivo del dogfooding)
tests/fakes/     claude.py, gh.py
tests/acceptance/test_e1.py
```

## Complexity Tracking

Sin desviaciones.
