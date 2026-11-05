# umbra-engine Constitution

## Core Principles

### I. Terminal primero

Toda capacidad de umbra-engine MUST poder ejecutarse desde la CLI `umbra`. Ninguna funcionalidad
MUST requerir un navegador, un servidor web o un servicio en red propio. Todo comando que produzca
datos MUST aceptar `--json` para que scripts y la capa conversacional lean su salida sin
interpretar texto.

### II. Comandos antes que conversación

La conversación (`umbra chat`) es una capa opcional sobre los mismos comandos. Toda acción que el
chat pueda realizar MUST existir como comando de la CLI. El chat MUST NOT tener más permisos que la
CLI. umbra MUST funcionar completo sin modelo conversacional; solo los agentes que ejecutan tareas
consumen IA, con una excepción: la conversación de requisitos (`umbra spec new`), que es opcional
y cuyo resultado MUST poder obtenerse también con Spec Kit y `umbra spec tasks`.

### III. El agente propone, el motor decide

Ninguna salida de un modelo equivale a una autorización. Transiciones de estado, permisos,
aprobaciones e integración MUST decidirse en código determinista. Una salida de agente que no
valide contra su contrato MUST bloquear la etapa (se permite una reparación de formato acotada).

### IV. Agentes intercambiables

El núcleo MUST NOT conocer agentes concretos por su nombre. Todo agente se integra mediante un
adaptador que implementa `check()`, `run(envelope)` y `resume(session_id)`, más un perfil
declarativo. El sobre de entrada/salida (`schema_version`, `run_id`, `stage`, `attempt_id`,
`input_sha`, `output_sha`, `status`, `findings`, `artifact_ids`) es una interfaz estable y
versionada. Un agente MUST pasar `umbra agent test` antes de poder usarse en una rutina.

### V. Toda sesión está acotada

Ningún agente MUST ejecutarse sin límite de tiempo, límite de costo, workspace definido y conjunto
de acciones permitidas. Los permisos efectivos MUST ser la intersección entre el perfil y la
política del proyecto; un perfil MUST NOT ampliar lo que la política permite. Agotar un límite
cierra el bloque y deja evidencia de lo ocurrido.

### VI. Evidencia o no pasó

Una etapa avanza solo por resultados verificables: exit code, reporte de tests, diff ligado a un
SHA. Cada evidencia MUST registrar el SHA probado, el comando, el perfil, el exit code y la salida
original. Un texto del agente que afirme éxito MUST NOT contar como evidencia. Un reporte vacío,
omitido o con cero pruebas inesperadas MUST NOT contar como éxito.

### VII. Humano antes de integrar (NON-NEGOTIABLE)

Ningún cambio MUST llegar a la rama principal sin aprobación humana explícita mediante
`umbra approve` en una terminal interactiva. La aprobación MUST quedar ligada al `head_sha`; un
commit posterior la invalida. El chat y los agentes MUST NOT aprobar, hacer push a la rama
principal ni fusionar. Una ejecución solo llega a `SUCCEEDED` cuando el merge del SHA aprobado está
confirmado por el proveedor.

Dentro de una rama de spec (`spec/<carpeta>`), umbra MAY integrar sin aprobación las tareas que
pasaron tests, revisión, verificación y política: la aprobación humana se da sobre la spec
completa, con un único PR de la rama de spec a la rama principal y toda la evidencia agregada.
La rama de spec nunca es la rama principal.

La aprobación humana explícita puede darse desde una terminal interactiva o desde un canal
autenticado que la persona configuró para sí (Telegram, verificando el `chat_id`); queda
registrada con su origen y quién la dio.

### VIII. Reanudable e idempotente

Si un proceso de umbra muere, el trabajo MUST retomarse desde el último checkpoint sin perder
estado. Cada efecto externo (rama, commit, push, PR, merge) MUST tener una `operation_key` estable
y MUST consultarse antes de repetirse. Repetir un comando MUST NOT duplicar ejecuciones, ramas,
PRs ni cargos. Un worker que perdió el lease MUST NOT publicar cambios.

