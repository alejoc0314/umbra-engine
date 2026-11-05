# umbra-engine — Documento de diseño

Oct 29, 2026 · @Alejandro

## 1. Visión y alcance

umbra-engine es un orquestador de agentes de IA 100% de terminal. Convierte una especificación en trabajo planificado y lo lleva por etapas con evidencias y aprobación humana. Sirve tanto para arrancar proyectos nuevos como para añadir funcionalidades a repositorios existentes, sin importar el stack. umbra-engine es una herramienta local, propia y extensible.

**Qué es**

- Un orquestador que decide qué agente trabaja, cuándo, con qué límites y qué evidencia debe devolver.
- Un registro abierto de agentes: se integra uno nuevo con un manifiesto, sin tocar el núcleo.
- Dos formas de uso equivalentes: comandos directos o conversación con Claude.

**Qué no es**

- No es un agente de código. Claude Code y Codex hacen el trabajo; umbra los coordina.
- No es una aplicación web ni requiere servidor.
- No es un gestor de trabajo personal (objetivos, hábitos, agenda).
- No despliega a producción: entrega ramas, commits y PRs.

**Usuario objetivo:** en la fase 1, un único desarrollador (Alejandro) en su máquina. En la fase 2, un equipo, con configuración compartida y versionada (sección 11).

## 2. El acrónimo UMBRA como arquitectura

Cada letra nombra un componente real del motor, no solo una idea. El código se organiza con estos mismos nombres, así el acrónimo sirve también de mapa del repositorio.

| Letra | Concepto | En umbra-engine | Módulo |
| --- | --- | --- | --- |
| U | Unified | Un solo espacio: registro de agentes y perfiles, estado de tareas, eventos y evidencias. Global en `~/.umbra/` y por proyecto en `.umbra/` | `umbra.unified` |
| M | Management | De un objetivo o spec a tareas con prioridad, criterios de aceptación y dependencias (grafo acíclico). Define la cola de trabajo | `umbra.management` |
| B | Blocks | Cada agente trabaja en una sesión acotada: tiempo máximo, costo máximo, workspace aislado y acciones permitidas. Al agotarse, el bloque se cierra con lo que haya | `umbra.blocks` |
| R | Routines | Pipelines reutilizables con preparación, etapas y cierre. PLAN → BUILD → REVIEW → VERIFY → SHIP es la rutina `feature`; puede haber otras | `umbra.routines` |
| A | Actions | Pasos atómicos y tipados: leer, parchear, ejecutar tests, hacer commit, abrir PR. Cada acción queda registrada como evidencia | `umbra.actions` |

Relación entre ellas: **Management** decide *qué* se hace, **Routines** *en qué orden*, **Blocks** *con qué límites*, **Actions** *cómo* se toca el mundo y **Unified** *dónde queda todo registrado*.

## 3. Principios no negociables

Estos diez principios son el borrador directo de la constitution. Cualquier decisión técnica posterior debe poder justificarse contra ellos.

1. **Terminal primero.** Todo se puede hacer desde la CLI. No hay funcionalidad que exija un navegador o un servidor.
2. **Comandos antes que conversación.** La conversación con Claude es una capa opcional sobre los mismos comandos. Nada se puede hacer *solo* conversando.
3. **El agente propone, el motor decide.** Ninguna salida de un modelo equivale a una autorización. Transiciones, permisos y aprobaciones los decide código determinista.
4. **Agentes intercambiables.** Un agente se integra con un manifiesto y un adaptador. El núcleo no conoce a Claude Code ni a Codex por su nombre.
5. **Toda sesión está acotada.** Ningún agente corre sin límite de tiempo, costo y acciones permitidas.
6. **Evidencia o no pasó.** Una etapa avanza por resultados verificables (exit code, tests, diff ligado a un SHA), no por el texto del agente que diga que terminó.
7. **Humano antes de integrar.** Ningún cambio llega a la rama principal sin aprobación explícita. Un commit nuevo invalida la aprobación anterior.
8. **Reanudable e idempotente.** Si el proceso muere, se retoma desde el último punto seguro. Repetir un comando no duplica ramas, commits, PRs ni costos.
9. **Aislamiento del trabajo.** Cada tarea trabaja en su propio workspace. Los agentes no pueden borrar tests, rebajar umbrales ni editar la política para pasar los controles.
10. **Simple hasta que duela.** Sin servidor, sin colas externas, sin framework multiagente. Se añade complejidad solo cuando una métrica o un caso real la justifica.

