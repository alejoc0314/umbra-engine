# Feature Specification: Sistemas de diseño por proyecto y réplica del diseño actual

**Feature Branch**: `031-sistemas-y-replica`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Que la librería se tome de forma dinámica: cuando cree la spec le
defino a umbra que ese proyecto trabaja con ese sistema de diseño. Y en el onboarding, que genere
una réplica del diseño actual de la aplicación a partir del código y el front, dentro de la
herramienta de diseño, para poder decir «en la vista X realiza este cambio»."

## Contexto

Hoy un proyecto usa una librería de diseño solo si alguien escribe a mano su ruta en la
configuración. Debe ser una elección del proyecto, hecha al crear la spec o en el onboarding, de
entre un catálogo de sistemas de la persona o su equipo. Y en un proyecto ya iniciado, el diseño
real vive en el código: para poder referenciar una vista, umbra necesita verla y tenerla en la
herramienta de diseño.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Elegir el sistema de diseño del proyecto (Priority: P1)

Un catálogo de sistemas vive fuera de los repos (`~/.umbra/design/<sistema>/sistema.toml` o en un
paquete): nombre, descripción, guías y archivo base. El proyecto declara cuál usa
(`[design] system` en `.umbra/project.toml`, versionado). Si no lo ha declarado y hay catálogo,
umbra pregunta al crear una spec (terminal y Telegram) y en el onboarding; `umbra design sistema`
y `/sistema` lo muestran o lo cambian. El diseñador recibe las guías y el archivo base del
sistema elegido.

**Acceptance Scenarios**:

1. **Given** un catálogo con «kit-equipo» y un proyecto sin sistema, **When** la persona abre una
   spec, **Then** umbra pregunta qué sistema usa y lo guarda en `project.toml`.
2. **Given** `system = "kit-equipo"`, **Then** el diseñador recibe sus guías y parte de su archivo.
3. **Given** `system = "ninguno"`, **Then** umbra no vuelve a preguntar y el diseñador define o
   extrae el sistema.

---

### User Story 2 - Réplica del diseño actual (Priority: P1)

`umbra design replicar` (o `/replicar`, ofrecido al aprobar el onboarding) levanta la app con
`dev`, recorre las vistas del inventario (`specs/000-linea-base/vistas.md`) con el navegador y
guarda una captura por vista en `design/actual/` con un índice (vista, ruta, archivo). Si hay una
herramienta de diseño conectada, crea en ella un tablero `Actual · <Vista>` por vista. Además
extrae del código el sistema visual (colores, tipografías, radios, espaciados) a
`design/sistema.md` y, con herramienta, a variables y componentes base. La persona aprueba (commit)
o descarta.

**Acceptance Scenarios**:

1. **Given** `dev` registrado e inventario de vistas, **When** la persona replica, **Then**
   `design/actual/` tiene capturas e índice y, al aprobar, quedan en un commit.
2. **Given** que el agente toca algo fuera de `design/`, **Then** se restaura y falla.
3. **Given** una tarea que toca la vista X, **Then** el diseñador recibe el índice y, si existe
   `Actual · X`, la reconstruye editable antes de aplicar el cambio.

### Edge Cases

- App con login: `[design.replica] usuario` y `clave_env` (variable de entorno); solo usuarios
  de prueba locales, porque la clave viaja en el sobre del agente.
- Sin `dev` registrado: la réplica lo dice y no corre.
- Apps nativas sin navegador: fuera de alcance.

## Requirements *(mandatory)*

- **FR-001**: Catálogo de sistemas en `~/.umbra/design/*/sistema.toml` y en paquetes.
- **FR-002**: `[design] system` en el proyecto; sus guías y archivo base llegan al diseñador.
- **FR-003**: umbra MUST preguntar el sistema al abrir una spec y en el onboarding si hay
  catálogo y el proyecto no lo ha declarado.
- **FR-004**: `umbra design sistema [nombre]`, `umbra design sistemas` y `/sistema`.
- **FR-005**: `umbra design replicar` y `/replicar`: capturas, índice, sistema extraído y
  tableros en la herramienta conectada; solo `design/`; aprobación explícita.
- **FR-006**: El diseñador recibe el inventario de vistas y el índice de la réplica.
- **FR-007**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: Con agentes falsos, abrir una spec sin sistema pregunta, guarda y el diseñador
  recibe las guías del sistema elegido.
- **SC-002**: La réplica con un `dev` falso deja capturas e índice y los confirma al aprobar.
- **SC-003**: Todas las pruebas anteriores pasan.
