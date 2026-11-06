# Guía de uso de umbra-engine

umbra orquesta agentes de IA desde la terminal: tú defines tareas, los agentes las ejecutan en
workspaces aislados y nada se integra sin tu aprobación. Todo se hace con comandos; la
conversación (`umbra chat`) es opcional.

## 1. Instalar y diagnosticar

```bash
uv tool install git+https://github.com/alejoc0314/umbra-engine   # la última versión publicada
umbra doctor
```

### Versiones y actualizar

umbra usa versiones `vMAYOR.MENOR.PARCHE` (ver `CHANGELOG.md`). `umbra --version` y la cabecera
de `watch` dicen cuál corre.

```bash
umbra self-update --check   # ¿hay una versión nueva? y qué trae
umbra self-update           # instalarla
```

Se instala la **última versión publicada**, no lo último de `main`: lo que umbra integra en
`main` no cambia tu instalación hasta que se publica una versión. En Windows la actualización
termina en segundo plano (un programa en uso no se puede reemplazar): detiene el puente de
Telegram y espera a que salga, espera hasta 10 minutos a que nada use umbra (`watch` abierto,
tareas en marcha), instala y comprueba que la versión nueva arranca; si no arranca, vuelve a la
anterior. Al terminar relanza el puente y avisa por Windows y por Telegram. Desde el teléfono,
`/actualizar` hace lo mismo y te dice qué trae la versión.

**Si desarrollas umbra**: trabaja en tu copia con `uv run umbra …` (no toca la instalación de
diario). Para publicar: cada PR describe su cambio en «Sin publicar» del CHANGELOG; luego
`uv run python scripts/release.py prepare minor` (abre el PR de la versión) y, al mezclarlo,
`uv run python scripts/release.py publish` (etiqueta y release de GitHub).

`doctor` comprueba git, gh, claude y codex (versión y sesión). Se necesitan git, gh y al menos
un agente. umbra no guarda credenciales: usa tus logins de `gh`, `claude` y `codex`.

## 2. Inicializar un repositorio

```bash
cd mi-repo
umbra init
```

Crea `.umbra/project.toml` con el stack detectado y los comandos de test y lint. Revísalo:

```toml
[project]
stack = "python"
base_branch = "main"
default_routine = "feature"        # o "quick" (BUILD → SHIP)

[commands]                          # lo único que agentes y chat pueden ejecutar
test = { run = "pytest -q", safe = true }
lint = { run = "ruff check .", safe = true }
sast = { run = "semgrep --error --config auto ." }

[scan]
commands = ["sast"]                 # se ejecutan en la etapa SCAN

[blocks]
isolation = "none"                  # "docker" para correr los comandos en un contenedor
# image = "python:3.12-slim"; network = "none"; cpus = 2; memory = "2g"

[policy]
protected_paths = [".umbra/", ".github/workflows/"]
# actions = ["read", "search", "edit", "run_tests"]   # tope para todos los perfiles
# trust_repo_agent_config = false
```

Versiona `.umbra/project.toml`, `.umbra/routines/` y `.umbra/profiles/`. La base de datos, los
artefactos y los worktrees quedan fuera de git.

### Un proyecto nuevo en un comando

```bash
umbra new cliente-x --stack laravel --idea "portal de pedidos"
```

Crea la carpeta con git, ejecuta el andamiaje del playbook (`composer create-project`, `uv
init`, `npm init`…), copia el CI y el `AGENTS.md` del playbook, escribe `.umbra/project.toml`
con sus comandos y rutina, hace el primer commit, crea el repo privado en GitHub y lo publica
(`--no-remote` para no hacerlo), genera `CONTEXT.md` con el cartógrafo (`--no-context`) y, con
`--idea`, deja abierta la primera conversación de spec (`umbra spec resume`).

Los playbooks de umbra (`python`, `node`, `laravel`) viven dentro del paquete; los del equipo
van en `~/.umbra/playbooks/<stack>/` y tienen prioridad: `umbra playbook sync <repo-git>` los
clona o actualiza desde el repo del equipo (una carpeta por stack con `playbook.toml`:
`scaffold`, `default_routine`, `[commands]`, `[files]` = archivo del playbook → destino) y
`umbra playbook list` muestra los disponibles.

### Un proyecto que ya existe: onboarding

Antes de trabajar en un proyecto con historia, umbra lo estudia a fondo:

```bash
umbra onboard            # retoma donde quedó; --de-cero empieza otra vez
```

En Telegram es `/onboarding` (y `/adoptar` te lo ofrece al terminar). El recorrido:

1. **Reconocimiento** (sin modelo): stack, comandos que declara el proyecto, CI,
   documentación, instrucciones para IA que ya existan (CLAUDE.md, AGENTS.md, .cursorrules…),
   variables de entorno de ejemplo, migraciones, tamaño e historia de git.
