# Cambios de umbra-engine

Versionado semántico (`vMAYOR.MENOR.PARCHE`): PARCHE corrige, MENOR añade capacidades, MAYOR
llegará con la versión estable (1.0.0, tras el piloto en un proyecto real). Cada PR describe
aquí, en «Sin publicar», qué cambia para quien usa umbra. `umbra self-update` instala la última
versión publicada.

## Sin publicar

## v0.26.3 — 2026-11-05

- Abrir a la vez un proyecto nuevo desde dos sitios (el puente y una tarea, por ejemplo) ya no
  falla con «database is locked» ni «table already exists».

## v0.26.2 — 2026-11-05

- `/replicar` y `umbra design replicar` funcionan en un espacio de trabajo: levantan el back y
  luego el front (con `UMBRA_URL_<REPO>`) y guardan la réplica en el repo de la app.

## v0.26.1 — 2026-11-05

- Adoptar una carpeta con varios repos (`/adoptar` en Telegram) crea un espacio de trabajo en vez
  de convertir la carpeta padre en un repo que los envuelve.

## v0.26.0 — 2026-11-05

- **Espacios de trabajo** para proyectos con front y back en repos separados: `umbra init` en la
  carpeta padre los une en una sola cola, un `watch` y un Telegram. Cada historia dice su repo
  (`**Repo**: api`) y la spec se aprueba de una vez, con un PR por repo integrado en orden.
- **Tareas entre repos**: una historia con `**Repo**: api, front` la trabaja un solo agente con
  los dos repos a la vista, con los tests de cada uno, un PR por repo y una sola aprobación. En
  VERIFY se levantan los dos y el front recibe la URL del back (`UMBRA_URL_API`).

## v0.25.0 — 2026-11-05

- **Sistemas de diseño por proyecto**: un catálogo en `~/.umbra/design/` y cada proyecto elige el
  suyo (umbra pregunta al abrir una spec y en el onboarding; `umbra design sistema`, `/sistema`).
- **Réplica del diseño actual** (`umbra design replicar`, `/replicar`): una captura por vista con
  su índice y el sistema visual del código en `design/`, y en tu herramienta de diseño si la
  conectaste; luego puedes pedir cambios «en la vista X».

- La **constitución del proyecto** llega a todos los agentes (con la línea base de tests): el
  revisor la usa como rúbrica y se enmienda con tu aprobación (`umbra constitucion enmendar`,
  `/enmendar`). En proyectos con onboarding, cada spec documenta primero cómo funciona hoy lo
  que toca.

- **Onboarding de proyectos ya iniciados** (`umbra onboard`, `/onboarding`): umbra estudia el
  proyecto (reconocimiento, línea base de tests, cinco exploradores), te pregunta lo que el código
  no dice y redacta `CONTEXT.md`, la constitución del proyecto y el inventario para que los apruebes.

## v0.24.0 — 2026-11-05

- `[design] starter`: el archivo del que parte el diseño de cada proyecto (p. ej. la librería de
  componentes de tu equipo) se copia a `design/` la primera vez y el diseñador trabaja sobre él.

## v0.23.0 — 2026-11-05

- umbra trae un **diseñador estándar** que no depende de ninguna herramienta: diseña en HTML y
  CSS, fotografía las pantallas con el navegador y deja el sistema del proyecto en
  `design/sistema.md`. Tu herramienta (Figma, Pencil u otra con MCP) y tus guías se conectan en
  `[design]` de `~/.umbra/local.toml` o del proyecto.
- Verificar con navegador ya funciona en Windows sin Google Chrome: usa Edge.

## v0.22.0 — 2026-11-05

- `umbra self-update` ya no deja umbra roto: espera a que el puente de Telegram y lo que esté
  usando umbra terminen, comprueba que la versión nueva arranca (si no, vuelve a la anterior),
  relanza el puente y avisa por Telegram. Desde el teléfono, `/actualizar`.