## 4. Dos modos de uso: comandos y conversación

umbra se usa entero con comandos. La conversación es una capa encima que traduce lo que pides a esos mismos comandos. Así ambos modos hacen exactamente lo mismo y la conversación nunca tiene más poder que la CLI.

**Modo comandos.** `umbra plan`, `umbra run`, `umbra approve`, etc. No necesita ningún modelo para operar el motor: solo los agentes que ejecutan tareas consumen IA.

**Modo conversación (`umbra chat`).** Abre una conversación con Claude en la terminal, con el contexto del proyecto cargado. Puedes pedir "planifica esta spec", "corre los tests" o "¿por qué se bloqueó la tarea 4?". Claude responde y ejecuta tanto comandos de umbra como comandos del propio proyecto, siempre dentro de las reglas de esta sección.

### Qué puede ejecutar la conversación

| Nivel | Ejemplos | Confirmación |
| --- | --- | --- |
| Consultas de umbra | `umbra status`, `umbra log`, `umbra evidence`, `umbra task list` | Ninguna |
| Comandos de umbra que cambian estado | `umbra plan`, `umbra run`, `umbra pause`, `umbra cancel`, `umbra retry` | Claude Code la pide |
| Comandos registrados del proyecto | `umbra exec test`, `umbra exec lint`, `umbra exec dev`, `umbra exec migrate` | Ninguna si están marcados `safe`; si no, la pide |
| Cualquier otro comando de shell | `npm install`, `composer require`, scripts sueltos | En cada ejecución |
| Prohibido | `umbra approve`, `git push`, merge a la rama principal, editar la política | Bloqueado por regla `deny` |

Los comandos del proyecto se declaran en `.umbra/project.toml` y se ejecutan con `umbra exec <nombre>`. Así quedan en el registro de eventos con su exit code, igual que si los lanzaras tú. El principio 2 se mantiene: todo lo que hace el chat también existe como comando.

```toml
# .umbra/project.toml
[commands]
test    = { run = "pytest -q", safe = true }
lint    = { run = "ruff check .", safe = true }
dev     = { run = "npm run dev", background = true }
migrate = { run = "php artisan migrate" }   # pide confirmación
```

### Cómo funciona con la suscripción Team

