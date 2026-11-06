# Quickstart: validar contexto y lecciones

## Pruebas automáticas (sin red ni modelos)

```bash
uv run pytest tests/unit/test_explore.py tests/unit/test_lessons.py tests/acceptance -q
uv run ruff check .
```

Usan agentes falsos (`tests/fakes`), un repo git temporal con historia y `UMBRA_HOME` apuntando a
una carpeta temporal, para que `lessons.db` no toque la máquina real.

## Escenarios que deben pasar

| # | Preparación | Acción | Resultado esperado |
|---|-------------|--------|--------------------|
| 1 | Repo con `src/pagos/cobro.py`, `tests/test_cobro.py` y 3 commits sobre cobro | Ejecutar una tarea con `scope = ["src/pagos/**"]` | El evento `explore.ready` lista cobro.py ("en scope"), test_cobro.py y los 3 commits; el `Envelope` de `build` trae `context` |
| 2 | Igual que el 1, con una ejecución anterior #12 que tocó cobro.py | Ejecutar la tarea | El paquete nombra la #12 y su resultado |
| 3 | Repo con 200 commits sobre la zona y `max_chars = 2000` | Ejecutar | `chars` ≤ 2000; `omitted` dice cuánta historia quedó fuera |
| 4 | Repo sin tests ni historia | Ejecutar | El paquete se arma con lo que hay, con una nota; la tarea sigue |
| 5 | Explorar lanza una excepción (simulada) | Ejecutar | Evento `explore.failed`; `build` corre sin `context`; `explain` dice por qué |
| 6 | Revisar falso con un hallazgo `high` y luego sin hallazgos | Ejecutar hasta Integrar | Aparece `L1` `proposed` con origen `review_rejected`, la tarea y la fecha |
| 7 | `L1` propuesta | Nueva tarea sobre la misma zona | Su paquete **no** incluye L1 |
| 8 | `umbra lesson approve L1 --text "…"` | Nueva tarea sobre la zona | El paquete incluye el texto editado; el historial guarda el original |
| 9 | `umbra lesson retire L1` | Nueva tarea | Ya no la incluye; `explain` de la tarea anterior sigue mostrando L1 |
| 10 | `umbra lesson discard L2`; se repite el mismo tropiezo | Cosechar | No aparece `L3`: L2 suma un origen |
| 11 | Ejecución detenida; `umbra done 5 -m "faltaba migrar la tabla"` | Cosechar | Lección propuesta con origen `human_correction` |
| 12 | Lecciones aprobadas | `git status` | Sin cambios |
| 13 | Clonar el repo de nuevo en otra carpeta | `umbra lesson list` | Mismas lecciones (misma clave de primer commit) |
| 14 | El hallazgo contiene `ghp_…` | Cosechar | El texto y el origen guardan `«oculto»` |
| 15 | Dos aprobadas con `conflicts_with` | Nueva tarea | Ninguna de las dos entra; `list` muestra el conflicto |
| 16 | Espacio con `front/` y `back/` | Tarea entre repos | Rutas del paquete con prefijo de repo; lecciones con la clave del espacio |
| 17 | `umbra lesson export > l.json`; borrar `lessons.db`; `import l.json` | `list --all` | Estados, orígenes y fechas intactos |

## Smoke manual con agentes reales (sandbox/)

1. En `sandbox/`, `umbra run` sobre una tarea pequeña; comprobar en `umbra explain <n>` la sección
   Contexto y abrir el paquete desde `watch` (detalle de la tarea, en Revisar).
2. Forzar un rechazo de Revisar (por ejemplo, pidiendo algo que viole una regla de la
   constitución); al terminar, comprobar en `watch` (tecla `l`) y en Telegram (`/lecciones`) la
   propuesta y aprobarla.
3. Crear otra tarea sobre esa zona y comprobar que el paquete trae la lección y que el coste de
   la tarea no sube por Explorar (Explorar no consume modelo).

## Piloto (SC-003 y SC-004)

Comparar en `landing-manager` 10 tareas antes y 10 después:

- coste medio de Construir;
- rechazos de Revisar repetidos por la misma causa.

Ajustar `max_chars` si el paquete se queda corto o sobra.