- **Diseñar antes de construir**: si la tarea toca la interfaz y tienes un diseñador instalado,
  umbra la diseña en `design/`, te manda las pantallas (también a Telegram) y espera tu visto
  bueno (`umbra design ok N` / `umbra design cambios N "..."`). Construir maqueta sobre lo
  aprobado y Verificar lo compara con la app.
- **Paquetes**: `umbra pack sync <repo>` instala perfiles, rutinas y playbooks que viven fuera de
  umbra (lo privado de tu equipo) y `umbra pack list` los muestra. Los perfiles pueden declarar
  sus propios servidores MCP.
- El diseño pasa por un **crítico** con una rúbrica (jerarquía, alineación, espaciado, contraste,
  consistencia…) y por las revisiones automáticas de la herramienta del diseñador. Lo
  importante vuelve a corregirse antes de preguntarte.
- La primera vez que un proyecto se diseña, eliges entre 2 o 3 **direcciones** (fotos y un botón
  por cada una en Telegram, o `umbra design elegir N 2`).
- umbra **aprende tu gusto**: lo que eliges, pides y apruebas queda en `~/.umbra/gusto.md` y lo
  reciben el diseñador y el crítico (`umbra design gusto`, `/gusto`).

## v0.21.1 — 2026-11-05

- Por Telegram ya puedes pedir una spec con tus palabras («crea una spec para…»): umbra abre la
  conversación de spec ahí mismo en vez de mandarte a la terminal.

## v0.21.0 — 2026-11-05

- umbra es open source (Apache 2.0): se instala desde `github.com/alejoc0314/umbra-engine` y
  `umbra self-update` busca las versiones nuevas ahí.

## v0.20.0 — 2026-11-04

- **Todos tus proyectos desde Telegram**: el puente atiende cualquier repo con umbra de tu
  carpeta de proyectos (p. ej. `C:/apps`), `/proyectos` muestra también las carpetas sin umbra y
  `/adoptar carpeta` pone umbra en una (con `git init` y un primer commit si hacía falta). Al
  conversar, umbra ya no dice que no puede salir de la carpeta actual: cambia de proyecto, adopta
  carpetas o crea proyectos nuevos cuando se lo pides.
- **Tu MySQL local**: `umbra db query` consulta sin pedir permiso, y `umbra db change` solo
  propone el cambio. Aplicarlo es siempre decisión tuya, con el botón de Telegram o con
  `umbra db apply`. La conexión va en `[mysql]` de `~/.umbra/local.toml`.

## v0.19.1 — 2026-11-04

- En Telegram, lo que escribes sin más ya puede actuar (encolar, aceptar, reintentar, crear
  tareas…), como `umbra chat --allow-changes`; aprobar, rechazar e integrar siguen siendo
  botones. El mensaje de bienvenida lo cuenta así.
- Si `claude` falla sin texto, umbra ya no muestra «None»: dice el motivo que haya y deja la
  salida cruda en `.umbra/artifacts/chat/last-error.log`; en Telegram, una conversación retomada
  que ya no existe se reabre sola de cero.

## v0.19.0 — 2026-11-04

- **Telegram como consola**: cuando una tarea queda lista, al teléfono llega el informe (qué se
  hizo, cómo se comprobó, cambios, costo, PR) y las capturas del navegador como fotos. Y todo lo
  de `watch` por comandos con menú en el bot: `/tareas`, `/explicar N`, `/registro N`,
  `/evidencia N`, `/cambios N`, `/agente N`, `/hallazgos N`, `/tarea título | criterio`,
  `/aceptar`, `/ejecutar`, `/reintentar`, `/decero`, `/pausar`, `/retomar`, `/cancelar`,
  `/descartar`, `/integrar`, `/rechazar`, `/noaplica`, `/despues`, `/noche`, `/integrar_spec`.
