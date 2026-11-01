# Medición del reto de lectura

## Eventos y límites

- `challenge_request`: la API aceptó una solicitud desde el reto. Guarda idioma,
  `already` y `email_status` (`queued` o `not_queued`), con el identificador de
  navegador y atribución existentes. No envía el email del formulario a analítica.
  No demuestra entrega ni descarga. Una tarea en segundo plano puede fallar.
- `challenge_product_click`: clic en un enlace interno a producto dentro del
  contenido del reto. Guarda el slug y el idioma, sin query del enlace destino.
- `purchase_return`: regreso del navegador después del pago. Cierra el estado
  de checkout y conserva el evento Meta Purchase con el mismo ID por pedido.
  No confirma una venta. La ingesta convierte también el antiguo evento público
  `purchase` a `purchase_return`, para scripts que aún estén en caché.
- Las ventas e ingresos del panel, histórico, serie diaria y tabla de productos
  cuentan solo `purchase` con `ua_class=server`. Son los eventos emitidos por la
  confirmación del pago. Los antiguos `purchase` del navegador quedan excluidos
  sin borrar registros. Los períodos históricos pueden bajar respecto del panel
  anterior; un período con solo eventos de navegador ya no cuenta esas ventas.
  Si falló el registro del servidor, este panel no reconstruye la venta: para
  conciliación contable se necesitan los pedidos pagados.

Los eventos del reto no sustituyen estados activos de carrito o checkout.
No se añadieron llamadas a proveedores ni envíos automáticos nuevos.
La respuesta de suscripción distingue una tarea programada de un envío real;
para suscriptores que ya recibieron la bienvenida no se programa otro correo.
Las bajas existentes siguen respetándose.

## Lectura de resultados

Medir por separado entradas a cada idioma, solicitudes aceptadas (y cuántas
quedaron pendientes de envío), clics a productos y pasos de carrito/checkout.
El ID actual vive en localStorage y puede persistir entre visitas: no representa
por sí solo una sesión delimitada, una persona ni una atribución causal.

Los eventos se conservan en la analítica del VPS. Este cambio no añade un informe
MCP de conversiones ni una unión fiable entre pedido pagado y entrada al reto.
El PDF gratuito sigue siendo un archivo estático: no se registra su descarga
con estos eventos. No llamar descarga ni venta a una solicitud del formulario.

Para la guía editada el 31 de octubre de 2026, usar datos GSC posteriores al
cambio: primera revisión con 14 días completos y siguiente con 28. El informe
consultado el 1 de noviembre termina el 28 de octubre y es solo la referencia
previa al cambio. La programación de informes no fue modificada.

## Verificación sin producción

Con dependencias instaladas y sin `server/.env`, ejecutar con un entorno limpio
sin credenciales y `DATABASE_URL=sqlite:///:memory:`:

```sh
server/.venv/bin/python -m unittest discover -s server/tests -p 'test_cart_diagnostic_events.py'
server/.venv/bin/python -m unittest discover -s server/tests -p 'test_challenge_subscription.py'
server/.venv/bin/python -m unittest discover -s server/tests -p 'test_tracking_ingestion.py'
TBW_BROWSER_TEST_MODULES=/ruta/node_modules TBW_TEST_CHROMIUM=/ruta/chromium node tests/challenge-measurement.browser.cjs
```

Las pruebas usan bases temporales y APIs simuladas. No compran, envían correos
ni generan eventos de producción. No se requiere migración de base de datos.
