# Implementation Plan: VERIFY con navegador

**Branch**: `020-verify-navegador` | **Spec**: [spec.md](spec.md)

## Summary

`commands.start_background` levanta el comando `dev` (grupo de procesos propio, espera a que
`url` responda; `NotReady` si no) y `stop_background` mata el árbol. `Engine.check_stage`
(verify, perfil con acción `browse`) lo levanta antes del intento y lo apaga después (eventos
`dev.started`/`dev.stopped`; `BLOCKED dev_not_ready`). `Envelope.app_url` y
`screenshots_dir` (`.umbra/artifacts/<intento>-shots`, fuera del workspace); el adaptador de
Claude Code añade `--mcp-config` con `@playwright/mcp` (`--headless`, `--output-dir`) y
`mcp__playwright` a `--allowedTools` solo cuando hay `app_url`. Tras el intento, cada archivo
de la carpeta se registra como artefacto `screenshot` ligado al `head_sha`
(`evidence.screenshots`). El perfil `verifier` gana `browse` y las instrucciones del
navegador; sin `dev` no cambia nada. Informe: «Visto en el navegador: N capturas»; `umbra init`
registra `dev` en Laravel.

## Constitution Check

VI (las capturas son evidencia ligada al SHA) · IX (Verificar sigue sin escribir en el
workspace) · V (mismos límites del perfil) · X (sin dependencias nuevas: el MCP lo trae `npx`
y solo se usa con `dev`).

## Pruebas

`tests/acceptance/test_verify_browser.py`: `python -m http.server` como `dev`, modo `browse` del
`claude` falso (visita la url y deja `home.png`), caso sin `dev` y app que no responde.
