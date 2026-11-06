# Feature Specification: Réplica autónoma y genérica

**Feature Branch**: `034-replica-autonoma`

**Created**: 2026-11-05

**Status**: Implemented

**Input**: User description: "El comando está funcionando como la mierda, siempre se revienta o
no cae en cuenta qué tiene que hacer. Si la prueba ejecuta una integración, o el servicio externo
tiene que funcionar para que funcione en local, él mismo debería ejecutarse. Debe ser genérica y
agnóstica."

## Contexto

En `landing-manager`, `/replicar` falló una y otra vez: por el comando `dev`, por los archivos
de Playwright y, al final, capturó solo el login. Hubo dos motivos:

- el catálogo depende de un ERP externo que en local devuelve 503;
- el panel pide sesión.

El replicador solo podía navegar y escribir en `design/`. No tenía cómo preparar la app.

## User Stories

### User Story 1 - El replicador prepara la app por su cuenta (Priority: P1)

Sin nada específico del proyecto, el replicador lee el código y resuelve lo que impide ver cada
vista:

- **Sesión:** crea usuarios de prueba temporales con los medios del propio proyecto (seed, CLI,
  endpoint o la base de datos local de desarrollo), los usa y los borra al terminar.
- **Servicios externos y datos:** simula en el navegador (`browser_route`) las peticiones que
  fallan, con datos de ejemplo con la forma que espera el front.
- **Piezas locales:** levanta las que falten.

Puede ejecutar comandos, pero no `git` que cambie algo. Solo escribe en `design/`.

**Acceptance Scenarios**:

1. **Given** una vista con login y sin credenciales configuradas, **Then** el replicador crea
   usuarios temporales en la base local, captura y los borra (o simula la sesión si la base no es
   local).
2. **Given** una petición a un servicio externo que falla en local, **Then** la simula con datos
   de ejemplo y el índice marca esas vistas.

### User Story 2 - Todo o nada (Priority: P1)

Si falta alguna vista del inventario, si el replicador cambió código o si falló, la réplica se
descarta entera y umbra dice por qué. Lo que deje suelto fuera de `design/` (registros,
temporales) se borra sin hacer fallar la réplica.

### User Story 3 - En un espacio de trabajo (Priority: P1)

Trabaja desde la carpeta padre, con todos los repos a la vista. Levanta el `dev` de cada repo en
orden y escribe solo en `design/` del repo de la app. Si hay una herramienta de diseño conectada,
deja allí un tablero por vista.

## Requirements

- **FR-001**: La acción `shell` da comandos libres, y vetados los de `git` que cambian algo.
- **FR-002**: El navegador de los agentes se abre con `--caps=network,storage`.
- **FR-003**: `replicate` aplica todo o nada, restaura lo versionado que cambió fuera de
  `design/` y borra lo suelto.
- **FR-004**: En un espacio, el replicador trabaja desde la carpeta padre con
  `allowed_paths = ["<app>/design/**"]`.
