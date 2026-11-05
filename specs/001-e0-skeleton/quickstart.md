# Quickstart: validar E0

```bash
cd C:/apps/umbra-engine
uv sync
uv run pytest
uv run ruff check .
uv run umbra doctor            # 4 herramientas OK, exit 0
uv run umbra doctor --json

# en un repo de prueba
mkdir /tmp/demo && cd /tmp/demo && git init && touch pyproject.toml
uv run --project C:/apps/umbra-engine umbra init     # stack python
uv run --project C:/apps/umbra-engine umbra init     # "ya inicializado", sin cambios
uv run --project C:/apps/umbra-engine umbra status --json
```