2. **Línea base** (sin modelo): corre `test` y `lint` y anota qué pasa y qué ya fallaba antes de
   que umbra toque nada.
3. **Exploración**: cinco exploradores de solo lectura en paralelo (arquitectura, dominio,
   convenciones, interfaz con el inventario de vistas, y riesgos).
4. **Preguntas**: hasta 8, solo lo que el código no dice, con opciones (la recomendada primero)
   o texto libre.
5. **Redacción y revisión**: `CONTEXT.md` ampliado, la constitución del proyecto
   (`.specify/memory/constitution.md`: principios MUST/SHOULD con su evidencia, marcados «así se
   hace hoy» o «así queremos que se haga») y `specs/000-linea-base/` (inventario de
   capacidades, vistas, línea base y riesgos). Apruebas o pides cambios; al aprobar quedan en un
   commit «umbra: onboarding» en la rama actual (sin push).

**Después del onboarding**, la constitución trabaja en todo el ciclo:

- Todos los agentes la reciben, junto con la línea base de tests. El revisor marca como
  importante incumplir un MUST en lo que el cambio añade; el planificador y el constructor se
  detienen y preguntan si una tarea obliga a romper un principio.
- Cada spec nueva parte de **cómo funciona hoy** el área que toca: la conversación de spec la
  documenta primero (sección «Cómo funciona hoy») y especifica el cambio sobre esa base. Así el
  proyecto entra a SDD por las zonas donde trabajas, sin escribir specs de todo lo existente.
- La constitución se enmienda con tu aprobación:

```bash
umbra constitucion ver
umbra constitucion enmendar "los endpoints nuevos llevan test de contrato"   # diff → ¿apruebas?
```

En Telegram, `/constitucion` te manda el archivo y `/enmendar …` propone la enmienda con botones.

Las notas de trabajo quedan en `.umbra/artifacts/onboarding/` (no se versionan). Cuesta unos
pocos dólares en un repo mediano: los exploradores usan Sonnet y el redactor, Opus.

### Varios repos

`umbra init` y `umbra new` registran cada repo en `~/.umbra/projects.json`. `umbra watch --all`
los lista (cuántas tareas te necesitan, cuántas en marcha, gasto); Enter entra en el `watch`
de ese repo y `P` vuelve a la lista. `umbra projects` imprime la misma lista.

### Front y back en repos separados: espacio de trabajo

Si tu proyecto es una carpeta con varios repos dentro (por ejemplo
`landing-manager/{api-landing-manager,front-landing-manager}`), ejecuta `umbra init` en la
carpeta padre: umbra crea un **espacio de trabajo** con todos ellos (`-y` para no preguntar).
Desde ahí, o desde dentro de cualquiera de sus repos, hay una sola cola, un `watch` y un
Telegram.

```toml
# <carpeta>/.umbra/project.toml (no se versiona: la carpeta padre no es un repo)
[workspace]
repos = ["api-landing-manager", "front-landing-manager"]  # orden de integración
```

- El orden sale del `.code-workspace` si lo tienes (si no, alfabético). Pon primero lo que los
  demás necesitan: normalmente, el back.
- Cada repo conserva su `.umbra/project.toml` versionado con su stack, comandos de test, lint y
  dev, rama base y política. El del espacio guarda lo común: avisos, paralelo, piloto
  automático y editor.
- Cada historia de la spec dice dónde se hace con una línea `**Repo**: <nombre>` (la
  conversación de la spec ya lo sabe). Las historias se encadenan: la del front espera a que la
  del back esté integrada. Para una tarea suelta: `umbra task add "…" --repo <nombre>` o
  `umbra task repo <n> <nombre>`.
- Cada tarea trabaja en un worktree de su repo, con sus tests y su política. Al integrarse todas
  las de una spec, hay un PR de spec por repo. `umbra approve --spec` los integra en el orden del
  espacio; si uno falla, el resto queda como estaba y aprobar de nuevo integra solo lo que faltó.
- Lo que depende de un repo concreto se le indica: `umbra exec test --repo <nombre>`.
- **Tareas entre repos.** Si un cambio solo tiene sentido completo en varios repos (un campo que
  viaja de la base de datos a la pantalla), la historia los nombra todos: `**Repo**: api, front`
  (o `umbra task add "…" --repo api --repo front`). Un solo agente trabaja en una carpeta con un
  worktree de cada repo y ve los dos lados. Cada repo pasa su política y sus tests, y la tarea
  avanza solo si pasan todos. Hay un PR por cada repo que cambió, enlazados entre sí, y una sola
  aprobación cubre todos; un commit nuevo en cualquiera la invalida. En VERIFY, umbra levanta el
  `dev` de cada repo en orden y pasa la URL de los anteriores como `UMBRA_URL_<REPO>` (por
  ejemplo, `UMBRA_URL_API`): haz que el front la use para apuntar al back de la tarea. El
  navegador abre la app del último repo, o la de `[workspace] app`. En estas tareas se salta la
  etapa de diseño: diseña antes, en una tarea del front.
