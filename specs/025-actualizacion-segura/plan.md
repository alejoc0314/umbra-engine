# Implementation Plan: Actualización segura

**Branch**: `025-actualizacion-segura` | **Spec**: [spec.md](spec.md)

## Summary

- `bridge._beat()` guarda también la carpeta (`root`) en `~/.umbra/bridge.json`.
  `bridge.handoff()` lee `pid` y `root` del latido vivo, detiene el bridge (`stop()`) y los
  devuelve para relanzarlo después.
- `version.install(v, previous, bridge, tg)`: en Windows genera el script de traspaso con:
  esperar al `pid` del bridge (60 s, luego `Stop-Process`), esperar a que ningún proceso cuyo
  ejecutable esté en la carpeta de la herramienta (`uv tool dir`/umbra-engine) o sea el lanzador
  `umbra.exe` siga vivo (10 min), `uv tool install`, `umbra --version` debe decir `v<nuevo>`, si
  no reinstalar `v<anterior>`, relanzar `umbra bridge` en `root` y avisar (toast + Telegram con
  `Invoke-RestMethod`, token leído de `$env:<token_env>`). Fuera de Windows: instalar en el
  momento y relanzar el bridge.
- `umbra self-update` y `/actualizar` (bridge) usan `bridge.handoff()` y
  `telegram.target(config)` (`token_env` + `chat_id`, nunca el token).

## Constitution Check

II (una sola instalación estable, sin estado a medias: se vuelve a la anterior) · III (la
persona decide cuándo: `self-update` o `/actualizar`). Sin enmienda.

## Pruebas

`tests/unit/test_version.py` sobre el script generado; `tests/acceptance/test_self_update.py`
con Telegram falso para `/actualizar`.