- **Specs, planes y proyectos desde el teléfono**: `/spec idea` lleva la conversación de
  requisitos por mensajes (las preguntas con sus opciones como botones, los puntos de control
  con Aprobar / Pedir cambios / Descartar, `/spec_ver` manda el archivo) hasta dejar las tareas
  en borrador; `/spec_seguir` y `/spec_salir`; `/plan ruta/spec.md`; `/nuevo_proyecto nombre
  stack [idea]`.
- **`~/.umbra/local.toml`** vale para todos tus repos (Telegram, editor…); el `.umbra/local.toml`
  de cada repo lo afina.

## v0.18.2 — 2026-11-04

- Las respuestas de umbra en Telegram llegan formateadas (negritas, títulos, código, viñetas) en
  vez de mostrar los asteriscos y almohadillas del Markdown.

## v0.18.1 — 2026-11-04

- **`.umbra/local.toml`**: configuración tuya que no viaja con el repo (git la ignora; `umbra
  init` lo añade al `.gitignore`): ahí van `[notify.telegram]`, `[editor]` o cualquier ajuste
  personal. Se lee encima de `project.toml`, tabla a tabla.

## v0.18.0 — 2026-11-04

- **Conversar con umbra desde Telegram**: lo que escribes al bot sin más es una pregunta a
  umbra sobre el proyecto actual («¿cómo va?», «¿por qué se detuvo la 3?», «¿qué costó la
  spec?»), con la misma conversación de `umbra chat` hilada entre mensajes (solo lectura);
  `/hacer …` permite que cambie estado (encolar, aceptar…), nunca aprobar ni fusionar.
  Un solo puente atiende todos tus repos: `/proyectos` los lista, `/usar <nombre>` cambia el
  actual, `/estado` resume qué te necesita, `/nuevo` reinicia la conversación. Cada aviso dice
  de qué repo viene y sus botones actúan sobre ese repo. `umbra bridge --stop` lo para.

## v0.17.0 — 2026-11-04

- **`umbra new <nombre> --stack python|node|laravel`**: un proyecto nuevo en un comando: carpeta
  con git, andamiaje del stack, CI, `AGENTS.md`, `.umbra/project.toml` con sus comandos y
  rutina, primer commit, repo privado en GitHub (`--no-remote` lo evita), `CONTEXT.md` del
  cartógrafo (`--no-context`) y, con `--idea "…"`, la primera spec abierta. Los **playbooks**
  del equipo van en `~/.umbra/playbooks/<stack>/` (`umbra playbook sync <repo>` los trae;
  `umbra playbook list` los muestra) y pisan a los de umbra.
- **`umbra watch --all`**: tus repos con umbra en una pantalla (cuántas tareas te necesitan,
  cuántas en marcha y el gasto); Enter entra en uno y `P` vuelve a la lista. `umbra projects`
  es la misma lista en la terminal. `umbra init` y `umbra new` registran cada repo.

## v0.16.0 — 2026-11-04

- **Verificar viendo la app**: si registras `dev = { run = "php artisan serve", background =
  true, url = "http://127.0.0.1:8000" }` en `project.toml` (`umbra init` lo hace en Laravel),
  umbra levanta la app sobre el código de la tarea antes de Verificar, el verificador la recorre
  en un navegador (Playwright, vía `npx`) y deja capturas como evidencia ligadas al SHA; luego la
  apaga. El informe dice «Visto en el navegador: N capturas». Sin `dev`, nada cambia.

## v0.15.0 — 2026-11-04

- **Decidir desde el teléfono**: con un bot de Telegram propio (`[notify.telegram] token_env` y
  `chat_id` en `project.toml`; el token solo en el entorno), cada tarea que se detiene o espera
  aprobación llega al teléfono con botones (Autorizar, Reintentar, De cero, No aplica, Integrar,
  Rechazar, Ver cambios) y cada spec lista con «Integrar la spec». Pulsar ejecuta el comando;
  escribir «3 tu respuesta» contesta al agente. `umbra bridge` atiende el teléfono (umbra lo
  arranca solo al encolar trabajo; `umbra bridge --stop` lo para).

## v0.14.0 — 2026-11-04