- Si un repo ya tenía tareas en marcha con su propio umbra, termínalas antes de unirlo. El
  onboarding se hace en cada repo antes de crear el espacio.

## 3. De la spec a las tareas

```bash
umbra plan docs/spec.md          # el proponente sugiere tareas en borrador
umbra task list                  # revisa; la columna "espera a" muestra dependencias
umbra task edit 3 -a "criterio nuevo" --expect-revision 1
umbra task deps 5 --on 3
umbra task accept 3 4 5          # o: umbra task drop 4
umbra task add "Arreglar X" -d "..." -a "criterio verificable"   # tarea a mano
```

### De la idea a las tareas

```bash
umbra spec new "mi idea"         # conversación interactiva: spec, plan y tareas en borrador
umbra spec tasks specs/001-mi-idea   # tareas en borrador por historia, sin conversación
umbra spec resume 001            # reabre la conversación en la fase donde quedó
umbra spec list                  # avance por spec: fase, historias hechas, costo
```

- `spec new` te guía por la spec, el plan y las tareas; entre fases hay **puntos de control**
  donde revisas y apruebas antes de seguir.
- `spec tasks <carpeta>` crea las tareas en borrador sin abrir conversación; si editaste las
  historias, ofrece actualizar las ya creadas (`--yes` acepta, `--json` para scripts).
- `spec resume [NNN|carpeta]` retoma una conversación interrumpida.
- `spec list` solo consulta: muestra el avance de cada spec.
- En `umbra chat`, `spec list` se consulta sin pedir permiso y `spec tasks` pide confirmación;
  `spec new` y `spec resume` abren una pantalla interactiva, así que se ejecutan en tu terminal.
  Por Telegram la misma conversación se abre con `/spec idea` o pidiéndola con tus palabras
  («crea una spec para…»): umbra la abre ahí y te pregunta con botones.

## 4. Ejecutar

```bash
umbra run 3                      # vuelve enseguida; el worker sigue aunque cierres la terminal
umbra log 3 -f                   # qué va pasando, contado en frases (--raw: registro técnico)
umbra watch                      # panel: tareas, situación explicada y línea de tiempo
```

### Entender dónde está una tarea

```bash
umbra status                     # qué necesita tu atención y qué está en marcha
umbra explain 3                  # por qué está así y qué puedes hacer, con los comandos
```

`umbra explain` responde siempre lo mismo: **qué pasó**, **por qué** umbra se comporta así
(la regla o el concepto detrás) y **qué puedes hacer**, cada opción con su comando. En
`umbra watch`, el panel «Situación» muestra eso para la tarea seleccionada; `t` alterna entre
la línea de tiempo narrada y el registro técnico.

| Situación | Qué significa |
| --- | --- |
| Borrador / Aceptada / Lista para ejecutar | Aún no se ha ejecutado |
| En cola / Trabajando / En pausa | El motor la tiene entre manos |
| Espera tu aprobación | Terminó todo; falta tu `umbra approve` |
| **Detenida** | umbra frenó por una regla o un resultado: **necesita tu decisión** |
| **Falló** | Problema técnico (sesión, red, error): normalmente basta con reintentar |
| Integrada / Cancelada | Terminó |

Si una tarea está detenida, `umbra run` no la reinicia en silencio: te pide elegir entre
continuar (`umbra retry 3`, el agente recibe el motivo de la detención) o empezar de cero
(`umbra run 3 --new`).

### Manejar todo desde `umbra watch`

La lista va ordenada por atención: `⚠` lo que te necesita (espera aprobación, detenida,
fallida), `▶` lo que trabaja o espera turno, `·` lo que falta por hacer y `✓` lo terminado.
Cada fila muestra el progreso por etapas (`●` hecha, `▶` en curso, `■` detenida, `✗` falló),
el costo y el tiempo. La cabecera resume el proyecto: worker vivo o parado, tareas en cola,
gasto acumulado y cuántas te necesitan.

Debajo van los intentos de la última ejecución, las specs y dos paneles: a la izquierda la
**Situación** (qué pasó, por qué y qué puedes hacer, en lenguaje llano); a la derecha, lo que
elijas con una tecla (la misma tecla vuelve a «Qué ha pasado»):