- `umbra chat` abre el `claude` interactivo instalado en tu máquina, con tu sesión de la cuenta Team. umbra nunca guarda ni maneja credenciales de claude.ai.
- Se usa el modo interactivo y no `claude -p`. Así las confirmaciones las pide Claude Code en tu terminal con su sistema de permisos nativo. En `-p`, una acción que requiere aprobación se deniega si nada la aprueba ([fuente](https://code.claude.com/docs/en/headless)).
- umbra le pasa un prompt de sistema propio con `--append-system-prompt-file` y las reglas de permisos con `--settings`. Esas reglas dejan pasar las consultas y los comandos `safe`, piden confirmación para el resto y deniegan lo prohibido.
- Un hook de Claude Code registra cada comando ejecutado en el log de eventos de umbra, con origen `chat`.
- No se usa `--bare`: ese modo no lee el login de la suscripción y exige API key.
- En la fase 2, un servidor MCP de umbra sustituye a Bash para las acciones de umbra, con herramientas tipadas.

### Reglas de la conversación

- La conversación **no puede aprobar**. `umbra approve` está en `deny` y, además, exige su propia terminal interactiva.
- Ni push ni merge desde el chat: integrar cambios solo ocurre en SHIP, después de tu aprobación.
- El chat no edita archivos de política: `.umbra/project.toml`, `.umbra/routines/` y los workflows de CI.
- Los comandos de larga duración (servidores de desarrollo, watchers) se declaran con `background = true` y se detienen al cerrar el chat.
- Si `claude` no está instalado o no hay sesión, `umbra chat` falla con un mensaje claro y el resto de umbra sigue funcionando.

### Límite de política a vigilar

Anthropic no permite que *terceros* ofrezcan el login de claude.ai en sus productos sin aprobación previa, incluidos los agentes hechos con el Agent SDK ([fuente](https://code.claude.com/docs/en/agent-sdk/overview)). umbra cumple porque no ofrece ningún login: cada persona usa su propio Claude Code con su asiento Team. Si umbra llegara a distribuirse como producto a usuarios externos, la conversación tendría que pasar a API key o pedir aprobación.

## 5. Agentes, adaptadores y perfiles

umbra separa tres conceptos. Un **adaptador** sabe lanzar un binario concreto. Un **agente** es un adaptador instalado y verificado. Un **perfil** es una forma de trabajar sobre un agente. De un mismo agente pueden salir varios perfiles con comportamientos muy distintos.

| Concepto | Qué define | Ejemplo |
| --- | --- | --- |
| Adaptador | Cómo invocar el binario, leer su salida y mapear límites a sus flags | `claude-code`, `codex`, `script` |
| Agente | Un adaptador más su binario, versión y autenticación comprobados | `claude` 2.1.x con sesión Team |
| Perfil | Rol, instrucciones de trabajo, modelo, acciones permitidas, límites y contrato de salida | `builder-tdd`, `reviewer-strict` |

### Primeros dos adaptadores

| Aspecto | Claude Code | Codex |
| --- | --- | --- |
| Invocación | `claude -p` | `codex exec` |
| Salida en streaming | `--output-format stream-json` | `--json` (JSON Lines) |
| Salida estructurada | `--json-schema` | `--output-schema` |
| Instrucciones del perfil | `--append-system-prompt-file` | Se inyectan en el sobre de entrada |
| Permisos | `--allowedTools`, `--permission-mode` | `--sandbox read-only` o `workspace-write` |
| Límite de costo | `--max-budget-usd` | Lo aplica umbra por tiempo y tokens del evento `turn.completed` |
| Reanudar | `--resume <session_id>` | `codex exec resume <SESSION_ID>` |
| Autenticación | Login de Claude Code (Team) | Login guardado de la CLI o `CODEX_API_KEY` |

Fuentes: [Claude Code headless](https://code.claude.com/docs/en/headless) y [Codex non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode).

### Perfiles: cada agente con su forma de trabajar

Un perfil es un archivo TOML más un archivo de instrucciones en Markdown. Las instrucciones describen el estilo: "escribe primero el test que falla", "commits pequeños", "nunca toques archivos fuera del alcance", "responde solo con hallazgos y severidad".

```toml
# ~/.umbra/profiles/builder-tdd.toml
name         = "builder-tdd"
agent        = "claude-code"
roles        = ["build"]
model        = "opus"
instructions = "builder-tdd.md"      # forma de trabajar
actions      = ["read", "edit", "run_tests"]
output       = "build-result/v1"     # contrato que debe devolver

[limits]
max_minutes  = 20
max_cost_usd = 2.00
```

```toml
# ~/.umbra/profiles/reviewer-strict.toml
name         = "reviewer-strict"
agent        = "codex"
roles        = ["review"]
instructions = "reviewer-strict.md"
actions      = ["read"]              # se traduce a --sandbox read-only
output       = "findings/v1"

[limits]
max_minutes  = 10
```

- Los perfiles globales viven en `~/.umbra/profiles/`; un proyecto puede tener los suyos en `.umbra/profiles/` y estos tienen prioridad.
- Un perfil nunca puede ampliar lo que permite la política del proyecto: el motor intersecta ambos.
- Revisar con un agente distinto del que construyó (por ejemplo, construye Claude y revisa Codex) es la configuración recomendada por defecto.

### Integrar un agente nuevo

1. Si su CLI ya encaja en un adaptador existente, basta con un perfil nuevo.
2. Si no, se usa el adaptador `script`: cualquier ejecutable que lea el sobre JSON por stdin y escriba el resultado JSON por stdout.
3. Si se usa a menudo, se escribe un adaptador propio en Python. Es una clase con tres métodos: `check()`, `run(envelope)` y `resume(session_id)`.
4. `umbra agent test <nombre>` lo ejecuta contra una tarea de prueba y valida su salida contra el contrato. Sin pasar este test, el agente no se puede usar en una rutina.

El sobre de entrada y salida conserva los campos del handoff original: `schema_version`, `run_id`, `stage`, `attempt_id`, `input_sha`, `output_sha`, `status`, `findings` y `artifact_ids`.

## 6. Rutinas, bloques y acciones

Una rutina es un pipeline declarado en YAML. Cada etapa se ejecuta dentro de un bloque acotado y solo puede tocar el mundo mediante acciones tipadas. La rutina por defecto es `feature`, y el núcleo no depende de ella: un proyecto puede definir otras.

```text
PLAN → BUILD → REVIEW → VERIFY → SHIP ──(umbra approve)──▶ SUCCEEDED
         ▲         │         │
         └─────────┴─────────┘  corregible · máx. 2 ciclos
                   └───────────▶ BLOCKED (ciclos agotados)
```

REVIEW y VERIFY devuelven el trabajo a BUILD hasta dos veces; después la tarea queda bloqueada con su evidencia.

### Rutina `feature`

```yaml
# .umbra/routines/feature.yaml
name: feature
on_start:  [create_worktree, check_budget]
stages:
  - plan:   { profile: planner }
  - build:  { profile: builder-tdd, max_fix_cycles: 2 }
  - review: { profile: reviewer-strict, block_on: high }
  - verify: { profile: verifier, skip_if: no_acceptance_tests }
  - ship:   { builtin: commit_and_pr, human_approval: true }
on_finish: [cleanup, summary]
```

- Si REVIEW o VERIFY fallan con algo corregible, la tarea vuelve a BUILD, con un máximo de dos ciclos. Después queda en BLOCKED con la evidencia.
- SHIP no es un agente: es código determinista. Hace el commit, abre el PR con `gh` y espera tu `umbra approve`.
- Otras rutinas previstas: `bootstrap` para proyectos nuevos (scaffold, CI y primer test), `refactor` sin VERIFY de comportamiento nuevo y `spike` sin SHIP.

### Bloques

Un bloque es la unidad de ejecución de un agente. Fija:

- **Tiempo máximo**: al cumplirse, umbra detiene el proceso del agente.
- **Costo máximo**: se reserva antes de empezar y se concilia al terminar.
- **Workspace**: el worktree de la tarea y nada más.
- **Acciones permitidas**: la intersección entre el perfil y la política del proyecto.

Cada bloque genera un `attempt_id`. Un reintento es un bloque nuevo, nunca la sobrescritura del anterior.

### Acciones

Las acciones son el vocabulario cerrado con el que un agente o el motor actúan:

| Acción | Quién la usa | Evidencia que deja |
| --- | --- | --- |
| `read`, `search` | Agentes | Archivos leídos |
| `edit` | Agentes de BUILD | Diff contra el SHA base |
| `run_tests`, `run_lint` | Agentes y motor | Comando, exit code, salida |
| `git_commit`, `git_branch` | Motor | SHA resultante |
| `open_pr`, `merge_pr` | Motor tras aprobación | Número de PR, merge SHA |

Los comandos de `run_tests` y `run_lint` vienen del perfil de stack del proyecto (`.umbra/project.toml`), nunca del texto del agente.

### Estados de una ejecución

`QUEUED`, `RUNNING`, `PAUSED`, `WAITING_APPROVAL`, `BLOCKED`, `FAILED`, `CANCELLED` y `SUCCEEDED`. Una ejecución solo llega a `SUCCEEDED` cuando el merge del SHA aprobado está confirmado.

## 7. Arquitectura técnica en Python

umbra es un único paquete de Python sin servidor. La CLI escribe intenciones en SQLite, y un proceso worker desacoplado las ejecuta. Cerrar la terminal no detiene el trabajo, y reiniciar el worker lo retoma desde el último punto seguro.

### Stack

| Necesidad | Elección | Motivo |
| --- | --- | --- |
| Lenguaje | Python 3.12+ | Preferencia del proyecto; `tomllib` y `sqlite3` en la librería estándar |
| CLI | Typer | Comandos tipados con ayuda automática |
| Salida y tablas | Rich | Progreso y tablas en terminal sin una TUI completa |
| Vista en vivo (fase 2) | Textual | Panel de terminal para `umbra watch` |
| Contratos | Pydantic v2 | Validar sobres, perfiles y rutinas |
| Estado | SQLite (modo WAL) | Un archivo, transaccional, sin servicio |
| Rutinas | YAML (PyYAML) | Legible para humanos |
| Git y PRs | `git` y `gh` por subprocess | Usa las credenciales que ya tienes |
| Distribución | `uv tool install umbra-engine` | Un comando, aislado del sistema |
| Tests | pytest | Estándar |

Sin Temporal, sin Redis, sin PostgreSQL y sin framework multiagente. El orquestador es una máquina de estados de unos cientos de líneas con checkpoints en SQLite.

### Estructura del repositorio

```text
umbra-engine/
├─ pyproject.toml
├─ src/umbra/
│  ├─ cli/          # comandos Typer (un archivo por grupo)
│  ├─ chat/         # umbra chat: envoltorio de claude -p
│  ├─ unified/      # store SQLite, eventos, artefactos, configuración
│  ├─ management/   # specs, tareas, dependencias (DAG)
│  ├─ routines/     # carga de YAML y máquina de estados
│  ├─ blocks/       # ejecución acotada, worktrees, límites
│  ├─ actions/      # acciones tipadas: git, gh, tests
│  ├─ adapters/     # base.py, claude_code.py, codex.py, script.py
│  └─ contracts/    # modelos Pydantic versionados
├─ defaults/        # perfiles y rutinas que se copian en umbra init
└─ tests/
```

### Cómo fluye una ejecución

1. `umbra run 4` valida la tarea, reserva presupuesto, escribe la ejecución en estado `QUEUED` y lanza el worker si no está vivo.
2. El worker toma el bloqueo del repositorio, crea el worktree y avanza la rutina etapa a etapa.
3. Cada etapa abre un bloque: el adaptador lanza el agente, transmite sus eventos al registro y valida su salida contra el contrato.
4. Tras cada etapa se guarda un checkpoint. Si el worker muere, al arrancar busca ejecuciones `RUNNING` y las retoma desde el último checkpoint.
5. En SHIP la ejecución queda en `WAITING_APPROVAL` hasta que corres `umbra approve 4` en una terminal interactiva.

## 8. Estado, datos y evidencias

Todo el estado de un proyecto vive en `.umbra/` dentro del repositorio, y la configuración personal en `~/.umbra/`. El modelo de datos del handoff se reduce a lo que necesita un solo usuario, conservando las reglas de integridad que evitan duplicados.

### Disposición en disco

```text
~/.umbra/                 # global (tuyo)
├─ config.toml            # preferencias y límites por defecto
├─ agents/                # agentes verificados
└─ profiles/              # perfiles globales

<repo>/.umbra/            # por proyecto
├─ project.toml           # stack, comandos de test/lint, rama base, política
├─ routines/              # rutinas del proyecto
├─ profiles/              # perfiles que sobrescriben los globales
├─ umbra.db               # SQLite (ignorado por git)
└─ artifacts/             # logs, diffs, reportes (ignorado por git)
```

`project.toml`, `routines/` y `profiles/` se versionan con el repo: son la base para compartir con un equipo. `umbra.db` y `artifacts/` no se versionan.

### Entidades

| Entidad | Campos clave | Regla |
| --- | --- | --- |
| Spec | id, versión, hash, texto | Inmutable; editar crea versión nueva |
| Task | número, título, criterios, alcance, prioridad, spec\_version | Número único por proyecto |
| Dependency | task, depende\_de | Sin ciclos; solo dentro del proyecto |
| Run | task, rutina, estado, base\_sha, head\_sha, idempotency\_key | Clave idempotente única |
| Attempt | run, etapa, número, perfil, inicio, fin, estado | Único por run, etapa y número |
| Artifact | attempt, tipo, ruta, checksum, tested\_sha | Ligado a un SHA |
| Finding | attempt, severidad, archivo, línea, estado | Abierto bloquea según política |
| Approval | run, head\_sha, decisión, fecha | Inválida si cambia el head\_sha |
| Usage | attempt, agente, modelo, tokens, costo, estimado o real | Costo en decimal, nunca float |
| Event | run, seq, tipo, origen (cli, chat, worker), payload | Solo se añade, nunca se edita |

### Evidencias

Cada evidencia responde cinco preguntas: qué SHA se probó, con qué comando, con qué perfil, cuál fue el exit code y dónde está la salida original. Un texto del agente que diga "tests pasan" no es evidencia.

### Reanudación e idempotencia

- Cada efecto externo (rama, commit, PR) tiene una `operation_key` estable. Antes de repetirlo, umbra consulta si ya existe.
- `umbra run` con la misma tarea y rutina mientras hay una ejecución activa devuelve la existente; no crea otra.
- Un solo worker por repositorio, protegido con un archivo de bloqueo con PID y fecha de renovación.

## 9. Seguridad y control humano

En la fase 1 el riesgo principal no es un atacante externo sino un agente que hace demasiado: tocar la rama principal, borrar tests o ejecutar comandos fuera de su alcance. Los controles se diseñan para eso y se endurecen cuando lleguen repos de terceros o un equipo.

| Superficie | Regla en fase 1 | Endurecimiento posterior |
| --- | --- | --- |
| Workspace | Un git worktree por tarea; el agente arranca con ese directorio como raíz | Contenedor Docker por bloque |
| Permisos del agente | Claude: `--allowedTools` y `--permission-mode` según perfil. Codex: `--sandbox read-only` o `workspace-write` | Red denegada por defecto |
| Rama principal | Ningún agente hace push ni merge; solo el motor en SHIP tras aprobación | Protección de rama obligatoria en GitHub |
| Controles de calidad | Un diff que borre tests, baje umbrales o toque `.umbra/` o los workflows de CI bloquea la etapa | Escaneo SAST y de secretos como etapa |
| Credenciales | umbra no guarda tokens; usa los logins de `claude`, `codex` y `gh` | Gestor de secretos para el equipo |
| Aprobación | Solo `umbra approve` en terminal interactiva; queda ligada al head\_sha | Revisores requeridos en GitHub |

### Riesgo conocido: Claude Code sin `--bare`

Para usar la suscripción, umbra lanza `claude -p` sin `--bare`. En ese modo Claude Code carga los hooks de `.claude/settings.json` y los servidores de `.mcp.json` del repositorio, sin pedir confirmación de confianza ([fuente](https://code.claude.com/docs/en/headless)). En repos propios es aceptable. Antes de trabajar sobre un repositorio ajeno, umbra debe avisar si encuentra esos archivos y pedir confirmación.

### Puntos de control humano

- **Obligatorio:** antes de integrar cualquier cambio (SHIP).
- **Configurable por rutina:** después de PLAN (revisar el plan antes de gastar en BUILD) y ante hallazgos de severidad media.
- **Siempre disponible:** `umbra pause` y `umbra cancel` en cualquier momento. Una cancelación después del merge no lo revierte; abre un PR de reversión.

## 10. Referencia de comandos

Los comandos se agrupan por las letras de UMBRA. Todos aceptan `--json` para que scripts y el propio chat lean su salida sin interpretar texto.

| Comando | Grupo | Qué hace |
| --- | --- | --- |
| `umbra init` | Unified | Crea `.umbra/` en el repo, detecta el stack y propone comandos de test y lint |
| `umbra doctor` | Unified | Comprueba `git`, `gh`, `claude`, `codex`, logins y versiones |
| `umbra status` | Unified | Tareas, ejecuciones activas y gasto del proyecto |
| `umbra plan <spec.md>` | Management | El perfil planificador propone tareas; quedan en borrador |
| `umbra task list` / `edit <n>` / `accept <n>` / `drop <n>` | Management | Revisar y ajustar las propuestas antes de ejecutar |
| `umbra task deps <n> --on <m>` | Management | Declarar dependencias; rechaza ciclos |
| `umbra run <n...> [--routine feature]` | Routines | Encola y ejecuta tareas (una activa por repo en el MVP) |
| `umbra pause` / `resume` / `cancel <n>` | Routines | Control de la ejecución en el siguiente punto seguro |
| `umbra retry <n> [--from build]` | Routines | Reintenta desde una etapa; crea intentos nuevos |
| `umbra approve <n>` / `reject <n>` | Routines | Muestra diff, tests, hallazgos y costo; pide confirmación |
| `umbra exec <nombre>` | Actions | Ejecuta un comando registrado en `project.toml` y guarda exit code y salida |
| `umbra log <n> [--stage build] [-f]` | Blocks | Eventos y salida de los bloques, en vivo con `-f` |
| `umbra evidence <n>` | Actions | Comandos ejecutados, exit codes, SHAs y artefactos |
| `umbra agent list` / `add` / `test <nombre>` | Agentes | Registrar y verificar agentes |
| `umbra profile list` / `new` / `show` / `test <nombre>` | Perfiles | Gestionar perfiles y probarlos contra una tarea de ejemplo |
| `umbra chat` | Conversación | Abre la conversación con Claude (sección 4) |
| `umbra watch` | Fase 2 | Panel de terminal en vivo con Textual |

## 11. De uso personal a equipo

La fase 1 no construye nada para equipos, pero tampoco cierra puertas. Tres decisiones tomadas desde el inicio hacen que el paso a equipo sea sobre todo configuración, no reescritura.

**Lo que se deja preparado desde el día uno**

- **Configuración versionada en el repo.** `project.toml`, rutinas y perfiles del proyecto viven en `.umbra/` y viajan con git. Un compañero que clona el repo hereda la forma de trabajar.
- **Origen en cada evento.** Cada evento y aprobación registra quién lo hizo (usuario git y origen `cli`, `chat` o `worker`). La auditoría ya existe aunque haya una sola persona.
- **Credenciales por persona.** Cada miembro usa su propio login de Claude Code (asiento Team), de Codex y de `gh`. umbra nunca centraliza credenciales.

**Lo que se añade cuando haya equipo**

| Capacidad | Cómo |
| --- | --- |
| Perfiles y rutinas compartidos entre repos | Un repo de "catálogo" que `umbra` sincroniza en `~/.umbra/` |
| Aprobación por otra persona | La revisión requerida de GitHub; umbra la lee y la exige antes del merge |
| Roles (operador y aprobador) | Mapeados a permisos del repositorio en GitHub, no a un sistema propio |
| Estándar de equipo | La constitution del proyecto se convierte en la política que umbra aplica |
| Ejecución compartida | Solo si hace falta: un runner en CI que ejecuta `umbra run` |

Lo que se evita a propósito: un servidor central, una base de datos compartida y un sistema de usuarios propio. GitHub ya resuelve identidad, permisos y revisión.

## 12. MVP y roadmap

Se construye por entregas verticales: cada una funciona de punta a punta antes de empezar la siguiente. No hay fechas comprometidas; cada entrega termina cuando cumple su criterio de salida.

**E0. Constitution y esqueleto.** Constitution escrita a partir de este documento. Paquete instalable con `uv`, `umbra init`, `umbra doctor` y el store SQLite. *Sale cuando:* `umbra doctor` detecta correctamente `git`, `gh`, `claude` y `codex` en tu máquina.

**E1. Primera tarea real.** Adaptador de Claude Code, perfil `builder` y una rutina mínima BUILD → SHIP sobre un repo de ensayo. Worktree, tests del proyecto como evidencia, commit, PR con `gh` y `umbra approve`. *Sale cuando:* una tarea pequeña produce un PR real, y matar el worker a mitad de BUILD no pierde estado ni duplica el PR.

**E2. Rutina completa y Codex.** PLAN, REVIEW y VERIFY. Adaptador de Codex. Perfiles distintos por etapa, con Claude construyendo y Codex revisando. Ciclos de corrección y límites de bloque. *Sale cuando:* un test que falla de verdad bloquea el avance y la tarea queda en BLOCKED con la evidencia.

**E3. Management y conversación.** `umbra plan` desde una spec, edición de tareas, dependencias y `umbra chat`. *Sale cuando:* desde el chat puedes planificar y lanzar una tarea, y el chat no puede aprobarla.

**E4. Integración abierta.** Adaptador `script`, `umbra agent test`, `umbra profile test` y documentación para escribir adaptadores. *Sale cuando:* integras un tercer agente sin modificar el núcleo.

**E5. Endurecimiento y vista en vivo.** `umbra watch` con Textual, Docker opcional por bloque y escaneo de secretos y SAST como etapa. *Sale cuando:* has usado umbra en 10 a 20 tareas reales y tienes métricas de costo, retrabajo y aceptación.

Solo después de E5 se evalúa la fase de equipo (sección 11).

## 13. Decisiones abiertas y riesgos

**Decisiones pendientes**

- [ ] Repositorio de ensayo para E1 y su comando real de tests.
- [ ] Proveedor Git: GitHub con `gh` es la suposición; confirmar si también habrá GitLab o Bitbucket.
- [ ] Modelo por defecto de cada perfil inicial (planificador, constructor, revisor).
- [ ] Presupuesto por defecto por bloque y por tarea.
- [ ] Si el chat debe poder lanzar `umbra run` sin pedir confirmación (hoy siempre la pide).
- [ ] Qué comandos del proyecto se marcan como `safe` por defecto en `umbra init`.
- [ ] Política de código enviado a modelos: qué repos o carpetas nunca deben salir de la máquina.

**Riesgos**

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| Cambios en los flags o la salida de `claude` y `codex` | Un adaptador deja de funcionar tras una actualización | `umbra doctor` fija versiones probadas; tests de contrato por adaptador |
| Uso de la suscripción en automatización intensiva | Límites de uso del plan Team alcanzados a mitad de una tarea | Bloques con pausa al detectar límite; perfil alternativo con API key |
| Política de login de claude.ai | No poder distribuir umbra con la conversación tal cual | Mantener el chat sobre el `claude` de cada usuario; API key si se vuelve producto |
| Agentes que "hacen trampa" para pasar tests | Entregas que parecen correctas y no lo son | Bloqueo de diffs sobre tests y política; revisión con otro agente |
| Costo real de Codex difícil de medir con login de ChatGPT | Ledger incompleto | Marcar el costo como estimado y medir por tiempo y tokens |
| Alcance creciente | No terminar nunca el MVP | Entregas verticales con criterio de salida; principio 10 |

## 14. Del documento a la constitution

La constitution debe recoger solo lo que no cambia de una funcionalidad a otra: principios, restricciones técnicas y reglas de gobierno. El resto de este documento alimenta las especificaciones y los planes de cada entrega.

| Va a la constitution | Fuente en este documento |
| --- | --- |
| Los diez principios no negociables | Sección 3 |
| Restricciones de stack: Python 3.12+, sin servidor, SQLite, sin framework multiagente | Sección 7 |
| Reglas de seguridad y aprobación humana | Sección 9 |
| Equivalencia entre comandos y conversación | Sección 4 |
| Contrato del sobre de agentes como interfaz estable | Sección 5 |
| Gobierno: cómo se enmienda la constitution y quién aprueba | Por definir |

| Va a specs y planes | Fuente |
| --- | --- |
| Comandos, flags y formatos concretos | Secciones 5, 6 y 10 |
| Modelo de datos y disposición en disco | Sección 8 |
| Entregas E0 a E5 con sus criterios de salida | Sección 12 |

Si la constitution se genera con [Spec Kit](https://github.com/github/spec-kit), la entrada de su comando de constitution es la sección 3 más las restricciones de la tabla anterior. Cada entrega de la sección 12 se convierte después en una spec propia.

## Referencias

- `handoff_motor_desarrollo_ia.docx`, versión 1.0 del 29/10/2026: especificación web original de la que deriva este diseño.
- [Vora Engine para tu equipo](https://vora.software/vora-engine/)
- [Vora, página principal](https://vora.software/)
- [Claude Code: ejecución programática (headless)](https://code.claude.com/docs/en/headless)
- [Claude Agent SDK: visión general y política de autenticación](https://code.claude.com/docs/en/agent-sdk/overview)
- [Codex: modo no interactivo](https://learn.chatgpt.com/docs/non-interactive-mode)
- [GitHub Spec Kit](https://github.com/github/spec-kit)

Páginas consultadas el 29 de octubre de 2026. Las versiones exactas de `claude`, `codex` y las librerías se fijarán en E0.

> Fuente viva: https://claude.ai/artifact/VzLosTTM6QNwVCja2ah2GR (exportado el 2026-10-29).
