# Contrato: CLI, watch y Telegram

Todos los comandos aceptan `--json`. Los mensajes van en español llano.

## `umbra lesson` (nuevo grupo)

| Comando | Qué hace |
|---------|----------|
| `umbra lesson list [--all] [--status S]` | Por defecto, las propuestas y las aprobadas del proyecto actual. `--all` incluye las descartadas y las retiradas. Marca las posiblemente obsoletas y las que están en conflicto. |
| `umbra lesson show L<n>` | Texto, zona, estado, orígenes (tarea, etapa, motivo, fecha), historial y tareas en las que se aplicó. |
| `umbra lesson approve L<n> [--text T] [--zone G ...] [--project-wide]` | Aprueba la lección (si estaba retirada, la vuelve a aprobar). Si se edita, el texto anterior queda en el historial. |
| `umbra lesson discard L<n> [--reason R]` | Descarta una propuesta. |
| `umbra lesson retire L<n> [--reason R]` | Retira una aprobada. |
| `umbra lesson resolve L<a> L<b>` | Marca dos lecciones como compatibles y quita el conflicto. Para quedarte con una, retira la otra. |
| `umbra lesson harvest` | Cosecha ya las fuentes pendientes del proyecto. |
| `umbra lesson export [ARCHIVO]` | Exporta el JSON del proyecto (a stdout si no das archivo). |
| `umbra lesson import ARCHIVO` | Importa al proyecto actual. Lo que ya existía se reconoce por texto y zona, y se mezclan sus orígenes. |

**Salida `--json` de `list`**:

```json
[{"id": "L7", "status": "approved", "text": "…", "zone": ["src/pagos/**"],
  "origins": 2, "stale": false, "conflicts": [], "updated_at": "…"}]
```

**Errores**, con código de salida ≠ 0 y mensaje accionable:

- `L<n>` no existe;
- la transición no es válida (p. ej. retirar una propuesta);
- no hay proyecto;
- `lessons.db` no se pudo abrir: umbra explica la causa y las tareas siguen sin lecciones.

**Quién puede decidir**: aprobar, descartar, retirar y resolver lo hace la persona, desde una
terminal, `watch` o Telegram (con el `chat_id` verificado).

- El chat (`umbra chat`) solo puede usar `list` y `show`: no se añaden a sus comandos de acción.
- Los agentes no tienen acceso.

## `umbra explain <n>`

- **Texto**: nueva sección **Contexto**. Muestra cuántos archivos, tests, commits, tareas
  anteriores y lecciones aplicadas hubo; los caracteres frente al tope (`9 310 / 12 000`); lo
  omitido; y la ruta del paquete.
- **`--json`**: nueva clave `context`, con el resumen de `data-model.md`, o `null` y `reason` si
  Explorar falló o la rutina no tiene esa etapa.

## `umbra watch`

- **Tecla `l`**: panel **Lecciones**, con propuestas primero.
  - Desde el panel: aprobar (`a`, abre un editor de una línea con el texto propuesto), descartar
    (`d`) y retirar (`x`), según el estado.
- **Detalle de tarea** (Revisar y cualquier etapa posterior a Explorar): bloque "Contexto que
  recibió" con el resumen y la acción "ver paquete", que abre el `.md`.
- **Cabecera**: `N lecciones por decidir` cuando haya propuestas.

## Telegram

- **Comandos nuevos**:
  - `/lecciones`: las propuestas, cada una con los botones Aprobar, Descartar y Ver;
  - `/leccion Ln`: el detalle, con los botones que aplican.
- **Aviso**: cuando la cosecha crea propuestas, llega un mensaje "Hay N lecciones nuevas por
  decidir", agrupado (un mensaje por cosecha, no uno por lección).

## Configuración (`.umbra/project.toml`)

```toml
[context]
max_chars = 12000      # tope del paquete de Explorar

[lessons]
enabled = true         # false: no se cosecha ni se aplica nada en este proyecto
writer  = "lesson-writer"   # perfil que redacta; "" = solo borrador determinista
```
