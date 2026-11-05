# Tasks: E1 — Primera tarea real

- [ ] T001 Contratos: `contracts/envelope.py`, `contracts/profile.py`, `contracts/routine.py`
- [ ] T002 Defaults: perfil `builder` (toml + md), rutina `quick.yaml`; `unified/profiles.py` (proyecto > `~/.umbra` > defaults)
- [ ] T003 `unified/events.py`: `add_event` con `seq` por run en transacción
- [ ] T004 [P] `blocks/process.py`: ejecutar con timeout, stdin, log a archivo y kill de árbol
- [ ] T005 [P] `blocks/worktree.py` y `blocks/lease.py` (+ tests unitarios de lease)
- [ ] T006 [P] `actions/git.py`, `actions/gh.py`, `actions/commands.py`, `actions/policy.py` (+ tests de policy)
- [ ] T007 `adapters/base.py` + `adapters/claude_code.py` (+ test de construcción de comando y parseo)
- [ ] T008 `routines/engine.py`: pasos idempotentes, intentos, ciclos de corrección, estados
- [ ] T009 `routines/worker.py`: lease, heartbeat, retomar RUNNING, spawn desacoplado
- [ ] T010 CLI: `task add/list`, `run`, `log`, `evidence`, `approve`, `reject`, `exec`, `_worker`
- [ ] T011 Fakes `tests/fakes/claude.py` y `tests/fakes/gh.py` + fixture con remoto bare
- [ ] T012 Aceptación: feliz → WAITING_APPROVAL → approve → SUCCEEDED; T04 test fallido; T05 borra test; T06 reinicio; T07 PR existente; T03 idempotencia; T08 commit tras evaluación; approve sin TTY; timeout
- [ ] T013 `sandbox/` con módulo y test; smoke test real con Claude Code sobre el repo de umbra-engine
- [ ] T014 pytest y ruff en verde