| Tecla | Panel derecho |
| --- | --- |
| (por defecto) | Qué ha pasado: la línea de tiempo narrada (`t` cambia al registro técnico) |
| `e` | Evidencia: el informe explicado en color y las últimas líneas de las pruebas |
| `d` | Cambios: archivo por archivo con líneas añadidas y quitadas, y el parche |
| `g` | Agente: qué hace ahora mismo: qué lee, edita, ejecuta y dice |
| `m` | Aprendido en este repo: lo que decidiste y los agentes ya saben |

Selecciona una tarea con las flechas y actúa con una tecla. El pie de pantalla muestra solo
las teclas que aplican a esa tarea:

| Tecla | Acción | Disponible cuando la tarea está… |
| --- | --- | --- |
| `a` | Aceptar; o autorizar el cambio que la política frenó | En borrador; detenida por política |
| `r` | Responder al agente (sigue donde quedó) | Detenida por preguntas |
| `T` | Integrar todas las que esperan | Dos o más esperan aprobación |
| `x` | Descartar (pide confirmación) | En borrador o lista |
| `r` | Ejecutar, o reintentar eligiendo la etapa | Lista, detenida o fallida |
| `n` | Empezar de cero (pide confirmación) | Detenida o fallida |
| `o` | Abrir en tu editor; de nuevo: confirmar tu arreglo y que umbra siga | Detenida, fallida o esperando aprobación |
| `I` | Integrar la spec completa (su PR a la rama base) | La spec de la tarea espera tu aprobación |
| `N` | Modo noche: aceptar los borradores y encolar lo que pueda ir | Siempre |
| `p` | Pausar / retomar | En cola, trabajando o en pausa |
| `c` | Cancelar (pide confirmación) | En marcha, detenida o esperando aprobación |
| `e` · `d` · `g` | Evidencia · Cambios · Agente en el panel derecho | Con alguna ejecución |
| `h` | Decidir hallazgos («no aplica» o «se hará después») | Con hallazgos abiertos |
| `A` | Aprobar e integrar: muestra la evidencia y pide confirmar | Espera tu aprobación |
| `R` | Rechazar, indicando el motivo | Espera tu aprobación |
| `t` · `?` · `q` | Registro técnico/narrado · ayuda · salir | Siempre |

Todas están también en la paleta (`Ctrl+P`). Cada acción ejecuta exactamente lo mismo que
su comando y, al terminar, te muestra el comando equivalente. En las ventanas de
confirmación la opción seleccionada por defecto es «No».

- **Tema**: `watch` trae «umbra» (oscuro) y «umbra-claro»; desde la paleta (`Ctrl+P` → *Theme*)
  puedes elegir cualquiera, también los integrados como «dracula». El elegido se recuerda en
  `~/.umbra/watch.json`.
- **Horas**: todo se muestra en la hora de tu máquina; el registro marca el cambio de día.
- **Avisos**: cuando una tarea te necesita, `watch` avisa en pantalla (y con campana, salvo
  `[notify] bell = false`); si no está abierto, llega el aviso del sistema (`[notify] desktop`).
  Nunca los dos.
- **Spec desde `watch`** (`s`): la conversación se abre dentro de la misma pantalla, con el
  mismo tema; `Esc` vuelve a la vista y la conversación queda retomable con `s` o
  `umbra spec resume`.
- Los agentes que umbra lanza no heredan tus plugins ni ganchos globales de Claude Code: solo la
  configuración del proyecto (ver «Seguridad»).

La rutina `feature` recorre:

```text
PLAN → BUILD → REVIEW → VERIFY → SCAN → SHIP ──(umbra approve)──▶ SUCCEEDED
         ▲                          │
         └── hallazgos ≥ block_on ──┘  (máx. 2 ciclos; luego BLOCKED)
```

- BUILD ejecuta el comando `test` registrado. Si falla, el agente recibe la salida y reintenta.
- Los tests existentes se protegen: se pueden **añadir** tests (en archivos nuevos o al final
  de uno existente, ampliando imports si hace falta), pero borrarlos, quitar o cambiar sus
  líneas o desactivarlos (`skip`, `xfail`, `.only`) detiene la tarea. Tocar rutas protegidas
  también.
- REVIEW la hace por defecto Codex en solo lectura; VERIFY comprueba cada criterio.
- SCAN bloquea cualquier secreto y devuelve a BUILD si falla un comando SAST.
- SHIP publica la rama y abre el PR. La ejecución queda en `WAITING_APPROVAL`.

Control: `umbra pause 3`, `umbra resume 3`, `umbra cancel 3` y
`umbra retry 3 --from build`.

**Arreglarlo tú.** Si una tarea se detiene y lo más rápido es corregir a mano: `umbra open 3`
(o `o` en `watch`) abre su espacio de trabajo en tu editor (`[editor] command` en
`.umbra/local.toml` o `project.toml`; si no, `$VISUAL`, `$EDITOR` o `code`). Cuando termines, `umbra done 3 -m "qué
arreglaste"` (o `o` de nuevo) confirma tus cambios como un commit tuyo, corre los tests del
proyecto como evidencia y la tarea sigue desde Revisar (en `quick`, directo a Publicar). Si los
tests quedan en rojo, la tarea sigue detenida y ves la salida. Tu arreglo cuenta como un intento
más, firmado «tú», en el registro, la evidencia y `watch`.

