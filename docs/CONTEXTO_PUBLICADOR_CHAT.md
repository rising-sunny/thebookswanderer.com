# The Books Wanderer — contexto para continuar en el chat con el entorno

Fecha: 19 de octubre de 2026. Idioma del usuario: español.

## Petición actual

Quiero pedir publicaciones de imagen para Facebook e Instagram directamente
desde este chat, sin ejecutar comandos en Termux cada vez. El publicador ya
está instalado en mi VPS. Ahora hay que verificar que el entorno conectado a
este nuevo chat tenga el secreto correcto y pueda acceder al servicio por HTTPS.

**Primero verifica la conexión con una consulta de lectura. No publiques un
post nuevo durante la configuración ni repitas el que ya está publicado.**

## Preferencias y límites

- Usa el checkout existente `/workspace/thebookswanderer.com`, si está disponible.
- La tienda en la VPS está en `/var/www/thebookswanderer.com`.
- Accedo a la VPS como root desde Termux. No usar nano; si necesito intervenir,
  dar un único comando autocontenido por paso y explicar qué hará.
- Ya no utilizo Tailscale. Para este publicador se diseñó acceso HTTPS público
  con autenticación; no requiere VPN ni SSH desde el chat.
- No mostrar claves, tokens, archivos .env ni volcados del entorno.
- No pedir que pegue credenciales en el chat. Deben ir en la bóveda del entorno.
- No modificar la tienda ni su automatización de reels para probar el acceso.

## Estado confirmado en producción

La VPS se identifica como `ubuntu-4gb-hil-1`.

- Python: `/var/www/thebookswanderer.com/server/.venv/bin/python`.
- Tiene FastAPI, Uvicorn, httpx y python-dotenv; no tiene el paquete mcp.
- Servicio de la tienda: `thebookswanderer.service`.
- Nginx: `/etc/nginx/sites-available/thebookswanderer.com`, enlazado en sites-enabled.
- El publicador utiliza una API HTTP autenticada. **No es un servidor MCP** ni
  se conecta automáticamente como app a cualquier chat.

Ejecuté correctamente este instalador, fijado a un commit de GitHub:

```bash
curl -fL 'https://raw.githubusercontent.com/rising-sunny/thebookswanderer.com/9a313b3f8d3e90eb1d83ff6f52b7133b9ba4ae90/deploy/install-social-publisher.py' -o /tmp/install-social-publisher.py && /var/www/thebookswanderer.com/server/.venv/bin/python /tmp/install-social-publisher.py
```

El instalador pasó sus 13 pruebas sin red y confirmó:

```text
Instalado: https://thebookswanderer.com/api/social-publisher/health
Autenticación local comprobada: con clave 200, sin clave 401.
No se publicaron posts. La tienda y su .env no se modificaron ni reiniciaron.
Respaldo Nginx y servicio: /var/backups/tbw-social-publisher/20261019T202820303330Z
```

Esto demuestra instalación y autenticación local; **todavía no confirma acceso
HTTPS autenticado desde el entorno del chat**. No reinstalar ni cambiar claves
por defecto.

## Clave del publicador

Durante la instalación introduje una clave nueva de al menos 32 caracteres,
dos veces y sin mostrarse en pantalla. El instalador no la generó ni imprimió.
Después indiqué que ya la había guardado en el entorno.

Configuración necesaria en el entorno correcto:

- Tipo: secreto de red.
- Nombre y variable: `SOCIAL_PUBLISHER_KEY`.
- Valor: exactamente la clave introducida en la VPS.
- Dominio autorizado: `thebookswanderer.com`.
- Cambios publicados/aplicados al entorno adjunto a este chat.

`SECRET_KEY` ya existente es otra credencial; no sustituye a
`SOCIAL_PUBLISHER_KEY`. No usar el token de Facebook como clave del publicador.

## Bloqueo observado en el chat anterior

La última consulta de `cloud_environment.environment_status` mostraba una
revisión 90, entorno en ejecución y política de red aplicada. Sin embargo,
en secretos solo aparecía `SECRET_KEY`; **no aparecía SOCIAL_PUBLISHER_KEY**.
La variable tampoco estaba presente en ese proceso de ejecución.

Las solicitudes normales por el proxy a
`https://thebookswanderer.com/api/social-publisher/health` fallaban con
`ProxyError: 503 Service Unavailable`, antes de poder comprobar autenticación.
El snapshot `/etc/codex/network-policy.json` conservaba
`vpn_configured: true`, aunque ya no uso Tailscale. Esto no demuestra por sí
solo que la VPN sea la causa del 503.

No reutilizar ese diagnóstico como estado actual: consultar el entorno de este
nuevo chat. No sortear el proxy, cambiar rutas, desactivar TLS ni modificar el
snapshot de política para intentar obtener acceso.

Se invocó `$cloud-environment-onboarding:setup`, pero esa habilidad no estaba
disponible tras buscar en los catálogos de habilidades cloud y executor.
Sí estaba disponible `cloud-environment:cloud-environment-runtime` para consultar
estado y diagnóstico; no permitía editar la configuración del entorno.

## Pasos para continuar ahora

1. Leer la habilidad de runtime disponible y consultar el estado actual del
   entorno. Revisar secretos, dominios permitidos y disponibilidad observada.
2. Confirmar `SOCIAL_PUBLISHER_KEY` con estado ready y observaciones actuales,
   además de la política de red aplicada. No imprimir su valor.
