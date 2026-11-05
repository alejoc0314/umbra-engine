# Integrar agentes en umbra-engine

umbra no conoce agentes concretos: los resuelve por nombre. Hay tres formas de sumar uno, de
menor a mayor esfuerzo.

| Situación | Qué hacer |
| --- | --- |
| La CLI ya encaja en un adaptador (Claude Code, Codex) | Crear un **perfil** nuevo |
| Cualquier otro ejecutable | Registrar un agente **script** con un manifiesto |
| Un agente que usas mucho y necesita algo especial | Escribir un adaptador en Python |

## 1. Un perfil nuevo

```bash
umbra profile new revisor-seguridad --from reviewer-strict
# edita .umbra/profiles/revisor-seguridad.md con su forma de trabajar
umbra profile test revisor-seguridad
```

El perfil define agente, roles, modelo (y `fallback_model`, el que Claude Code usa si el
principal no está disponible), acciones (`read`, `search`, `edit`, `run_tests`,
`run_lint`), contrato de salida y límites. Las acciones efectivas son la intersección con
`[policy] actions` del proyecto.

## 2. Un agente `script`

Un directorio con `agent.toml` y lo que necesite tu ejecutable:

```toml
name        = "todo-reviewer"          # minúsculas, números y guiones
adapter     = "script"
command     = ["python", "{agent_dir}/reviewer.py"]
description = "Marca los TODO añadidos"
```

`{agent_dir}` se reemplaza por la ruta del directorio registrado. El proceso corre con el
workspace de la tarea como directorio actual y con los límites de tiempo del perfil.

**Entrada (stdin)**, un objeto JSON:

| Campo | Contenido |
| --- | --- |
| `envelope` | Sobre de la etapa: `run_id`, `stage`, `attempt_id`, `input_sha`, `task`, `plan`, `diff`, `feedback`, `findings` |
| `profile` | El perfil que lo invoca |
| `instructions` | Texto del `.md` del perfil |
| `output_schema` | JSON Schema que debe cumplir `output` |
| `allowed_commands` | Comandos registrados del proyecto que puede ejecutar |

**Salida (stdout)**: la última línea que empiece por `{` debe ser
`{"output": {...}, "cost": 0.0, "session_id": "...", "input_tokens": 0, "output_tokens": 0}`.
Solo `output` es obligatorio. Para etapas, `output` sigue el contrato de etapa:
`{"status": "done"|"blocked", "summary": "...", "findings": [...], "questions": [...]}`.

Un exit code distinto de 0, una salida sin JSON o un `output` que no valida hacen fallar el
intento.

```bash
umbra agent add examples/agents/todo-reviewer          # global (~/.umbra/agents)
umbra agent add ./mi-agente --project                  # solo este repo (.umbra/agents)
umbra agent test todo-reviewer                         # tarea de ejemplo → verificado
umbra agent list
```

Un agente registrado **no entra en ninguna rutina hasta pasar `umbra agent test`**. Si cambias
su `agent.toml`, la verificación se invalida y debes volver a probarlo.

Después, úsalo desde un perfil (`agent = "todo-reviewer"`) y ese perfil desde una etapa de una
rutina en `.umbra/routines/*.yaml`.

## 3. Un adaptador en Python

Implementa el protocolo de `src/umbra/adapters/base.py`:

```python
class MiAdaptador:
    name = "mi-agente"

    def check(self) -> bool: ...                       # el binario existe
    def run(self, req: AgentRun) -> AgentResult: ...   # lanza, espera, valida
```

`run` debe respetar `req.profile.limits` (usa `blocks.process.run_bounded`), validar la salida
contra `req.output_model` y devolver `AgentResult` con costo y tokens. Regístralo en
`ADAPTERS` (`src/umbra/adapters/__init__.py`) y añade pruebas con un ejecutable falso, como las
de `tests/fakes/`.