### Varias a la vez y specs que se integran solas

- **`[blocks] parallel = 2`** (`project.toml`): umbra atiende hasta dos tareas a la vez, cada
  una en su worktree; las dependencias entre tareas se respetan. Con `1` (o sin la línea) va
  una a la vez.
- **Rama de spec**: una tarea creada desde una spec (`umbra spec tasks`) parte de la rama
  `spec/<carpeta>` (umbra la crea desde la base si no existe) y, al pasar tests, revisión,
  verificación y política, su PR se integra ahí sin pedirte nada. El piloto automático arranca
  entonces las siguientes que ya pueden ir. `[spec] branch = false` desactiva este modo.
- **Una aprobación por spec**: con todas las historias integradas, umbra abre el PR
  `spec/<carpeta> → base`, avisa una vez y la lista de specs lo muestra como «espera tu
  aprobación». `umbra approve --spec <carpeta>` (o `I` en `watch` sobre cualquier tarea de la
  spec) lo integra.
- **Modo noche**: `umbra night` (o `N` en `watch`) acepta todos los borradores y encola lo que
  pueda ir; `--spec <carpeta>` lo limita a una spec. Con `[autopilot] enabled = false` solo
  arrancan las que caben ahora.

### Verificar viendo la app en el navegador

Registra el servidor de desarrollo en `.umbra/project.toml`:

```toml
[commands]
dev = { run = "php artisan serve --port=8765", background = true, url = "http://127.0.0.1:8765" }
```

Antes de Verificar, umbra lo levanta sobre el código de la tarea, espera a que la `url`
responda (`ready_timeout_s`, 60 por defecto) y le pasa la app al verificador, que la recorre
con un navegador (el MCP de Playwright; hace falta `npx`) y deja una captura por criterio visto.
Las capturas quedan en `.umbra/artifacts/<intento>-shots/` como evidencia ligada al SHA
verificado; el informe de aprobación las cuenta y `umbra evidence N --raw` las lista. Al
terminar, umbra apaga la app. Si no responde a tiempo, la tarea se detiene («la app de
desarrollo no respondió»). Sin `dev`, Verificar funciona como siempre.

### Diseñar antes de construir

En la rutina `feature`, después de Planificar va **Diseñar**. Corre solo si el planificador dice
que la tarea toca lo que la persona ve (pantallas, componentes, estilos, web o móvil); si no,
se salta.

umbra trae un diseñador estándar (`designer`, Opus) que no depende de ninguna herramienta. Por
defecto diseña en HTML y CSS dentro de `design/maquetas/` y fotografía cada pantalla con el
navegador (Playwright; en Windows usa Edge). La primera vez deja el sistema del proyecto en
`design/sistema.md`: paleta, tipografía, espaciado, radios y componentes. Las tareas siguientes
lo respetan.

**Conectar tu herramienta** (Figma, Pencil o cualquiera con servidor MCP) no requiere tocar el
perfil. Se hace en `~/.umbra/local.toml`, para ti en todos tus proyectos, o en
`.umbra/project.toml`, para un proyecto:

```toml
[design]
guides = ["~/.umbra/design/mi-equipo.md"]   # cómo usar tu herramienta, tu marca, tu librería
starter = "~/.umbra/design/kit.fig"         # archivo base: se copia a design/<proyecto>.fig

[design.mcp.mi-herramienta]
command = "mi-herramienta-mcp"
args = ["--modo-agente"]
env = { ALGUNA_OPCION = "1" }
```

El diseñador recibe esos servidores (además del navegador) y las guías; el crítico también lee
las guías. `starter` (opcional) es el archivo del que parte el diseño de cada proyecto, p. ej. la
librería de componentes de tu equipo: la primera vez umbra lo copia a `design/` y el diseñador
trabaja sobre esa copia. Las listas no se suman entre capas: si un proyecto define `guides`,
incluye también las tuyas generales. Para cambiar el perfil entero, pon tu `designer.toml` en el proyecto, en `~/.umbra`
o en un paquete.

El diseñador solo puede tocar la carpeta `design/` del proyecto y debe devolver las pantallas
exportadas (`images`). Después la tarea se detiene esperando tu visto bueno, y las pantallas te
llegan como fotos a Telegram:

```bash
umbra design ok 3                       # aprobado: Construir maqueta sobre él
umbra design cambios 3 "menos texto"    # el diseñador lo ajusta y vuelve a preguntarte
```

