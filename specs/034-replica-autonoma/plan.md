# Implementation Plan: Réplica autónoma y genérica

- **`contracts/profile.py`**: nueva acción `shell`. En **`adapters/claude_code.py`** se traduce a
  `Bash` con `--disallowedTools` para `git commit/push/reset/checkout/switch/clean/stash/rebase/`
  `merge/restore/rm/tag`. Playwright se abre con `--caps=network,storage`.
- **`defaults/profiles/replicator.*`**:
  - instrucciones genéricas en cinco pasos: preparar, capturar, sistema, herramienta, dejar todo
    como estaba;
  - `actions` incluye `shell`;
  - límites de 60 min y US$10.
- **`management/replica.py`**:
  - el agente trabaja desde `home`, que es la carpeta padre en un espacio;
  - el primer `feedback` dice la carpeta de diseño;
  - `_tidy` restaura lo versionado (falla) y borra lo suelto (no falla);
  - todo o nada con `discard`, que ahora también borra las carpetas vacías;
  - `onboarding.agent(..., allowed_paths=...)`.

## Constitution Check

- **V (sesiones acotadas):** `shell` es más amplio. Se justifica porque sin él la réplica no
  puede funcionar en proyectos reales (caso `landing-manager`). Queda acotado por el veto de
  `git`, la regla de escribir solo en bases de datos locales, la restauración de todo lo
  versionado y los límites de tiempo y costo.
- **VII:** la persona sigue aprobando la réplica.
- **X:** sin dependencias nuevas.

## Pruebas

Cubiertas en `test_design_systems`, `test_cross_repo` y `test_e1_units`:

- réplica completa con limpieza de lo suelto;
- cambio de código: se restaura y se descarta;
- vistas faltantes: se descarta entera;
- espacio desde la carpeta padre;
- permisos de `shell`.
