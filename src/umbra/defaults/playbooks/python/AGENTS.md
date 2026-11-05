# Indicaciones para agentes

- Los tests van en `tests/` y se corren con `uv run pytest -q`; el lint es `uv run ruff check .`.
  Nada se integra con tests o lint en rojo.
- Cada cambio de comportamiento trae su test. No se borran ni se desactivan tests existentes.
- Código y comentarios en el idioma del proyecto; mensajes de commit cortos, en imperativo.
- No se añaden dependencias sin justificarlo en la tarea.