### IX. Aislamiento del trabajo

Cada tarea MUST trabajar en su propio git worktree. Un diff que borre o debilite tests
existentes, rebaje umbrales o modifique `.umbra/` o los workflows de CI MUST bloquear la etapa; un
cambio legítimo en esas rutas requiere un flujo de aprobación separado. umbra MUST NOT almacenar
credenciales: usa los logins existentes de `git`, `gh`, `claude` y `codex`.

### X. Simple hasta que duela

Sin servidor, sin colas externas, sin base de datos de red y sin framework multiagente. Se usa la
librería estándar antes que una dependencia y una dependencia ya instalada antes que una nueva.
Toda complejidad adicional MUST justificarse con un caso real o una métrica, documentado en el
plan de la feature correspondiente.

## Restricciones técnicas y de seguridad

- Lenguaje: Python >= 3.12. Distribución con `uv tool install`.
- Dependencias de ejecución permitidas: typer, rich, pydantic (v2), pyyaml; textual solo para la
  vista en vivo y la pantalla de conversación de requisitos. Cualquier otra MUST justificarse en
  el plan de la feature.
- Estado: SQLite (modo WAL) en `.umbra/umbra.db` por proyecto; configuración en TOML y rutinas en
  YAML. Costos MUST almacenarse como decimales, nunca como float.
- Adaptadores iniciales: Claude Code (`claude -p`) y Codex (`codex exec`). La capa conversacional
  usa el `claude` interactivo del usuario con su propio login; la conversación de requisitos usa
  `claude -p` en stream-json con ese mismo login, y umbra controla sus fases y lo que puede
  escribir (solo `specs/` y `.specify/feature.json`). umbra MUST NOT ofrecer ni gestionar login de
  claude.ai.
- Los comandos de prueba, lint y build MUST provenir de `.umbra/project.toml`, nunca del texto de
  un agente. No se concatenan entradas de modelo a un shell.
- Multiplataforma: Windows y POSIX. Gestión de procesos, rutas y locks MUST funcionar en ambos.
- Fuera de alcance: despliegue a producción y escritura sobre bases de datos productivas.
- Ejecución paralela: hasta `[blocks] parallel` tareas a la vez por repositorio, cada una con su
  worktree, su lease y su conexión; las dependencias entre tareas se respetan siempre.

## Flujo de desarrollo y controles de calidad

- Cada entrega del roadmap (E0–E5) se desarrolla como una feature de Spec Kit:
  specify → plan → tasks → implement.
- Cada entrega vive en su propia rama y se integra por PR a `main`, revisado y fusionado por el
  responsable del proyecto. `main` está protegida contra push directo y force push.
- Antes de abrir un PR: `uv run pytest` y `uv run ruff check .` MUST pasar.
- La lógica no trivial (máquina de estados, idempotencia, políticas, parsers de adaptadores) MUST
  tener pruebas automáticas. Las pruebas automáticas MUST NOT depender de red ni consumir modelos:
  usan agentes falsos, un remoto git local y un `gh` falso.
- Los criterios de salida de cada entrega incluyen un smoke test manual con agentes reales sobre
  `sandbox/`.

## Governance

Esta constitution prevalece sobre cualquier otra práctica del proyecto. Cada plan de feature MUST
incluir una verificación explícita de cumplimiento contra los principios I–X; cualquier excepción
se documenta en la sección de complejidad del plan con su justificación.

Las enmiendas se proponen por PR que modifique este archivo, con la justificación y el impacto en
specs existentes. Las aprueba el responsable del proyecto (Alejandro). Versionado semántico:
MAJOR para eliminar o redefinir principios, MINOR para añadir principios o secciones, PATCH para
aclaraciones. La guía de diseño de referencia es `docs/design.md`.

**Version**: 1.2.1 | **Ratified**: 2026-10-29 | **Last Amended**: 2026-11-04