- **Varias tareas a la vez**: con `[blocks] parallel = 2` en `project.toml` (lo trae `umbra init`),
  umbra trabaja hasta dos tareas a la vez, cada una en su worktree, respetando las dependencias.
- **Aprobación por spec**: las tareas de una spec trabajan sobre la rama `spec/<carpeta>` y, al
  pasar tests, revisión, verificación y política, se integran solas ahí. Cuando están todas,
  umbra abre un único PR de la spec a la rama base y avisa una vez: `umbra approve --spec
  <carpeta>` (o `I` en `watch`) integra la spec completa. Las tareas sin spec siguen pidiendo
  aprobación una a una.
- **Modo noche**: `umbra night [--spec <carpeta>]` (o `N` en `watch`) acepta los borradores y
  encola lo que pueda ir; el piloto automático encadena el resto a medida que se integran. Por
  la mañana solo quedan specs por aprobar o tareas detenidas con su motivo.

## v0.13.0 — 2026-11-04

- **Arreglar a mano y que umbra siga**: cuando una tarea se detiene, `umbra open 3` (o la tecla
  `o` en `watch`) abre su espacio de trabajo en tu editor (`[editor] command`, `$VISUAL` o
  `$EDITOR`); tras corregir, `umbra done 3 -m "qué arreglaste"` (o `o` de nuevo) confirma tu
  cambio, corre los tests como evidencia y la tarea sigue desde Revisar sin volver a construir.
  Tu arreglo aparece como un intento más («tú») en el registro y la evidencia.

## v0.12.0 — 2026-11-04

- **Escalada automática**: si Construir agota sus intentos, umbra sigue sola con un perfil más
  fuerte (`builder-strong`: Fable 5.1 con esfuerzo alto) antes de detenerse; y si constructor y
  revisor no se ponen de acuerdo tras tres rondas, un **árbitro** (Opus 5.5, solo lectura) decide
  qué hallazgos siguen en pie. Menos `retry` a mano. Se configura por etapa en la rutina
  (`escalation`, `arbiter`) y los perfiles aceptan `effort`.

## v0.11.0 — 2026-11-04

- El costo de una tarea se ve más corto, como `$0.42 + 60k tokens` (dólares de Claude más tokens
  de Codex), sin la etiqueta «sin precio».
- Lo que decides una vez vale para siempre: los hallazgos que marcas «no aplica» o «para
  después», tus respuestas al agente y las rutas que autorizas quedan en `.umbra/aprendido.md`
  (versionado con el repo) y los agentes lo reciben en las tareas siguientes; un revisor que
  repite un hallazgo ya decidido no vuelve a frenar la tarea. `umbra memory show` lo muestra y
  `umbra memory rebuild` lo regenera desde el historial. En `watch`, `m` lo muestra.
- `CONTEXT.md`, el mapa del repositorio que leen todos los agentes: `umbra context build` lo
  genera con el cartógrafo (solo puede escribir ese archivo) y umbra lo pone al día tras cada
  tarea integrada (`[context] auto = false` lo desactiva).
- Si Codex falla al revisar (modelo saturado, sesión), la rutina `feature` revisa con Claude en
  vez de detener la tarea (`fallback_profile`).

## v0.10.3 — 2026-11-04

- El informe de evidencia (panel y confirmación de aprobar) se envuelve al ancho real de la
  pantalla: se acabaron las líneas cortadas con sangría rota.

## v0.10.2 — 2026-11-04

- Los constructores (`builder-tdd` y `builder`) construyen con **Claude Fable 5.1** y, si no está
  disponible, con Opus 5.5 (`fallback_model` en el perfil); el planificador usa Opus 5.5. Su
  presupuesto por intento sube a 5 USD.

## v0.10.1 — 2026-11-04

- `umbra self-update` y el resto de comandos ya no fallan en consolas de Windows que arrancan en
  cp1252 cuando un aviso trae un símbolo como «−» o «✓».

