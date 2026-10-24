# Retomar The Books Wanderer desde otra cuenta

Actualizado: 24 de octubre de 2026. Este documento no contiene credenciales.
El código y la configuración desplegada pueden cambiar: verifica su estado
antes de operar. Los datos de Search Console y Merchant Center de abajo son
observaciones fechadas, no consultas en tiempo real.

## Política del dueño

Las claves de CJ, Printify, Lulu, Prodigi y futuras integraciones se guardan y
utilizan exclusivamente en el VPS. Codex sirve para editar código y probar con
datos ficticios. Las consultas y operaciones autenticadas contra proveedores
se ejecutan en el VPS, preferentemente mediante herramientas limitadas del MCP.
No introducir claves de proveedores en las variables del entorno de Codex.

La autorización del propio cliente a GitHub o al MCP es independiente: una
sesión OAuth del cliente puede ser necesaria para conectarse, pero no debe
transportar las claves de los proveedores. Si el dueño exige que tampoco exista
una sesión de acceso en el cliente, deberá ejecutar él mismo los comandos en el
VPS y compartir resultados sanitizados.

No está confirmado que las credenciales anteriormente configuradas en Codex
hayan sido eliminadas de su configuración persistente. El dueño debe retirarlas
y reiniciar/recrear ese entorno; cambiar este repositorio no las elimina.

## Accesos que necesita una cuenta nueva

1. Acceso autorizado al repositorio `rising-sunny/thebookswanderer.com` en GitHub.
2. Un entorno de desarrollo sin credenciales de proveedores.
3. Autorización separada al MCP del VPS, si el cliente permite conectar ese MCP.
   No se obtiene por clonar el repo ni por añadir una URL a un archivo.
4. Acceso SSH solo si la tarea lo necesita y el dueño lo configura expresamente.
   No copies una clave SSH privada al entorno para sustituir el MCP.

El historial de este chat, los cambios sin commit y los archivos adjuntos no se
transfieren a otra cuenta. Publica el código y la documentación mediante una
rama/PR y conserva los informes sin datos privados en el lugar adecuado.

## Arquitectura y rutas

| Componente | Referencia |
| --- | --- |
| Web | `https://thebookswanderer.com` |
| Frontend | HTML/CSS/JS en la raíz, `guides/`, `assets/` |
| API y renderizado SEO | `server/main.py`, `server/ssr.py`, `server/urls.py` |
| Servicios de proveedores | `server/services/` |
| Pagos | PayPal; captura y envío al proveedor son operaciones reales |
| VPS: árbol de producción | `/var/www/thebookswanderer.com` |
| Python del servicio | `/var/www/thebookswanderer.com/server/.venv/bin/python` |
| Servicio de la tienda | `thebookswanderer.service`, Uvicorn en `127.0.0.1:8010` |
| Base de producción | `server/data/store.db` en el VPS; no sustituir por la copia local |
| Configuración de la tienda | `/var/www/thebookswanderer.com/server/.env` |
| Prodigi: clave protegida | `/etc/tbw-prodigi/api_key`; systemd `LoadCredential` |
| Prodigi: original de impresión | `/var/lib/tbw-prodigi/artwork` |
| Sitemap dinámico | `https://thebookswanderer.com/sitemap.xml` |
| Feed de productos | `https://thebookswanderer.com/api/feeds/google-products.xml` |

No uses un servidor local con una copia de la base o `.env` de producción.
Importar la aplicación o ejecutar scripts puede inicializar tablas o activar
otros comportamientos: revisa el código y aísla datos antes de hacerlo.

## Credenciales verificadas en el VPS

En la salida que compartió el dueño, `CJ_API_KEY`, `LULU_CLIENT_KEY` y
`LULU_CLIENT_SECRET` aparecían presentes tanto en `.env` como en el entorno del
proceso activo de la tienda. Se comprobó presencia, no validez ante el proveedor.
No se mostraron ni copiaron sus valores.

El código de Prodigi utiliza el archivo protegido indicado arriba. El resto de
las credenciales y los permisos efectivos deben comprobarse en el VPS sin
imprimir valores. No asumir que una variable configurada en Codex está en el VPS,
ni que la ausencia en una terminal implica ausencia en el proceso systemd.

## MCP del VPS

El dueño reportó que el MCP con OAuth funcionaba y que `tbw_health` y
`tbw_list_products` habían sido probados. Su código estaba en el PR #93:
<https://github.com/rising-sunny/thebookswanderer.com/pull/93>.
En la revisión de `main` realizada para esta guía, `deploy/mcp/` no estaba
presente. No se ha vuelto a comprobar la instalación en producción desde esta
sesión. Comprueba revisión/fusión e instalación por separado.

Diseño documentado en esa rama: endpoint `https://thebookswanderer.com/mcp`,
OAuth de GitHub limitado al dueño autorizado, servicio en loopback y puente a
la API administrativa restringida. Claves y estado OAuth del servidor permanecen
en el VPS. El diseño incluye lecturas de productos y borradores Qikink aislados;
no herramientas de publicación, pagos ni pedidos reales.

Una cuenta nueva de ChatGPT necesita volver a autorizar la conexión con la
identidad permitida. El código OAuth de esa rama restringe los clientes de
redirección; no se garantiza compatibilidad con cualquier cliente Codex.
Si las herramientas no aparecen, no inventes llamadas ni eludas el control de
acceso. Consulta la documentación de la rama y prueba primero `tbw_health` y una
lista pequeña de productos, sin crear borradores.

La decisión comercial fue dejar de buscar proveedores POD indios y mantener
CJ, Printify y Lulu, añadiendo Prodigi. No reactivar el trabajo de Qikink o
Printrove como siguiente paso implícito.

## Desarrollo y pruebas sin secretos