En `watch`, `a` aprueba y `r` pide cambios. En Telegram, el botón «Aprobar diseño» o responder al
mensaje con lo que quieres cambiar. Lo aprobado viaja a Construir, que maqueta fiel a esas
pantallas, y a Verificar, que compara la app con ellas. El informe lo dice: «Maquetado sobre el
diseño que aprobaste». Con `human_approval: false` en la etapa, el diseño se aprueba solo.

**Sistemas de diseño.** Tu catálogo vive fuera de los repos: una carpeta por sistema en
`~/.umbra/design/<sistema>/` (o en un paquete, en `design/<sistema>/`) con su `sistema.toml`:

```toml
nombre = "Kit del equipo"
descripcion = "apps web internas"
guias = ["guia.md"]          # reglas de uso, marca, componentes
starter = "kit.umbra"        # el archivo de la librería: se copia a design/ del proyecto
```

Cada proyecto declara cuál usa con `[design] system = "<sistema>"` en `.umbra/project.toml`
(versionado), o `"ninguno"` para que el diseñador defina o extraiga el suyo. Si hay catálogo y
el proyecto aún no lo dijo, umbra pregunta al abrir una spec (`umbra spec new`, `/spec`) y en el
onboarding. `umbra design sistemas` lista el catálogo; `umbra design sistema [nombre]` y
`/sistema` lo muestran o lo cambian. El diseñador recibe las guías del sistema y parte de su
archivo.

**Réplica del diseño actual.** En un proyecto que ya tiene interfaz:

```bash
umbra design replicar      # o /replicar; se ofrece al aprobar el onboarding
```

umbra levanta la app con `dev`, recorre las vistas del inventario del onboarding
(`specs/000-linea-base/vistas.md`) con el navegador y deja una captura por vista en
`design/actual/` con su índice (vista, ruta, archivo), además del sistema visual que el código ya
usa en `design/sistema.md`. Con una herramienta de diseño conectada, crea también un tablero
`Actual · <Vista>` por vista y las variables y componentes base. Apruebas (commit) o descartas.
Desde ahí puedes pedir «en la vista Ajustes cambia esto»: el diseñador reconstruye esa vista
editable, fiel a la captura, y aplica solo el cambio. Si la app pide login, `[design.replica]`
con `usuario` y `clave_env` (el nombre de una variable de entorno); úsalo solo con usuarios de
prueba locales, porque la clave viaja en el sobre del agente.

Antes de preguntarte, el diseño pasa por dos filtros:

- **Revisiones automáticas**: lo que la herramienta del propio diseñador detecta (contraste,
  texto cortado, objetivos táctiles pequeños) y devuelve como observaciones.
- **Crítica**: un segundo agente (`design-critic`, Opus) mira las pantallas con una rúbrica:
  jerarquía, alineación, espaciado, contraste, consistencia, tipografía, objetivos táctiles,
  estados y oficio.

Las observaciones desde `block_on` (en `feature`, `medium`) devuelven el diseño al diseñador,
hasta `max_fix_cycles` rondas. Lo que siga pendiente te llega junto con la pregunta («El crítico
todavía ve…»), y tú decides.

**Direcciones.** La primera vez que un proyecto se diseña, el diseñador propone 2 o 3
direcciones de la pantalla clave. Te llegan como fotos, una por dirección, con un botón para
cada una (`umbra design elegir N 2`; en `watch`, `a` y el número). El diseñador sigue la que
elijas. Responder al mensaje pide otra ronda.

**Tu gusto.** Cada dirección que eliges (frente a las que no), cada cambio que pides y cada
diseño que apruebas quedan en `~/.umbra/gusto.md`, que es tuyo y vale para todos tus proyectos.
El diseñador y el crítico lo reciben en cada tarea. Puedes editarlo a mano. `umbra design gusto`
y `/gusto` en Telegram lo muestran.

### Decidir desde el teléfono (Telegram)

1. Crea un bot con @BotFather y guarda su token en una variable de entorno (por ejemplo
   `UMBRA_TELEGRAM_TOKEN`); escribe al bot y averigua tu `chat_id` (por ejemplo con
   `https://api.telegram.org/bot<token>/getUpdates`).
2. En `~/.umbra/local.toml` (vale para todos tus repos) o en `.umbra/local.toml` del repo
   (configuración tuya: git la ignora y se lee encima de `project.toml`):

   ```toml
   [notify.telegram]
   token_env = "UMBRA_TELEGRAM_TOKEN"
   chat_id = 123456789
   ```

3. Desde entonces, cada tarea que se detiene o espera aprobación llega con botones, y cada spec
   completa con «Integrar la spec». Pulsar ejecuta el comando equivalente (queda registrado con
   origen `telegram` y tu usuario). Para contestar al agente escribe «3 tu respuesta» o responde
   al mensaje de esa tarea. `umbra bridge` es quien atiende el teléfono: umbra lo arranca solo al
   encolar trabajo y `umbra bridge --stop` lo para. Solo atiende a tu `chat_id`.
