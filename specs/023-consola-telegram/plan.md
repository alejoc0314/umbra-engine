# Implementation Plan: Telegram como consola de umbra

**Branch**: `023-consola-telegram` | **Spec**: [spec.md](spec.md)

## Summary

`routines/console.py`: textos de `tareas`, `explicar`, `registro`, `evidencia` (`report_text`
sobre `service.evidence`), `cambios`, `agente`, `hallazgos`; `add_task`, `plan_from_spec`
(`umbra plan` sin pantalla); `delivery(run)` (informe + capturas con `tested_sha` del run);
`SpecTalk`, la máquina de la conversación de spec sin pantalla (misma lógica que
`cli/spec_screen.py`: turnos con `elicit.run_turn`, preguntas con opciones, puntos de control,
cambios, descarte, tareas). `blocks/telegram.py`: `upload` multipart, `send_photos`
(`sendMediaGroup`/`sendPhoto`), `send_document`, `set_commands` (menú del bot), `deliver`.
`Engine.event` llama a `deliver` en `run.waiting_approval` y `run.integrated`. El puente gana
la tabla `COMMANDS`, `with_task` para los comandos «/algo N», trabajos largos en hilos (`_job`)
con el repo fijado en los botones (`_say`), y el enrutado de `sq:`/`sr:` a la spec en curso.
`project.load_project` lee también `~/.umbra/local.toml`.

## Constitution Check

I y II (cada comando del teléfono es una operación de `service`, con origen `telegram`) · VI
(las capturas que se mandan son las ligadas al SHA evaluado) · VII (aprobar sigue siendo
explícito: `/integrar` o el botón) · IX (sin credenciales).

## Pruebas

`tests/acceptance/test_telegram_console.py`: entrega con informe y foto (servidor falso de
Telegram acepta multipart), comandos de ver y de hacer, hallazgos, conversación de spec con el
`claude` falso de varias fases (pregunta, revisión, cambios, descarte, tareas), proyecto nuevo y
plan desde el teléfono, noche, ayuda y menú.
