# Indicaciones para agentes en umbra-engine

## Cada cambio deja su línea en el CHANGELOG

Si tu cambio afecta a quien usa umbra (un comando nuevo, otro comportamiento o un error
corregido), añade un punto al final de `## Sin publicar` en `CHANGELOG.md`:

- En español llano: qué puede hacer ahora quien usa umbra, no cómo está hecho por dentro.
- Una o dos líneas, en el estilo de las versiones anteriores.
- Los cambios internos (refactor, solo tests, solo specs) no llevan línea.

No cambies `__version__` ni crees secciones `## vX.Y.Z`: eso lo hace
`scripts/release.py prepare` al publicar.