## v0.10.0 — 2026-11-04

- **Decidir desde `watch`**: cuando una tarea te necesita, el panel «Situación» pasa a ser
  «Decisión» con las teclas que lo resuelven. `a` autoriza, solo para esa tarea, el cambio de
  tests o rutas protegidas que la política frenó (queda registrado quién) y sigue desde
  Construir; `r` responde a las preguntas del agente y sigue donde quedó; `T` integra todas las
  que esperan; `h` decide hallazgos abiertos aunque no frenen. En la terminal:
  `umbra task allow <n> <rutas>`, `umbra task answer <n> "texto"`, `umbra approve --all`.
- Tras integrar, tu copia local de la rama base queda al día (si está limpia y en esa rama).

- `umbra watch` es ahora la consola: la lista va ordenada por atención (primero lo que te
  necesita, luego lo que trabaja, lo que falta y al final lo hecho), cada fila muestra el
  progreso por etapas, el costo y el tiempo, y la cabecera dice si el worker está vivo, cuántas
  tareas hay en cola, el gasto acumulado y cuántas te necesitan.
- El panel derecho muestra, además de «Qué ha pasado», la **Evidencia** (`e`: el informe en color
  y la salida de las pruebas), los **Cambios** (`d`: archivo por archivo con +/- y el parche) y el
  **Agente** (`g`: qué hace ahora mismo: qué lee, edita, ejecuta y dice). La misma tecla vuelve.
- Aprobar muestra el mismo informe en color dentro de la confirmación.
- Los registros de los agentes se escriben mientras trabajan, no solo al terminar.
- En terminales de menos de 100 columnas la lista y el detalle se apilan.

- `umbra watch` responde al instante aunque el proyecto crezca: solo recalcula cuando algo cambió,
  actualiza las celdas que cambian sin perder el cursor ni el scroll, y nada lento (git, evidencia)
  corre en el hilo de la pantalla.
- Las horas de `watch` y de `umbra log` son las de tu máquina (antes salían en UTC) y el registro
  marca el cambio de día.
- Tema propio «umbra» (oscuro) y «umbra-claro», con colores por estado; los temas integrados
  siguen disponibles y el que elijas se recuerda. Si no eliges, se usa «umbra».
- La conversación de spec (`s`) se abre dentro de `watch`, con el mismo tema y sin parpadeo; `Esc`
  vuelve a la vista y la conversación queda retomable.
- Un solo aviso por tarea que te necesita: en pantalla si `watch` está abierto, del sistema si
  no. `[notify] bell = false` apaga la campana.
- Los agentes que lanza umbra ya no heredan tus plugins ni ganchos globales de Claude Code.

- `umbra chat "pregunta"` responde en la terminal y termina, sin abrir la sesión; con `-` lee el
  mensaje de la entrada estándar.
- `umbra chat "mensaje" --json` devuelve un único objeto JSON con la respuesta, la conversación,
  el costo, los comandos de umbra ejecutados y el estado (también cuando hay un error).
- `umbra chat "mensaje" --allow-changes` permite que Claude ejecute comandos que cambian estado
  (por ejemplo `umbra run 3`); sin la opción solo te dice el comando exacto. Aprobar, rechazar,
  push, merge y editar la política siguen bloqueados siempre.
- `umbra chat "mensaje" --continue` sigue la última conversación del proyecto (o empieza una
  nueva y lo avisa); `--session ID` continúa una conversación concreta.
- El costo de una tarea se ve como `$0.42 + 60k tokens` (dólares de Claude más tokens de Codex),
  sin la etiqueta «sin precio».

## v0.9.1 — 2026-10-30

- `umbra self-update` muestra las notas de la versión sin cortes a mitad de frase.

## v0.9.0 — 2026-10-30

De la idea a las tareas: umbra conversa contigo para escribir la spec y el plan, y los convierte
en tareas. Primera capacidad que umbra construyó con sus propias tareas.

