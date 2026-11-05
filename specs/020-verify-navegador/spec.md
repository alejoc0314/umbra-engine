# Feature Specification: VERIFY con navegador

**Feature Branch**: `020-verify-navegador`

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Para apps web, la verificación levanta la app, recorre los
criterios con un agente de navegador y deja capturas como evidencia."

## Contexto

Hoy Verificar lee código y tests. Para una app web eso no equivale a verla funcionar: un botón
que no aparece o una pantalla rota pasan los tests y llegan a la aprobación. Si umbra levanta la
app sobre el código de la tarea y el verificador la recorre en un navegador dejando capturas, lo
que se aprueba ya se vio funcionando.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Verificar viendo la app (Priority: P1)

Con un comando `dev` registrado (`background = true` y `url`), antes de Verificar umbra lo
levanta sobre el workspace de la tarea, espera a que la `url` responda y se la pasa al
verificador, que la recorre con un navegador y deja una captura por criterio visto. Al terminar,
umbra apaga la app.

**Acceptance Scenarios**:

1. **Given** `dev` registrado, **When** la tarea llega a Verificar, **Then** la app se levanta,
   el verificador recibe la `url` y las herramientas del navegador, y las capturas quedan como
   evidencia ligadas al SHA verificado.
2. **Given** que la app no llega a responder, **Then** la tarea se detiene con un motivo claro.
3. **Given** un proyecto sin `dev`, **Then** Verificar funciona como hoy.

---

### User Story 2 - Las capturas son evidencia (Priority: P2)

El informe de aprobación dice cuántas capturas se vieron; la evidencia técnica lista cada una.

## Edge Cases

- Las capturas se guardan fuera del workspace: no ensucian el diff ni frenan la etapa.
- El comando `dev` no entra en los comandos que el agente puede ejecutar: lo levanta umbra.
- Verificar nunca escribe en el workspace (la regla de solo lectura se mantiene).

## Requirements *(mandatory)*

- **FR-001**: `[commands] dev = { run, background = true, url }` MUST levantarse antes de
  Verificar y detenerse después, con eventos en el registro.
- **FR-002**: El verificador MUST recibir `app_url` y `screenshots_dir` en el sobre y las
  herramientas del navegador (MCP de Playwright) solo cuando hay app.
- **FR-003**: Cada archivo de `screenshots_dir` MUST registrarse como evidencia (`screenshot`)
  con el SHA verificado.
- **FR-004**: Si la app no responde a tiempo, la tarea MUST detenerse con `dev_not_ready`.
- **FR-005**: `umbra init` MUST registrar `dev` en proyectos Laravel; el informe MUST contar
  las capturas.

## Success Criteria *(mandatory)*

- **SC-001**: Con un `dev` falso (servidor HTTP) y un verificador falso que visita la url y
  deja una captura, la tarea llega a «Espera tu aprobación» con la captura como evidencia y el
  servidor apagado.
- **SC-002**: Todas las pruebas anteriores pasan.
