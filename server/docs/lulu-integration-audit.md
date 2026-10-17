# Auditoría web → Lulu y coexistencia con Etsy

Fecha: 17 de octubre de 2026. Repositorio de la web revisado en `7069a40`.

## Alcance y resultado

La revisión autorizada del documento de contexto se realizó con consultas de lectura en la VPS y comprobaciones offline. No se ejecutó el worker Etsy manualmente, no se crearon pedidos reales o de prueba, no se capturaron pagos y no se enviaron notificaciones. Las correcciones de este PR están preparadas para revisión; no se han desplegado. No cambia la integración Etsy, sus archivos de configuración, sus historiales ni sus cron.

## Comprobado en la VPS

- El servicio `thebookswanderer.service` está activo como `www-data`, con el intérprete existente en `/var/www/thebookswanderer.com/server/.venv/bin/python` y configuración en `server/.env`.
- `main.py`, `models.py`, `database.py`, `services/lulu.py`, `lulu_check.py` y `sync_order_tracking.py` coinciden por SHA-256 con el repositorio revisado.
- `scripts/sync_lulu_tracking.py` existe todavía en disco y no está en `main`, pero no tiene cron activo. No se borró ni se sobrescribió.
- Un único cron de seguimiento web ejecuta `sync_order_tracking.py` a los minutos 17 de cada dos horas. El registro muestra ciclos hasta las 10:17 UTC del 17 de octubre, sin excepciones en las últimas 100 líneas examinadas.
- Un único cron Etsy ejecuta el worker unificado cada 15 minutos. Los dos cron antiguos están comentados. Se observó una ejecución programada a las 11:30 UTC; posteriormente apareció su registro, sin contenido ni traceback. No había procesos del worker activos en la lectura posterior. Su punto de entrada captura errores y los imprime al registro; el procesamiento normal puede terminar en silencio si no hay recibos elegibles. Se comprobó el arranque programado y ausencia de errores registrados, pero no una venta nueva ni un código de salida histórico explícito.
- Web y Etsy usan las mismas credenciales de cliente Lulu y pueden leer el mismo trabajo histórico, en estado `SHIPPED`, cuyo ID externo pertenece a Etsy. No se publicaron credenciales, identificadores de comprador ni respuestas completas.
- La configuración unificada de Etsy conserva `create_jobs_enabled=true`, `manual_payment_confirmed=true` y `etsy_tracking_approved=false`. El teléfono comercial autorizado está configurado allí. La web todavía no tiene `LULU_MERCHANT_PHONE`.
- La base de datos web no tiene pedidos registrados; no hay ventas web para una verificación real de fabricación, tracking o recuperación. El estado Etsy conserva un receipt histórico bloqueado y un job histórico.