4. **Conversa**: cualquier otro mensaje es hablar con umbra sobre el proyecto actual («¿cómo
   va?», «¿por qué se detuvo la 3?», «encola la 4 y acepta la 5»), con la misma conversación de
   `umbra chat --allow-changes` hilada entre mensajes: responde y actúa; aprobar, rechazar y
   fusionar siguen siendo botones (o `/integrar`). `/nuevo` reinicia la conversación. Si una
   respuesta falla, el detalle queda en `.umbra/artifacts/chat/last-error.log`.
5. **La consola en el teléfono**: cuando una tarea queda lista llega su informe (qué se hizo,
   cómo se comprobó, cambios, costo, PR) y, si se verificó en el navegador, las capturas como
   fotos. El bot trae un menú con todo lo de `watch`: `/tareas`, `/explicar N`, `/registro N`,
   `/evidencia N`, `/cambios N`, `/agente N`, `/hallazgos N`, `/tarea título | criterio`,
   `/aceptar`, `/ejecutar`, `/reintentar N [etapa]`, `/decero`, `/pausar`, `/retomar`,
   `/cancelar`, `/descartar`, `/integrar`, `/rechazar N motivo`, `/noaplica`, `/despues`,
   `/noche [spec]`, `/integrar_spec nombre`. Y lo que empieza cosas: `/spec idea` (la
   conversación de requisitos por mensajes: preguntas con botones, puntos de control con
   Aprobar / Pedir cambios / Descartar, `/spec_ver` manda el archivo; termina con las tareas
   en borrador), `/spec_seguir [NNN]`, `/spec_salir`, `/plan ruta/spec.md` y
   `/nuevo_proyecto nombre stack [idea]` (crea el repo junto al actual con su playbook).
6. **Varios repos, un bot**: un solo puente atiende todos los repos registrados (`umbra init`,
   `umbra new`) con el mismo bot. `/proyectos` los lista con cuántas tareas te necesitan,
   `/usar <nombre>` cambia el proyecto actual y `/estado` resume qué te necesita. Cada aviso
   dice de qué repo viene y sus botones actúan sobre ese repo aunque el actual sea otro.
7. **Todas tus carpetas**: el puente también atiende los repos con umbra que estén en la misma
   carpeta que el repo desde el que arrancó (por ejemplo `C:/apps`), aunque no estén en el
   índice. `/proyectos` lista además las carpetas sin umbra, y `/adoptar carpeta` pone umbra en
   una de ellas. Si no era repo git, lo crea con un primer commit y un `.gitignore` básico que
   deja fuera `.env`, `node_modules/`, `vendor/` y entornos virtuales. Conversando también
   funciona: «pasemos a api-ventas y crea una tarea…», «adopta la carpeta rea» o «crea
   un proyecto node llamado tienda». umbra cambia de proyecto y sigue con tu mensaje allí.
   Nunca trabaja fuera de esa carpeta.
