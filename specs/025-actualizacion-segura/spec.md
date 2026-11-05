# Feature Specification: Actualización segura

**Feature Branch**: `025-actualizacion-segura`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Que al publicar una versión umbra se actualice solo y vuelva a
montar el bridge con Telegram."

## Contexto

`umbra self-update` instala la versión nueva cuando umbra se cierra (Windows no deja reemplazar
un programa en uso). El 2026-11-05 falló: `umbra bridge --stop` respondió «puente detenido»,
pero el proceso siguió vivo unos segundos esperando mensajes de Telegram. La instalación chocó
con él, quedó a medias y `umbra` dejó de arrancar hasta reinstalar a mano. Además, actualizar
apaga el teléfono: hay que volver a levantar el bridge a mano y nadie avisa por Telegram de que
umbra volvió (o no).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Actualizar sin romper nada (Priority: P1)

`umbra self-update` detiene el bridge, espera a que ningún proceso de umbra use la instalación
(el bridge, `watch`, tareas en marcha), instala, comprueba que la versión nueva arranca y vuelve
a levantar el bridge si estaba en marcha. Si la versión nueva no arranca, vuelve a la anterior.
El resultado llega como aviso de Windows y por Telegram.

**Acceptance Scenarios**:

1. **Given** el bridge en marcha, **When** la persona ejecuta `umbra self-update -y`, **Then**
   umbra espera a que el proceso del bridge termine antes de instalar y lo vuelve a levantar
   después, en la misma carpeta.
2. **Given** una instalación que falla o una versión que no arranca, **Then** umbra reinstala la
   versión anterior y avisa «no se pudo actualizar; sigues en vX».
3. **Given** un `watch` abierto o tareas trabajando que no terminan en 10 minutos, **Then** umbra
   no instala, deja el bridge como estaba y explica qué lo impidió.

---

### User Story 2 - Actualizar desde el teléfono (Priority: P2)

`/actualizar` en Telegram dice qué trae la versión nueva y la instala igual que
`umbra self-update`; el bridge vuelve solo y escribe «Ya estoy en vX».

**Acceptance Scenarios**:

1. **Given** una versión nueva publicada, **When** la persona escribe `/actualizar`, **Then** el
   bridge responde «Actualizando a vX…», se detiene y la instalación queda en marcha.
2. **Given** que ya está en la última, **Then** responde «Ya estás en vX» y no hace nada.

### Edge Cases

- El token de Telegram nunca se escribe en el script de actualización: se lee del entorno.
- Copia de desarrollo (instalación editable): no hay versión anterior a la que volver; se dice.
- Fuera de Windows no hay bloqueo de archivos: se instala en el momento y se reinicia el bridge.

## Requirements *(mandatory)*

- **FR-001**: Antes de instalar, umbra MUST detener el bridge y esperar a que su proceso
  termine (forzándolo tras 60 s).
- **FR-002**: umbra MUST esperar hasta 10 minutos a que ningún proceso use la instalación; si
  sigue en uso, MUST abortar sin tocarla y explicarlo.
- **FR-003**: Tras instalar, umbra MUST comprobar que `umbra --version` informa la versión nueva;
  si no, MUST reinstalar la anterior.
- **FR-004**: Si el bridge estaba en marcha, MUST volver a levantarse en su carpeta, tanto si
  la actualización salió bien como si no.
- **FR-005**: El resultado MUST avisarse por Windows y, si Telegram está configurado, por
  Telegram, sin escribir el token en disco.
- **FR-006**: `/actualizar` en Telegram MUST hacer lo mismo que `umbra self-update -y`.
- **FR-007**: El CHANGELOG y `docs/usage.md` MUST registrar los cambios visibles.

## Success Criteria *(mandatory)*

- **SC-001**: El script de actualización espera al proceso del bridge, espera a que la
  instalación quede libre, vuelve a la versión anterior si la nueva no arranca y relanza el
  bridge en su carpeta (pruebas sobre el script generado).
- **SC-002**: Con Telegram falso, `/actualizar` con una versión nueva detiene el bridge y lanza
  la instalación con el bridge a relanzar; sin versión nueva, no lanza nada.
- **SC-003**: Todas las pruebas anteriores pasan.