El estado de pago manual se apoya en la configuración existente y en la evidencia de portal aportada en la sesión de origen; no se volvió a consultar una pantalla de facturación. Ningún código revisado invoca un endpoint de pago de Lulu. La creación de un job no sustituye comprobar Auto Pay en el portal: si alguien lo activara allí, podría cambiar el comportamiento de cobro. [Documentación oficial](https://help.api.lulu.com/en/support/solutions/articles/64000293838-how-do-i-set-up-automatic-payment-fulfillment-for-my-api-orders-).

## Archivos físicos

Los seis productos activos suman nueve variantes. En todas se comprobó presencia de interior/cubierta, hash, acceso HTTP 200 con firma y PDF válido por cabecera; sin firma responden 404. Se consultaron las dimensiones de cubierta de Lulu para el paquete y número de páginas, y coinciden con los PDF desplegados.

| Producto | Variantes | Páginas interiores | Cubierta |
| --- | --- | --- | --- |
| Reading Passport paperback | EN / ES | 40 | Coincide |
| Reading Passport hardcover | EN / ES | 40 | Coincide |
| Color the Classics | EN / ES | 60 | Coincide |
| The Lost Manuscript | EN | 96 | Coincide |
| Book Club Companion | EN | 100 | Coincide |
| Commonplace Book | EN | 160 | Coincide |

Los identificadores de paquete existentes se conservaron. Esta revisión no equivale a imprimir una prueba física ni a volver a normalizar todas las páginas con Lulu. No se publicaron las URLs firmadas.

## Problemas confirmados y correcciones preparadas

1. **Creación ambigua y duplicados.** Antes, una respuesta perdida después de que Lulu aceptara el job dejaba `lulu_job_id` vacío. Un reintento podía crear otro. El PR guarda una reclamación duradera por pedido antes del POST, consulta referencias exactas con paginación, respeta cantidades y variantes y persiste el resultado. Una creación incierta no vuelve a enviarse automáticamente. Coincidencias múltiples o discrepancias de líneas requieren revisión.
2. **Recuperación sin reenvío.** `reconcile_lulu_submissions.py` permite localizar jobs ya existentes. Por defecto solo informa; `--apply` restaura el vínculo local verificado. Nunca crea jobs, captura PayPal, paga producción, envía correo ni programa otro cron.
3. **Datos de envío ficticios.** Se elimina `Customer`/`0000000000` como sustitución. Un contacto incompleto se bloquea antes de crear el checkout PayPal. Se admite un teléfono comercial real mediante `LULU_MERCHANT_PHONE` cuando el comprador omite el suyo; un teléfono introducido pero inválido no se sustituye silenciosamente.
4. **Pago manual tratado como error.** El tracking actual clasifica `UNPAID` como problema y recomienda añadir tarjeta. El PR lo considera una espera normal y dirige al pago manual. Conserva el periodo de gracia y los avisos existentes, sin nuevas tareas programadas.
5. **Pedidos mixtos incompletos.** El tracking podía marcar el pedido entero como enviado si solo las partes conocidas habían salido, aunque otra aún no tuviera job. El PR exige referencias de todos los proveedores y almacenes necesarios antes de cerrar el pedido.

La tabla adicional `lulu_submissions` se crea con el mecanismo de esquema existente. No reemplaza tablas o historiales. El workflow de despliegue incluye el nuevo módulo, pero este PR no se ha fusionado ni desplegado.

## Validación

145 pruebas offline aprobadas, incluidas 17 específicas de esta revisión. Cubren respuesta perdida, fallo de commit después de la aceptación, concurrencia, reclamación interrumpida, coincidencias parciales de ID, paginación, duplicados remotos, cantidades y paquetes distintos, reconciliación sin POST, teléfono real de respaldo, datos ficticios y pedidos mixtos. Las llamadas de proveedor y pago están simuladas.

## Antes de desplegar

- Reutilizar de forma privada el teléfono comercial ya autorizado en la configuración Etsy para `LULU_MERCHANT_PHONE` de la web, sin publicarlo ni volver a pedirlo. No copiar el resto de credenciales o configuración de Etsy.
- Mantener Auto Pay y los pagos programados de Lulu desactivados. No registrar tarjetas recurrentes desde estos cambios.
- Conservar copia de la base de datos y configuración. El cambio es aditivo; la tabla de reclamaciones debe conservarse incluso si se revierte código, para no perder el historial de intentos.
- Desplegar por GitHub Actions, comprobar salud y el esquema, y ejecutar inicialmente la reconciliación en modo de lectura. No ejecutar `_fulfil` ni un envío como prueba.

## Pendientes reales

- **PayPal sin retorno del navegador:** el código desplegado captura/verifica el pago en `/api/checkout/return`; no se encontró un webhook de PayPal ni un reconciliador de pagos capturados. La presencia de `PAYPAL_WEBHOOK_ID` no demuestra que exista un consumidor. Este PR no añade ni activa ese flujo. Hace falta diseñarlo con verificación del evento/importe y exclusión mutua, sin cobrar o reenviar pedidos en pruebas.
- **Primera venta nueva:** no se ha verificado un pedido nuevo de extremo a extremo. El job histórico enviado de Etsy no demuestra que una venta web ni el worker consolidado hayan completado el flujo nuevo.
- **Voronoi:** la lectura final confirma siete entradas de catálogo, seis habilitadas y una deshabilitada intencionalmente: Voronoi. No se habilitó ni se sustituyeron sus archivos por los digitales.

## Evidencia de las lecturas

Ejecuciones temporales en la rama de auditoría; no despliegan la aplicación:

- [Código, servicio, configuración y cuenta](https://github.com/rising-sunny/thebookswanderer.com/actions/runs/39028825889)
- [PDF, dimensiones, acceso firmado y cron](https://github.com/rising-sunny/thebookswanderer.com/actions/runs/39028911552)
- [Programación y registro del worker](https://github.com/rising-sunny/thebookswanderer.com/actions/runs/39029040016)
- [Estado agregado posterior al ciclo](https://github.com/rising-sunny/thebookswanderer.com/actions/runs/39029257448)

- [Catálogo retenido y procesos del worker](https://github.com/rising-sunny/thebookswanderer.com/actions/runs/39029426682)
- [Punto de entrada y comportamiento de registro, con literales ocultos](https://github.com/rising-sunny/thebookswanderer.com/actions/runs/39029559380)
