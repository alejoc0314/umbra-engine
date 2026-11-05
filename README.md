# umbra-engine

Orquestador de agentes de IA 100% de terminal. Convierte una especificación en tareas y las
lleva por PLAN → BUILD → REVIEW → VERIFY → SCAN → SHIP con evidencias y aprobación humana. Usa
agentes intercambiables: Claude Code y Codex vienen integrados, y cualquier ejecutable se puede
sumar con un manifiesto.

**U**nified · **M**anagement · **B**locks · **R**outines · **A**ctions

```bash
uv tool install git+https://github.com/alejoc0314/umbra-engine
umbra doctor && umbra init
umbra plan spec.md && umbra task accept 1 2
umbra run 1 && umbra watch
umbra approve 1
```

- Guía de uso: [`docs/usage.md`](docs/usage.md)
- Integrar agentes: [`docs/adapters.md`](docs/adapters.md)
- Diseño: [`docs/design.md`](docs/design.md)
- Constitution: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
- Specs por entrega: [`specs/`](specs/)

## De la idea a las tareas

```bash
umbra spec new "mi idea"         # conversación con puntos de control: spec, plan, tareas
umbra spec tasks specs/001-mi-idea   # tareas en borrador sin conversación
umbra spec resume 001            # retoma la conversación
umbra spec list                  # avance por spec
```

Detalles en [`docs/usage.md`](docs/usage.md).

## Desarrollo

```bash
uv sync
uv run pytest        # sin red ni costo: agentes y gh falsos, remoto git local
uv run ruff check .
```

## Contribuir y licencia

Lee [`CONTRIBUTING.md`](CONTRIBUTING.md) antes de abrir un PR y [`SECURITY.md`](SECURITY.md) para
reportar vulnerabilidades. umbra se publica bajo la [licencia Apache 2.0](LICENSE).