3. Consultar únicamente GET /health, usando el proxy y CA heredados y la
   cabecera `Authorization: Bearer <SOCIAL_PUBLISHER_KEY>`.
4. Un HTTP 200 con `ready: true` confirma acceso autenticado al publicador.
   Este endpoint verifica configuración local; no prueba una nueva publicación
   ni la vigencia remota del token de Meta.
5. Si falta el secreto, comprobar que estoy editando el mismo entorno adjunto
   al chat y que sus cambios se publicaron. No pedirme volver a instalar la VPS.
6. Si persiste un 503 del proxy, diagnosticar la conectividad del entorno por
   el flujo admitido. Revisar la configuración VPN antigua sin asumir causalidad.
7. Informar con precisión de qué está confirmado y qué sigue pendiente.

Ejemplo de consulta de lectura, cuando la variable esté disponible:

```python
import os
import httpx

key = os.environ.get("SOCIAL_PUBLISHER_KEY")
if not key:
    raise SystemExit("SOCIAL_PUBLISHER_KEY no está disponible en este proceso.")
with httpx.Client(timeout=20, follow_redirects=False) as client:
    response = client.get(
        "https://thebookswanderer.com/api/social-publisher/health",
        headers={"Authorization": "Bearer " + key},
    )
    print("HTTP:", response.status_code)
    if response.status_code == 200:
        data = response.json()
        print({k: data.get(k) for k in ("service", "ready", "format", "networks")})
```

Una variable de secreto de red puede ser un placeholder del proxy. No asumir
que está mal solo por eso: usar la vía HTTP configurada y comprobar el resultado.

## API instalada

Base: `https://thebookswanderer.com/api/social-publisher`.
Todas las rutas requieren la misma cabecera Bearer.

- `GET /health`: estado local; no publica ni llama a Meta.
- `POST /drafts`: prepara un borrador, sin publicar. JSON estricto:
  `campaign`, `slug`, `facebook_caption`, `instagram_caption`.
- `GET /jobs/{campaign}`: consulta contenido guardado y resultados.
- `POST /jobs/{campaign}/publish`: publica explícitamente el borrador en ambas
  redes como foto; normalmente devuelve 202. Consultar el job para los enlaces.

Cada post nuevo necesita una referencia campaign única. El borrador valida
producto e imagen JPEG pública de la propia tienda. Antes de publicar se
comprueba que la imagen siga igual y que las cuentas Meta sean las previstas.
Repetir una solicitud con la misma referencia no debe crear duplicados.
Una escritura incierta o un reinicio durante el envío requiere revisión;
**no borrar el registro ni inventar otra referencia para reintentar**.

Alcance actual: una foto JPEG existente del producto, publicación inmediata en
las dos redes. No incluye carruseles, subida de imágenes nuevas, programación
ni selección de una sola red. La automatización diaria de reels sigue activa.

## Ubicaciones del servicio en la VPS

- Servicio: `tbw-social-publisher.service`, usuario www-data, un worker.
- Escucha solo en `127.0.0.1:8877`, publicado por Nginx mediante HTTPS.
- Código: `/opt/tbw-social-publisher/`.
- Clave: `/etc/tbw-social-publisher/key`; no mostrar su contenido.
- Copia mínima de credenciales Meta: `/etc/tbw-social-publisher/meta.env`;
  permanece en la misma VPS. No mostrarla. Reinstalar solo si hace falta
  actualizar esa copia tras una rotación de token confirmada.
- Registros persistentes: `/var/lib/tbw-social-publisher/`.
- Snippet Nginx: `/etc/nginx/snippets/tbw-social-publisher.conf`.

Código y documentación en el borrador de PR:
https://github.com/rising-sunny/thebookswanderer.com/pull/90

Branch: `codex/static-social-posts`. No se fusionó main durante este trabajo.

## Cuentas y publicación ya confirmada: NO REPETIR

- Facebook: The Books Wanderer, ID `1200587819810293`.
- Instagram: `@thebooks.wanderer`, ID `17841443635177157`.
- El token Page se comprobó válido en la VPS y tenía permisos de publicación
  para Facebook e Instagram. Los valores nunca se compartieron en chat.

Ya se publicó correctamente una foto de la tote Reading Society en ambas redes:

- Campaign anterior: `reading_society_tote_photo_20261019`.
- Facebook: https://www.facebook.com/1200587819810293_122120661771418245
- Instagram: https://www.instagram.com/p/DesEcPUIA9B/
- Media ID de Instagram: `18412486147093297`; tipo confirmado: IMAGE.

Ese post se publicó con un CLI anterior, cuyo registro está en
`/var/www/thebookswanderer.com/server/data/static-social-posts/`.
El nuevo servicio usa un directorio distinto: no intentar migrar/recrear ese
post para probar la conexión.

## Antecedente Qikink, fuera del paso actual

La conversación original trataba la integración Qikink Sandbox. Las credenciales
Sandbox están en la VPS. Se crearon únicamente pedidos de prueba confirmados:

- Pedido `24616032`, referencia `tbw_9ba7265277`.
- Pedido con impresión `24620736`, referencia `tbw_print001`.

Las credenciales LIVE se solicitaron a Qikink y quedaban pendientes de aprobación;
no asumir que ya llegaron. No cargar saldo ni crear pedidos reales.
El código Sandbox está en el borrador de PR #89:
https://github.com/rising-sunny/thebookswanderer.com/pull/89

La tarea actual es terminar el acceso al publicador social, no modificar Qikink.
