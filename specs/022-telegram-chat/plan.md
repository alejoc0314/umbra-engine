# Implementation Plan: Conversar con umbra desde Telegram

**Branch**: `022-telegram-chat` | **Spec**: [spec.md](spec.md)

## Summary

`routines/bridge.py` reescrito como un proceso único: `State` (bot, repos servidos por
nombre, repo actual, offset, sesión de chat por repo); `served()` toma los repos de
`~/.umbra/projects.json` con Telegram configurado; `command()` enruta `/proyectos`, `/usar`,
`/estado`, `/nuevo`, `/hacer` y «N texto» (solo si `asks_questions`), y el resto va a
`converse()` → `chat.launcher.ask` (solo lectura, `resume` por repo). Los botones y textos
llevan `@repo` / «umbra · repo · tarea #N» (`telegram.decision_message/spec_message` con
`project`; el motor pasa `self.root.name`). El puente único usa un latido en
`~/.umbra/bridge.json` (`alive`, `stop`, `_beat`, `_mine`) en vez de un lease por repo;
`service.ensure_bridge` lo consulta. Respuestas largas se parten en trozos de 3900.

## Constitution Check

II (la conversación es `umbra chat`; cada botón un comando) · VII (aprobar sigue siendo botón
explícito; `/hacer` hereda las prohibiciones de `--allow-changes`) · IX (sin credenciales).

## Pruebas

`tests/acceptance/test_telegram_chat.py` (conversación hilada, `/nuevo`, `/hacer`, «N texto»,
dos repos con `/proyectos`/`/usar`/`/estado`, botón con `@repo`, respuestas largas, puente
único); `test_telegram.py` adaptado a los nombres de repo. La fixture del Telegram falso pasa a
`tests/acceptance/conftest.py`.
