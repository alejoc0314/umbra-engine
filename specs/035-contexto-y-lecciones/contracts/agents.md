# Contrato: sobre de los agentes y redactor de lecciones

## `Envelope.context` (nuevo campo opcional)

```python
context: str | None = None  # paquete de Explorar para esta tarea (con tope)
```

- `schema_version` sigue en `"1"`: el campo es opcional y los adaptadores que no lo conocen lo
  ignoran.
- Lo reciben `plan`, `design`, `build`, `review`, `verify` y `arbiter`. No lo reciben `critic`,
  `summary` ni `lesson`.
- `adapters/base.py` lo presenta después de `project_notes`, con este encabezado:
  "Contexto de esta tarea (reunido por umbra antes de empezar: archivos, tests, historia, tareas
  anteriores y lecciones aprobadas por la persona; léelo antes de explorar por tu cuenta)".

### Forma del `.md` del paquete (lo que ve el agente)

```markdown
# Zona de la tarea
- src/pagos/cobro.py — en scope
- src/pagos/tarifas.py — cambia junto a cobro.py
# Tests que la cubren (comando: `test`)
- tests/test_cobro.py — cubre src/pagos/cobro.py
# Historia reciente
- 1a2b3c4 2026-10-30 «redondeo de tarifas» (cobro.py, tarifas.py)
# Tareas anteriores de umbra en esta zona
- #12 «Cobro con descuento» — integrada; Revisar pidió: «no redondear antes de sumar»
# Lecciones aprobadas por la persona (respétalas)
- L7: En pagos, redondear solo al final y con Decimal.
# Omitido por tope
- 14 commits de historia
```

## `lesson-writer` (perfil nuevo en `defaults/profiles/`)

```toml
name         = "lesson-writer"
agent        = "claude-code"
roles        = ["lessons"]
model        = "haiku"
instructions = "lesson-writer.md"
actions      = []
output       = "lesson-draft/v1"

[limits]
max_minutes  = 3
max_cost_usd = 0.10
```

**Entrada**: el `Envelope` normal con `stage = "lesson"`.

- `feedback` lleva los hechos del tropiezo:
  - el tipo;
  - los hallazgos o el motivo;
  - el mensaje de la persona;
  - los archivos implicados.
- `findings` lleva los hallazgos de Revisar, si los hay.
- `project_notes` lleva las lecciones existentes en esa zona, con su `L<n>`, estado y texto.

**Salida** (`output_model = LessonDraft`):

```python
class LessonDraft(BaseModel):
    skip: bool = False             # nada generalizable (p. ej. error de red puntual)
    text: str = ""                 # regla corta, imperativa, ≤ 280 caracteres
    zone: list[str] = []           # globs relativos; [] = todo el proyecto
    same_as: int | None = None     # equivale a la lección L<n> ya existente
    conflicts_with: list[int] = [] # contradice estas lecciones aprobadas
```

**Validación del motor** (principio III):

- `text` no puede estar vacío si `skip` es falso.
- Los globs de `zone` no pueden salir del proyecto (nada de `..` ni rutas absolutas).
- `same_as` y `conflicts_with` se descartan si no existen en el proyecto.
- Si `same_as` apunta a una lección descartada, solo se suma el origen.
- Se ocultan los secretos.
- Si falla la validación, se usa el borrador determinista (research §8).
- El coste cuenta en la ejecución (intento con `stage = "lesson"`).
