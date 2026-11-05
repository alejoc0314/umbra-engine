# Feature Specification: Tus proyectos y tu MySQL desde Telegram

**Feature Branch**: `024-proyectos-y-mysql`

**Created**: 2026-11-04

**Status**: Implemented

**Input**: User description: "Al escribirle desde Telegram me dice que no puede llevar a cabo
procesos en ninguna otra carpeta que no sea la actual. Necesito que umbra tenga acceso a
trabajar con BDs locales, crear carpetas en C:/apps para nuevos proyectos y que le permita
brincar de carpeta en carpeta dentro de C:/apps." Decisiones de la persona: consultar la BD sin
pedir permiso; todo cambio a la BD exige su permiso; todas sus BDs son MySQL; todo pasa por
umbra (sin terminal libre); las carpetas se adoptan una a una.

## Contexto

El puente ya atendía varios repos (`/proyectos`, `/usar`, `/nuevo_proyecto`), pero solo los del
índice de umbra, y la conversación libre corre en la carpeta del proyecto actual sin saber que
existen los demás: por eso respondía que no podía. Las carpetas de C:/apps sin umbra no
existían para Telegram, y no había forma de tocar una base de datos.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver y adoptar las carpetas del espacio de trabajo (Priority: P1)

`/proyectos` lista los repos con umbra de la carpeta que los contiene (C:/apps), aunque no
estén en el índice, y las carpetas sin umbra. `/adoptar carpeta` pone umbra en una de ellas: si
no era repo git lo crea con un primer commit (con un `.gitignore` básico si no tenía, para no
versionar `.env` ni dependencias) y pasa a ser el proyecto actual.

**Acceptance Scenarios**:

1. **Given** un repo con umbra fuera del índice, **When** `/proyectos`, **Then** aparece y entra
   al índice.
2. **Given** una carpeta sin git con un `.env`, **When** `/adoptar`, **Then** queda con umbra,
   un primer commit sin el `.env`, y es el proyecto actual.

### User Story 2 - La conversación se mueve entre proyectos (Priority: P1)

La conversación sabe qué proyectos y carpetas hay. Si el mensaje pide trabajar en otro
proyecto, adoptar una carpeta o crear un proyecto, termina su respuesta con una línea
`UMBRA> usar|adoptar|nuevo_proyecto …` y el puente lo hace; con `usar` le repite el mensaje en
el proyecto nuevo (una sola vez).

### User Story 3 - MySQL local: consultar libre, cambiar con permiso (Priority: P1)

`umbra db query "SQL"` consulta sin pedir permiso (solo lectura). `umbra db change "SQL"` solo
propone: el cambio queda pendiente y en Telegram llega con «Aplicar cambio» / «Descartar». En
la terminal, `umbra db list`, `umbra db apply ID` y `umbra db discard ID` (estos dos exigen una
terminal interactiva). La conversación puede consultar y proponer, nunca aplicar.

### Edge Cases

- Una «consulta» que escribe (UPDATE, DROP, `WITH … UPDATE`, `INTO OUTFILE`, `SELECT 1; DROP …`)
  se rechaza: lista de sentencias de lectura, transacción `READ ONLY` y una sola sentencia.
- Un cambio con varias sentencias que falla a medias se revierte (salvo DDL, que MySQL confirma
  solo); el cambio sigue pendiente y el error llega a la persona.
- Pulsar «Aplicar» dos veces no aplica dos veces.
- `/adoptar` no sale del espacio de trabajo ni adopta una carpeta que ya tiene umbra.

## Requirements *(mandatory)*

- **FR-001**: El puente MUST servir todos los repos con umbra de su espacio de trabajo.
- **FR-002**: `/adoptar` MUST poner umbra en una carpeta existente sin versionar secretos.
- **FR-003**: La conversación MUST conocer los proyectos y poder pedir moverse, adoptar o crear.
- **FR-004**: Ningún cambio a la BD MUST ejecutarse sin una decisión explícita de la persona.
- **FR-005**: La conexión MUST leerse de `[mysql]` en `local.toml`, con la contraseña en una
  variable de entorno (`password_env`).
- **FR-006**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios.

## Success Criteria *(mandatory)*

- **SC-001**: Con los falsos, `/adoptar`, el cambio de proyecto conversando y el cambio de BD con
  botón pasan; contra un MySQL 8 real, consultas, escrituras frenadas y cambios aplicados.
- **SC-002**: Todas las pruebas anteriores pasan.
