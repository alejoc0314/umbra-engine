# Implementation Plan: Decidir desde el teléfono (Telegram)

**Branch**: `019-telegram` | **Spec**: [spec.md](spec.md)

## Summary

`blocks/telegram.py` (solo `urllib`): `settings(config)` lee `[notify.telegram] token_env` y
`chat_id`; `send` con `inline_keyboard`; `updates` (long polling `getUpdates`); `ack` y
`clear_buttons`; `decision_message(run, type, payload)` y `spec_message` deciden texto y
botones (`callback_data` = `acción:tarea`). `Engine.event` envía a Telegram en cada `ALERTS`
(además del aviso de escritorio) y `spec_ready` el de la spec. `routines/bridge.py`:
`act` ejecuta cada botón con `service.*` y origen `telegram` (evento `telegram.decided` con el
usuario), `handle` filtra por `chat_id` y entiende «N texto» o respuestas al mensaje de la
tarea, `serve` hace el bucle con lease `bridge`, `spawn`/`stop`. `service.dispatch` arranca el
puente si hay Telegram y no hay uno vivo. CLI `umbra bridge [--stop]`. La base de la API se
sobreescribe con `UMBRA_TELEGRAM_API` para el servidor falso de las pruebas.

## Constitution Check

I (sin servidor propio: long polling) · II (cada botón es un comando existente) · VII
enmienda 1.2.1 (aprobación desde un canal autenticado con `chat_id` verificado) · IX (sin
credenciales guardadas: el token vive en el entorno) · X (librería estándar).

## Pruebas

`tests/acceptance/test_telegram.py` con un `HTTPServer` local que hace de
`api.telegram.org`: avisos con botones, autorizar, integrar, ver cambios, responder por texto,
otro chat ignorado, spec completa con un toque, `bridge --stop`.
