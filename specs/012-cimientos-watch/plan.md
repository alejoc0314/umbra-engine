# Implementation Plan: Cimientos de la nueva `umbra watch`

**Branch**: `012-cimientos-watch` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

`watch` deja de consultar la base entera en el hilo de la interfaz: una conexión propia (hilo
lector exclusivo), `PRAGMA data_version` para saber si algo cambió, índices en `run(task_id)` y
`usage(attempt_id)`, y una instantánea (`Snapshot`) calculada fuera del hilo de pantalla que la
vista aplica de forma incremental (celdas, filas nuevas, líneas nuevas del registro). Las horas
pasan a hora local con separador de día. Nace el tema «umbra» (oscuro y claro) y un archivo de
estilos `watch.tcss`; los temas integrados siguen y «dracula» se respeta. La pantalla de spec pasa a
ser un `Screen` (`SpecScreen`) dentro de la misma app; `SpecApp` queda como envoltorio para
`umbra spec new/resume`. Los avisos del sistema se callan mientras haya un `watch` abierto (lease
`watch:<pid>@host`) y la campana se configura. Los agentes se lanzan con `--setting-sources project`.

## Technical Context

**Language/Version**: Python >= 3.12 · **Primary Dependencies**: textual 8.2.8 (se declara
`textual>=8.0` en pyproject: se usan `Theme`, `reactive(bindings=True)`, `DataTable.update_cell`
por clave, `Screen.dismiss`), rich 15, typer; sin dependencias nuevas de runtime. Dev: `pytest-textual-snapshot==1.0.0`,
`syrupy>=6` (instantáneas SVG). **Storage**: SQLite (migración V4: índices). **Testing**: pytest +
Pilot; snapshots en `tests/acceptance/__snapshots__/`. **Target**: Windows y POSIX. **Performance**:
tick sin cambios < 5 ms (50 tareas / 2 000 eventos), con cambios < 50 ms; nada de git ni archivos
en el hilo de UI. **Constraints**: teclas y acciones sin cambios; tests actuales verdes.

## Constitution Check

| Principio | Cumple | Cómo |
|---|---|---|
| I. Terminal primero | Sí | Solo cambia `watch`; `--json` intacto (UTC en JSON). |
| II. Comandos antes que conversación | Sí | Ninguna acción nueva; `umbra spec new/resume` siguen. |
| III. El motor decide | Sí | No toca transiciones. |
| IV. Agentes intercambiables | Sí | `--setting-sources` es del adaptador de Claude Code, no del núcleo. |
| V. Sesión acotada | Sí | Sin cambios de límites. |
| VI–VIII | N/A | No cambia evidencia, aprobación ni idempotencia. |
| IX. Aislamiento | Mejora | Los agentes dejan de heredar plugins del usuario. |
| X. Simple hasta que duela | Sí | Un hilo lector, sin colas ni servidor; dev deps solo para snapshots. |
| Restricción «textual solo para watch y spec» | Sí | Se mantiene; la enmienda para la 1.0 va en la spec de pulido. |

## Project Structure

```text
src/umbra/
├─ cli/watch.py          # WatchApp: compone, aplica Snapshot, acciones (sin SQL en UI)
├─ cli/watch_data.py     # NUEVO: Snapshot + load() en hilo lector; data_version; caché explicaciones
├─ cli/watch.tcss        # NUEVO: estilos
├─ cli/theme.py          # NUEVO: temas umbra / umbra-claro + variables de estado y etapa
├─ cli/spec_screen.py    # SpecScreen(Screen) + SpecApp(App) envoltorio
├─ cli/explain.py        # renderable con colores por variable de tema
├─ unified/clock.py      # NUEVO: hora local, separador de día, duración
├─ unified/store.py      # migración V4 (índices) + data_version()
├─ blocks/notify.py      # send() calla si hay un watch abierto
├─ routines/engine.py    # usa notify.send(conn=…)
├─ adapters/claude_code.py, chat/stream.py, chat/launcher.py  # --setting-sources project
tests/acceptance/test_watch_foundation.py   # NUEVO: rendimiento, hora local, tema, avisos, Screen
tests/acceptance/__snapshots__/             # SVG
```

## Decisiones

- **Hilo lector**: `@work(thread=True, exclusive=True, group="refresh")` con una conexión
  `check_same_thread=False` usada solo por ese grupo exclusivo. `refresh_data(tasks=True)` sigue
  siendo el punto de entrada (los tests lo cuentan); programa el worker y, al terminar, aplica el
  `Snapshot` en el hilo de UI con `call_from_thread`.
- **Sin cambios → nada**: `data_version` igual y misma selección/modo ⇒ solo se actualiza la
  duración del intento en curso (sin SQL).
- **Tabla de tareas**: filas con clave = número; `update_cell` por celda cambiada; `add_row` /
  `remove_row` para altas y bajas; `prevent(RowHighlighted)` mientras se muta.
- **Evidencia y aprobación**: `service.evidence` en worker de hilo; la UI muestra
  «Preparando evidencia…» y abre el modal al terminar.
- **Hora local**: `clock.local(ts)`; en el registro, cuando cambia el día local respecto a la línea
  anterior se escribe una línea separadora `── 4 nov ──`. `umbra log` usa lo mismo.
- **Tema**: `Theme("umbra", …)` y `Theme("umbra-claro", …)` con `variables` `state-*` y `stage-*`;
  `get_theme_variable_defaults` aporta esas variables a los temas integrados. Por defecto «umbra»
  si no hay preferencia; si la guardada no existe se usa «umbra» y se avisa una vez.
- **SpecScreen**: toda la lógica de `SpecApp` pasa a `SpecScreen(Screen)`; `SpecApp.get_default_screen`
  devuelve la pantalla (así `app.query_one("#entry")` y `app.screen` siguen valiendo en los
  tests). `WatchApp._spec_open` hace `push_screen(SpecScreen(...), callback)`; `check_action` de
  `WatchApp` devuelve `False` mientras la pantalla superior sea `SpecScreen`; `escape` en la
  pantalla la cierra dejando la conversación retomable.
- **Avisos**: `WatchApp` toma un lease `watch:<pid>@host` (TTL 60 s, renovado cada 20 s);
  `notify.send(title, body, conn)` no envía si existe un lease `watch:%` vigente. En watch:
  `notify` + `bell` solo si `[notify] bell` (por defecto `true`).
- **Agentes**: `--setting-sources project` en `claude_code.build_command`, `Stream` y `launcher.ask`.
  El chat interactivo (`umbra chat` sin mensaje) es la sesión del propio usuario y no cambia.
