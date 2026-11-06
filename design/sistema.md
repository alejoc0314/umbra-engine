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
| error (conflicto, acción fallida) | `#FF5555` | `#B42318` |
| info (aviso de salud: posible obsoleta) | `#8BE9FD` | `#0B6E85` |

Estados de lección: **propuesta** = aviso (ámbar), **aprobada** = éxito, **descartada** y
**retirada** = texto-tenue (tachado no: se lee mal en terminal; se marca con la palabra).
El ámbar queda **reservado a «por decidir»**. Los avisos de salud de una lección vigente nunca
usan ámbar: `△ posible obsoleta` en info y `≠ conflicto con Ln` en error, en una segunda línea
de 12 px bajo el texto de la fila, alineada con el texto.

## Espaciado

Múltiplos de una celda: 1 celda horizontal (8 px), 1 fila (20 px). Paneles con 1 fila y 2
celdas de relleno. Separación entre paneles: 1 celda.

## Componentes base

- **Cabecera**: nombre del proyecto, rama de spec, contadores (`2 en curso · 3 lecciones por decidir`).
- **Panel**: borde de una línea con título incrustado en el borde superior.
- **Fila de lista**: columnas de ancho fijo — cursor 1 celda, marcador 2 celdas centrado
  (`●` propuesta, `✓` aprobada, `–` descartada, `↺` retirada), id 4 celdas, texto (resto,
  una sola línea, se trunca con `…`), zona 27 celdas. Avisos de salud en segunda línea tenue.
- **Vista de la lista** (`f` la cambia): `por decidir + vigentes` (las descartadas y retiradas
  se resumen en una línea «ocultas: …») o `todas`. La etiqueta dice siempre lo que se ve.
- **Línea de estado** (entre el cuerpo y el pie, solo mientras hace falta): borde izquierdo de
  3 px + icono + mensaje + pista tenue a la derecha. Variantes: en curso (`↻` primario,
  «cosechando…»), hecho (`✓` éxito al aprobar, `↺` primario al retirar) y error (`✗` error,
  p. ej. «ya la aprobó desde Telegram»; la lista se actualiza sola).
- **Pie de atajos**: tecla en primario sobre superficie-alta + verbo en texto-tenue. Solo se muestran las acciones válidas para el estado seleccionado.
- **Editor de una línea** (modal): superficie con borde primario sobre la bandeja velada; campo
  de texto (borde primario con foco, marca `editado` si cambió), el original debajo en
  texto-tenue («queda en su historial»), campo de zona (pista «Tab ir a zona», el mismo texto
  que en la barra de teclas), el efecto en una frase y
  `Enter aprobar · Tab ir a zona · Ctrl+Z volver al original · Esc cancelar`.
  Enter solo significa «aprobar» dentro de este editor; fuera de él no hace nada en Lecciones.
- **Detalle de lección**: id + chip de estado, texto (y su aviso de salud), ZONA, SE APLICA(RÍA)
  EN y **justo debajo las acciones válidas**: propuesta `a aprobar…`/`d descartar`, vigente
  `x retirar`; siempre `v historial completo`. Después, separador e HISTORIAL / POR QUÉ SE
  PROPONE: cada entrada en dos líneas (`#N verbo · fecha` tenue arriba, descripción a todo el
  ancho debajo).
- **Vacío**: frase en negrita, explicación tenue de cuándo propone umbra y el atajo `h`.
- **Telegram**: mensajes con texto plano y botones en línea (Aprobar · Descartar · Ver).
