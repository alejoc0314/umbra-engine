# CLI contract: E0

## `umbra doctor [--json]`

Exit 0 si git, gh y al menos un agente están presentes; 1 en otro caso.

```json
{"ok": true, "tools": [
  {"name": "git", "kind": "required", "found": true, "version": "2.49.0", "session": null},
  {"name": "gh", "kind": "required", "found": true, "version": "2.101.0", "session": true},
  {"name": "claude", "kind": "agent", "found": true, "version": "2.1.312", "session": true},
  {"name": "codex", "kind": "agent", "found": true, "version": "0.163.0", "session": true}
]}
```

`session`: `true`/`false`, o `null` si no aplica o no se pudo determinar.

## `umbra init [--json]`

Exit 0 al crear o si ya existía; 2 si no es un repo git.

```json
{"root": "C:/apps/demo", "created": true, "stack": "python",
 "commands": {"test": "pytest -q", "lint": "ruff check ."}}
```

`.umbra/project.toml` generado:

```toml
[project]
stack = "python"
base_branch = "main"

[commands]
test = { run = "pytest -q", safe = true }
lint = { run = "ruff check .", safe = true }

[policy]
protected_paths = [".umbra/", ".github/workflows/"]
```

## `umbra status [--json]`

Exit 0; 2 si el proyecto no está inicializado.

```json
{"tasks": {"draft": 0, "accepted": 0, "done": 0, "dropped": 0},
 "active_runs": [], "spend": {"total": "0", "estimated": "0"}}
```