- **`umbra spec new "idea"`**: una pantalla de conversación te lleva de la idea a la spec, el
  plan y las tareas en borrador. Las preguntas traen la respuesta recomendada primero (o
  escribes la tuya), y antes de seguir apruebas o pides cambios en la spec y en el plan.
  Descartar pide confirmación. Si el gasto pasa del límite (5 USD por defecto, `[spec]
  max_cost_usd`), la conversación se pausa y te avisa.
- **`umbra spec resume`**: retoma una conversación en la fase donde quedó, con su historial. Solo
  una pantalla puede tenerla abierta a la vez.
- **Tareas al día con su spec**: si editas una historia, su tarea queda marcada como desalineada
  y `umbra spec tasks` te muestra qué cambiaría antes de actualizarla. No toca tareas en marcha
  ni terminadas.
- **Avance por spec**: `umbra spec list`, `umbra status` y `watch` muestran historias hechas del
  total, desalineadas y costo. `explain` dice de qué historia viene cada tarea. En `watch`, la
  tecla `s` empieza una idea nueva o retoma la conversación abierta.
- **En `umbra chat`**: consultar el avance va sin preguntar, crear tareas pide confirmación, y
  `spec new` / `spec resume` te los pide ejecutar en tu terminal.

## v0.8.0 — 2026-10-30

Primera versión publicada: desde aquí umbra se instala desde una versión y no desde la carpeta
donde se desarrolla.

- **Instalación estable y versiones**: `umbra self-update` instala la última versión publicada y
  `umbra --version` / la cabecera de `watch` dicen cuál corre (o «desarrollo» si es la copia de
  trabajo).
- **Avisos**: aviso del sistema y campana en `watch` cuando una tarea espera tu aprobación, se
  detiene o falla.
- **Piloto automático**: al integrar una tarea, arranca sola la siguiente aceptada que ya puede ir.
- **Decidir sobre hallazgos**: «no aplica» o «se hará después» (crea una tarea), con la tecla `h`
  en `watch` o `umbra finding`. El revisor solo marca como grave lo que el cambio rompe.
- **Costo honesto**: lo que Codex no pone precio se ve como «tokens sin precio», no como $0.00.

## v0.7.0

- «De qué trata» de cada tarea en lenguaje llano, separado de las indicaciones técnicas para el
  agente (`t` en `watch` las muestra).

## v0.6.0

- Evidencia explicada: qué se hizo, cómo se comprobó, qué cambió, costo y tiempo; un agente de
  resumen la escribe al terminar y encabeza el PR. En `watch`, el scroll ya no salta y el tema
  elegido se recuerda.

## v0.5.0

- `umbra spec tasks`: de una spec de Spec Kit a una tarea por historia, sin IA (fase 1 del
  levantamiento de requisitos).

## v0.4.2

- Los agentes recuerdan las rondas de revisión anteriores de la misma tarea; reintentar tras un
  bloqueo por hallazgos vuelve a construir con el hallazgo correcto.

## v0.4.1

- Tareas más rápidas: tests en paralelo, sin repetir la suite completa, revisión de Codex sin
  razonamiento máximo.

## v0.4.0

- `umbra explain` muestra de qué trata la tarea, cómo la planteó el agente y qué hizo.

## v0.3.2

- Si la rama base avanza mientras una tarea espera, umbra trae los cambios y resuelve conflictos.

## v0.3.1

- En Windows los agentes ya no abren ventanas de consola.

## v0.3.0

- Acciones desde `umbra watch`: aceptar, ejecutar, reintentar, pausar, aprobar, rechazar…

## v0.2.0

- Los estados de las tareas se explican en lenguaje llano; añadir tests a un archivo existente ya
  no se bloquea.

## v0.1.1

- `umbra watch` ya no se congela al refrescar.

## v0.1.0

- Base completa (E0–E5): tareas desde una spec, rutina PLAN → BUILD → REVIEW → VERIFY → SCAN →
  SHIP con Claude Code y Codex, aprobación humana, seguridad y vista en vivo.
