# Indicaciones para agentes

- Tests con `php artisan test` y estilo con `vendor/bin/pint --test`; nada se integra en rojo.
- Cada cambio de comportamiento trae su test (Feature o Unit). No se borran ni se desactivan
  tests existentes.
- Migraciones siempre reversibles; nada de SQL crudo contra producción.
- La app se verifica en el navegador con `php artisan serve`: cada pantalla nueva debe cargar sin
  errores con datos de prueba.
