# Contribuir a umbra

Gracias por querer mejorar umbra. Todo el proyecto (código, specs y documentación) está en
español.

## Antes de empezar

- **Errores**: abre un issue con la plantilla «Algo no funciona»; incluye `umbra --version`,
  tu sistema y los pasos para reproducirlo.
- **Ideas**: ábrelas como issue «Propuesta» o en Discussions antes de escribir código; los
  cambios grandes pasan por una spec (ver abajo).
- **Vulnerabilidades**: nunca en un issue público; sigue [`SECURITY.md`](SECURITY.md).

## Preparar el entorno

```bash
uv sync
uv run pytest -q        # sin red ni costo: agentes, gh y Telegram falsos
uv run ruff check .
```

## Cómo se trabaja

1. **Specs primero.** Cada funcionalidad nueva tiene su carpeta en `specs/NNN-nombre/` con
   `spec.md`, `plan.md` y `tasks.md` (Spec Kit). Los arreglos pequeños no necesitan spec.
2. **La constitution manda.** [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
   fija los principios (aprobación humana, evidencia, agentes intercambiables…). Un PR que la
   contradiga necesita antes una enmienda.
3. **Tests.** Todo cambio de comportamiento llega con su test; `pytest` y `ruff` en verde.
4. **CHANGELOG.** Si el cambio se nota para quien usa umbra, añade una línea al final de
   `## Sin publicar` en [`CHANGELOG.md`](CHANGELOG.md), en lenguaje llano. No cambies la versión:
   eso lo hace `scripts/release.py` al publicar.
5. **PR pequeño** contra `main`, con la plantilla completa.

## Licencia

Al contribuir aceptas que tu aporte se publique bajo la [licencia Apache 2.0](LICENSE).
