# Sistema de diseño de umbra (TUI `umbra watch` y Telegram)

umbra vive en la terminal: `umbra watch` es una app Textual. Todo se diseña sobre una
retícula de celdas monoespaciadas (1 celda = 8 px de ancho × 20 px de alto en las maquetas a
1280×800, ~160×40 celdas). Nada de sombras ni degradados: bordes de una línea, color con
intención y tipografía monoespaciada.

## Tipografía

- Familia única: **JetBrains Mono** (en la terminal real, la fuente de la persona).
- Tamaños en maqueta: 13 px texto, 13 px negrita para títulos de panel, 11 px para pies y atajos.
- Interlineado 20 px (una fila de terminal). Jerarquía por peso y color, no por tamaño.

## Paleta (roles, oscuro por defecto; la persona usa el tema Dracula en Warp)

| Rol | Oscuro | Claro |
|-----|--------|-------|
| fondo | `#1E1F29` | `#FAF8F3` |
| superficie | `#282A36` | `#FFFFFF` |
| superficie-alta (fila seleccionada) | `#343746` | `#EFEBE1` |
| borde | `#44475A` | `#D9D3C4` |
| texto | `#F8F8F2` | `#1F1D1A` |
| texto-tenue | `#A4A8C0` | `#6A645A` |
| primario (acento, foco) | `#BD93F9` | `#6D3FD0` |
| éxito (aprobada) | `#50FA7B` | `#1F7A3E` |
| aviso (propuesta / por decidir) | `#F1FA8C` / `#FFB86C` | `#9A5B00` |
| error (conflicto) | `#FF5555` | `#B42318` |

Estados de lección: **propuesta** = aviso (ámbar), **aprobada** = éxito, **descartada** y
**retirada** = texto-tenue (tachado no: se lee mal en terminal; se marca con la palabra).

## Espaciado

Múltiplos de una celda: 1 celda horizontal (8 px), 1 fila (20 px). Paneles con 1 fila y 2
celdas de relleno. Separación entre paneles: 1 celda.

## Componentes base

- **Cabecera**: nombre del proyecto, rama de spec, contadores (`2 en curso · 3 lecciones por decidir`).
- **Panel**: borde de una línea con título incrustado en el borde superior.
- **Fila de lista**: marcador de estado (`●` propuesta, `✓` aprobada, `–` descartada, `↺` retirada), id `L7`, texto truncado, zona.
- **Pie de atajos**: tecla en primario sobre superficie-alta + verbo en texto-tenue. Solo se muestran las acciones válidas para el estado seleccionado.
- **Editor de una línea** (modal): superficie con borde primario sobre la bandeja velada; campo
  de texto (borde primario con foco, marca `editado` si cambió), el original debajo en
  texto-tenue («se guarda en el historial»), campo de zona (Tab), el efecto en una frase y
  `Enter aprobar · Tab cambiar a zona · Ctrl+Z volver al original · Esc cancelar`.
- **Detalle de lección**: id + chip de estado, texto, ZONA, HISTORIAL (origen `#N`, verbo,
  qué pasó, fecha; incluye el texto original si se editó y en cuántas ejecuciones se usó),
  SE APLICA EN, y abajo solo las acciones válidas: propuesta `a`/`d`, vigente `x`,
  descartada/retirada ninguna (solo `Enter` historial).
- **Vacío**: frase en negrita, explicación tenue de cuándo propone umbra y el atajo `h`.
- **Telegram**: mensajes con texto plano y botones en línea (Aprobar · Descartar · Ver).