Clona el repositorio y crea una rama de trabajo desde `origin/main`. Usa Python
3.12, un virtualenv local e instala `server/requirements.txt`. No copies `.env`
desde el VPS ni ejecutes scripts de proveedores con credenciales locales.

Para cambios SEO, la suite concreta se puede ejecutar desde la raíz así, en un
clon limpio sin `server/.env` y con un virtualenv creado en `server/.venv`:

```bash
TBW_TEST_DIR=$(mktemp -d /tmp/tbw-tests.XXXXXX)
env -i PATH="$PATH" HOME="$TBW_TEST_DIR" \
  DATABASE_URL="sqlite:///$TBW_TEST_DIR/store.db" \
  PYTHONPYCACHEPREFIX="$TBW_TEST_DIR/pycache" \
  "$PWD/server/.venv/bin/python" -m unittest discover \
  -s server/tests -p 'test_product_schema.py' -v
```

La suite usa datos y clientes simulados. Para otros cambios, selecciona las
pruebas pertinentes tras revisar su aislamiento. La CI actual ejecuta
`test_prodigi_store`, `test_worldwide_shipping`, `test_paypal_recovery`,
`test_lulu_submission` y `test_product_schema` antes del despliegue.
Una modificación puramente documental necesita verificar enlaces y diff;
no requiere pagos, pedidos ni pruebas autenticadas.

## Despliegue: no confundirlo con guardar documentación

Consulta [el workflow](../.github/workflows/deploy.yml) y
[la guía de despliegue](../deploy/DEPLOY.md). Los pushes a `main` y la ejecución
manual del workflow activan despliegue. Además de copiar archivos y reiniciar
el servicio, el workflow actual ejecuta actualizaciones de catálogo y el
publicador de la lámina Prodigi revisada. No es un cambio exclusivamente estático.

La CI referencia secretos de GitHub Actions llamados `VPS_SSH_KEY` y
`VPS_KNOWN_HOSTS`. No se inspeccionaron sus valores ni su disponibilidad.
Por tanto, aún no se ha migrado todo el mecanismo de despliegue a un modelo
sin credenciales fuera del VPS. Si ese es el objetivo estricto del dueño,
hay que diseñar un despliegue iniciado desde el VPS y migrarlo por separado;
no borrar el acceso actual antes de contar con un reemplazo comprobado.

No ejecutes instaladores de primera instalación sobre servicios ya instalados.
No sobrescribas `.env`, bases, archivos de credenciales, drop-ins de systemd o
estado de pedidos. Revisa el diff y respalda lo que corresponda dentro del VPS
antes de una migración autorizada. No hay un rollback universal: copiar código
antiguo no revierte automáticamente cambios de base o publicaciones.

Lecturas públicas para comprobar disponibilidad, sin autenticar proveedores:

```bash
curl -fsS https://thebookswanderer.com/api/health
curl -fsS -o /dev/null https://thebookswanderer.com/sitemap.xml
curl -fsS -o /dev/null https://thebookswanderer.com/api/feeds/google-products.xml
```

## Contexto comercial y pendientes

- **Prodigi:** la lámina `moonlit-botanicals-phyllotaxis-art-print` se publicó
  con compra habilitada. Diseño botánico generado mediante código matemático;
  el texto público debe distinguirlo de un generador de imágenes IA. El código
  tuvo asistencia de IA. Ver [integración y recuperación de pedidos](../server/docs/prodigi/storefront.md).
  El bloqueo de pedidos del antiguo prototipo de cotizaciones no describe este
  checkout publicado. No crear pedidos para probarlo.
- **GMC:** el dueño compartió un correo confirmando retirada de la incidencia
  de información engañosa y reportó ausencia de productos bloqueados. La
  exportación del 22 de octubre tenía 142 artículos/variantes de 48 productos,
  pero no incluía columnas de aprobación o incidencias. No afirmar que la
  exportación prueba aprobación individual. Todos declaraban envío gratuito a
  EE. UU. e `identifier exists=no`: revisar coherencia por producto/proveedor.
- **Merchant API:** integración propuesta, todavía no implementada en este
  trabajo. Objetivo: estados, incidencias y rendimiento a través del MCP del
  VPS. Registrar proyecto y autorizar cuenta; guardar claves/tokens en el VPS.
  El scope OAuth documentado permite lectura/escritura, así que la limitación
  a consultas debe aplicarse también en las herramientas expuestas.
- **SEO:** exportación del 22 de octubre: 91 URLs indexadas y 74 excluidas en
  el gráfico hasta el día 15. Los detalles incluían rastreos del día 17. Había
  12 rastreadas sin indexar y 3 descubiertas sin indexar. Estas últimas eran
  `antique-animal-bookends`, `modern-bookends-pair` y `washable-kraft-book-cover`.
  Las comprobaciones públicas de esta conversación encontraron esas páginas
  accesibles e indexables. Próximo trabajo: enlaces internos, contenido y
  relaciones entre idiomas, sin asumir una causa ni garantizar indexación.
- **Analítica:** GSC mide búsqueda orgánica de Google. GMC puede desglosar
  fichas gratuitas y anuncios. Meta/TikTok requieren analítica de la web y UTM;
  no atribuir sus clics a GSC ni mezclar períodos o filtros de informes.

## Texto para iniciar otra sesión

> Trabajamos en The Books Wanderer. Lee AGENTS.md y docs/CONTINUITY.md antes de
> actuar. Las credenciales y operaciones de proveedores permanecen en el VPS;
> este entorno solo debe usar datos ficticios para desarrollo y pruebas.
> Comprueba qué accesos y herramientas están realmente disponibles. Retoma la
> tarea que te indique sobre una rama desde main y explica qué verificaste.