8. **Tu MySQL local**: la conversación consulta sin pedir permiso. Cuando algo requiere
   cambiar datos o estructura, te llega el SQL exacto con «Aplicar cambio» y «Descartar»; nada
   se ejecuta hasta que lo pulsas. Ver [MySQL local](#mysql-local).

## 5. Aprobar

```bash
umbra evidence 3                 # comandos, exit codes, SHAs, intentos, costo
umbra approve 3                  # muestra diff y evidencia, pide confirmación, fusiona
umbra reject 3 -m "motivo"
```

`approve` exige una terminal interactiva y que la rama no tenga commits posteriores al SHA
evaluado. La ejecución termina en `SUCCEEDED` solo cuando el proveedor confirma el merge.
`umbra approve --spec <carpeta>` integra una spec completa (ver arriba).

## 6. Conversar

```bash
umbra chat
```

Abre Claude Code con el estado del proyecto. Las consultas y los comandos `safe` corren sin
preguntar; lo que cambia estado pide confirmación; aprobar, rechazar, hacer push o merge y
editar la política están prohibidos.

### MySQL local

```bash
umbra db query "SELECT * FROM clientes LIMIT 10"     # solo lectura, sin pedir permiso
umbra db query "SHOW DATABASES"
umbra db query "DESCRIBE pedidos" --db tienda         # otra base del mismo servidor
umbra db change "UPDATE clientes SET activo = 0 WHERE id = 7"   # solo lo propone
umbra db list                                         # cambios que esperan tu decisión
umbra db apply a4ab4f97                               # lo aplica (terminal interactiva)
umbra db discard a4ab4f97
```

La conexión va en `~/.umbra/local.toml` (todos tus repos) o en `.umbra/local.toml` (la base de
ese repo). Sin nada configurado, umbra usa root sin contraseña en `127.0.0.1:3306`, lo normal en
Laragon o XAMPP:

```toml
[mysql]
host = "127.0.0.1"
port = 3306
user = "root"
password_env = "UMBRA_MYSQL_PASSWORD"   # el nombre de la variable, nunca la contraseña
database = "tienda"
```

Una consulta solo acepta SELECT, SHOW, DESCRIBE y EXPLAIN, de una en una y dentro de una
transacción de solo lectura, y devuelve hasta 200 filas. Un cambio puede tener varias
sentencias. Se aplica en una transacción y, si una falla, se revierte todo, salvo las
sentencias de estructura (CREATE, ALTER, DROP), que MySQL confirma al momento. Cada propuesta,
aplicación y descarte queda en el registro. La conversación puede consultar y proponer, pero
nunca aplicar.

## 7. Agentes y perfiles

```bash
umbra agent list
umbra profile list
umbra profile new revisor-seguridad --from reviewer-strict   # edita su .md
umbra agent add examples/agents/todo-reviewer && umbra agent test todo-reviewer
```

Ver [`adapters.md`](adapters.md) para integrar cualquier ejecutable como agente.

### Servidores MCP de un perfil

Un perfil de Claude Code puede declarar los servidores MCP que necesita. umbra se los pasa a
ese agente, y solo esos: nunca los MCP globales de tu instalación.

```toml
[mcp.lienzo]
command = "lienzo"
args = ["--sin-ventana", "--estilos", "{profile_dir}/estilos"]
env = { MODO = "agente" }
```

`{profile_dir}` es la carpeta del perfil y `{workspace}` la de la tarea. No pongas secretos en
`env`: el servidor hereda tu entorno, así que las claves van en variables de entorno.

### Paquetes

Lo que no debe vivir en el repo de umbra (los perfiles, rutinas y playbooks privados de un
equipo, un diseñador con su herramienta) va en un **paquete**: un repo git con las carpetas
`profiles/`, `routines/` y `playbooks/` que necesite.

```bash
umbra pack sync git@github.com:mi-equipo/umbra-equipo.git   # clona o pone al día
umbra pack list                                             # qué aporta cada uno
```

Quedan en `~/.umbra/packs/<nombre>/`. umbra busca cada perfil y rutina en este orden: el
proyecto (`.umbra/`), `~/.umbra/`, los paquetes y, por último, lo que trae umbra.

## 8. Lo que umbra aprende

- **`.umbra/aprendido.md`** (versionado): cada hallazgo que decides («no aplica» o «para
  después»), cada respuesta al agente y cada ruta que autorizas. Los agentes lo reciben en su
  sobre y un revisor que repite un hallazgo ya decidido no vuelve a frenar la tarea.
  `umbra memory show` lo muestra; `umbra memory rebuild` lo regenera desde el historial; `m` en
  `watch` lo abre.
- **`CONTEXT.md`** (raíz del repo): el mapa del proyecto (qué es, cómo está organizado, cómo se
  corre y se prueba, convenciones) que leen todos los agentes. Lo escribe el cartógrafo, un agente
  de solo lectura que solo puede tocar ese archivo: `umbra context build` lo genera y, tras cada
  tarea integrada, umbra lo pone al día solo (`[context] auto = false` lo desactiva).
- **Escalada y árbitro**: si Construir agota sus intentos, la rutina sigue con el siguiente
  perfil de `escalation` (por defecto `builder-strong`, Fable 5.1 con `effort = "xhigh"`); si
  tras los ciclos de revisión constructor y revisor no se ponen de acuerdo, el `arbiter` (Opus,
  solo lectura) decide qué hallazgos siguen. Ambos se configuran por etapa en
  `.umbra/routines/*.yaml`.
- **Revisor de respaldo**: si Codex falla por algo técnico (modelo saturado, sesión), la rutina
  `feature` revisa con Claude (`fallback_profile` en la etapa) en vez de detener la tarea.

## 9. Medir

```bash
umbra metrics
```

Muestra el tiempo hasta el PR y hasta el merge, el costo, los ciclos de corrección, la tasa de
aceptación inicial y el costo por entrega. Úsalo tras 10 a 20 tareas reales para fijar metas.

## Seguridad: lo que conviene saber

- Claude Code en modo `-p` carga `.claude/settings.json` y `.mcp.json` del repo sin preguntar.
  Por eso `umbra run` se niega si existen, salvo `--trust-repo-config` o
  `trust_repo_agent_config = true`.
- Con `isolation = "docker"`, los comandos del proyecto (donde corre código del repo) se
  ejecutan sin red y con límites. Los agentes siguen en el host con sus propios sandboxes.
