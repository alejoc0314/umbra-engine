# Feature Specification: Paquetes, MCP en el perfil y la etapa Diseñar

**Feature Branch**: `026-paquetes-y-diseno`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Un perfil previo a la construcción que trabaje como el diseñador
de los proyectos; el constructor se basa en lo diseñado para maquetar (siempre que la tarea
requiera diseño o frontend, mobile, etc.). umbra será open source: el perfil del diseñador con
la herramienta de diseño de mi equipo debe ser algo local, no del repo; los perfiles estándar
son los que se inicializan."

## Contexto

Hoy el constructor maqueta a partir del texto de la tarea, y el resultado visual depende de su
criterio. La persona quiere ver y aprobar el diseño antes de que se escriba código, y que lo
construido se parezca a lo aprobado. La herramienta de diseño y los perfiles de su equipo son
privados: umbra, que es open source, solo debe ofrecer el mecanismo genérico. Lo privado llega
por un canal local.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver y aprobar el diseño antes de construir (Priority: P1)

Cuando el planificador marca que la tarea toca la interfaz y hay un diseñador instalado, umbra
lo pone a diseñar en `design/`, recoge las pantallas exportadas y espera el visto bueno de la
persona, que las recibe como fotos en Telegram. Aprobar sigue a Construir; pedir cambios vuelve
al diseñador con el texto. Construir maqueta sobre lo aprobado y Verificar compara con ello.

**Acceptance Scenarios**:

1. **Given** una tarea de interfaz y un perfil `designer`, **When** corre `feature`, **Then**
   la tarea se detiene con «el diseño espera tu visto bueno» y las pantallas llegan a Telegram.
2. **Given** un diseño esperando, **When** la persona responde «más contraste», **Then** el
   diseñador recibe ese texto y vuelve a pedir el visto bueno.
3. **Given** un diseño aprobado, **Then** el sobre de Construir y el de Verificar llevan las
   pantallas aprobadas y el informe dice «Maquetado sobre el diseño que aprobaste».
4. **Given** una tarea sin interfaz, o sin diseñador instalado, **Then** Diseñar se salta y la
   tarea sigue como antes.

---

### User Story 2 - Lo privado, en un paquete local (Priority: P1)

`umbra pack sync <repo>` clona o pone al día un paquete en `~/.umbra/packs/<nombre>/` con
perfiles, rutinas y playbooks. umbra los encuentra después del proyecto y de `~/.umbra`, y antes
de lo que trae por defecto. `umbra pack list` muestra qué aporta cada uno.

**Acceptance Scenarios**:

1. **Given** un paquete con `profiles/designer.toml`, **Then** la etapa Diseñar lo usa.
2. **Given** el mismo perfil en el proyecto, **Then** gana el del proyecto.

---

### User Story 3 - Un perfil declara sus servidores MCP (Priority: P1)

Un perfil de Claude Code puede declarar `[mcp.<nombre>]` (`command`, `args`, `env`) con
`{profile_dir}` y `{workspace}`. umbra se los pasa a ese agente, y solo esos.

**Acceptance Scenarios**:

1. **Given** un perfil con `[mcp.lienzo]`, **Then** el agente arranca con ese servidor,
   `--strict-mcp-config` y permiso para sus herramientas (`mcp__lienzo`).

### Edge Cases

- El diseñador toca algo fuera de `design/`: la tarea se detiene («el diseñador tocó código»).
- El diseñador no exporta pantallas: la tarea se detiene («el diseñador no dejó pantallas»).
- `human_approval: false` en la etapa: el diseño se aprueba solo.
- Ningún nombre de producto de diseño en el repo: el test de lo privado lo vigila.

## Requirements *(mandatory)*

- **FR-001**: La rutina `feature` MUST incluir `design` tras `plan`, que corre solo si el plan
  devolvió `needs_design` y existe el perfil del diseñador.
- **FR-002**: El diseñador MUST poder cambiar solo `design/`; sus cambios se confirman en la
  rama de la tarea y sus pantallas se registran como evidencia.
- **FR-003**: Con aprobación humana, la tarea MUST detenerse con el código `design_review`, las
  fotos en Telegram y las decisiones `umbra design ok|cambios`, `watch` (`a`/`r`), botón y
  respuesta en Telegram.
- **FR-004**: Construir y Verificar MUST recibir las pantallas aprobadas.
- **FR-005**: `umbra pack sync|list` y los paquetes en la resolución de perfiles, rutinas y
  playbooks.
- **FR-006**: Los perfiles MUST poder declarar servidores MCP que el adaptador de Claude Code
  pasa en exclusiva.
- **FR-007**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Con agentes falsos: plan de interfaz → diseño → cambios pedidos por Telegram →
  segundo diseño → aprobado → Construir con las pantallas → «Espera tu aprobación».
- **SC-002**: Sin diseñador o sin interfaz, `feature` hace las mismas etapas que antes.
- **SC-003**: Todas las pruebas anteriores pasan.
