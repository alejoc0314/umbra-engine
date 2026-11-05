# Research: E0

## Sondas de herramientas (verificado el 2026-10-29 en la máquina de desarrollo)

| Herramienta | Versión | Sesión | Obligatoria |
| --- | --- | --- | --- |
| git | `git --version` | no aplica | sí |
| gh | `gh --version` (1.ª línea) | `gh auth status` → exit 0 | sí |
| claude | `claude --version` | `claude auth status --json` → `loggedIn` | agente (≥1 de 2) |
| codex | `codex --version` | `codex login status` → exit 0 | agente (≥1 de 2) |

- **Decisión**: tabla de sondas como datos (`Probe(name, version_cmd, session_cmd, kind)`), un
  único ejecutor. **Motivo**: añadir herramientas sin lógica nueva (principio IV).
- Timeout por comando: 8 s. En Windows, `claude`/`codex`/`gh` pueden ser `.cmd`; se resuelven con
  `shutil.which` y se ejecutan con la ruta resuelta.

## Almacén

- **Decisión**: `sqlite3` de la stdlib, `journal_mode=WAL`, `foreign_keys=ON`, migraciones como
  lista de scripts SQL indexada por `PRAGMA user_version`. **Alternativas**: SQLAlchemy/alembic,
  descartado por principio X.
- Costos como `TEXT` con `decimal.Decimal` en Python. IDs internos `TEXT` (uuid4 hex); números
  visibles de tarea como `INTEGER` secuencial por proyecto.
- Tiempos en ISO-8601 UTC (`TEXT`).

## Detección de stack

| Archivo | Stack | test | lint |
| --- | --- | --- | --- |
| `pyproject.toml` / `setup.py` | python | `pytest -q` | `ruff check .` |
| `package.json` | node | `npm test` | `npm run lint` |
| `composer.json` | php | `php artisan test` si existe `artisan`, si no `vendor/bin/phpunit` | `vendor/bin/pint --test` |
| ninguno | generic | — | — |

## Empaquetado

- **Decisión**: hatchling, layout `src/`, script `umbra = "umbra.cli.main:app"`. Instalación de
  desarrollo `uv sync` + `uv run umbra`; instalación como herramienta `uv tool install -e .`.
- `.gitattributes` con `* text=auto eol=lf` para evitar CRLF en Windows.
