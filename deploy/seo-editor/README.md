# Piloto editorial autónomo del VPS

Servicio independiente de Codex, de GitHub Actions y del proceso de la tienda.
Python 3.12 estándar, DeepSeek `deepseek-flash`, una ejecución los lunes a las
10:00 America/Santiago, máximo cuatro intentos editoriales por mes calendario.
El propietario autorizó publicación automática tras controles y US$5/mes.

## Qué hace

1. Lee únicamente el resumen exportado de GSC, no la clave de Google ni la base
   de clientes/pedidos. Si tiene más de nueve días, se detiene.
2. Lee contenido público del árbol local de la web: títulos de guías y extractos de
   guías/retos, sin scripts. Envía estos datos públicos y consultas agregadas a
   DeepSeek. No hace investigación web externa ni consulta proveedores.
3. Propone cuatro temas mensuales alternando inglés/español, evita títulos
   similares y reutiliza el plan durante el mes.
4. Genera un artículo con referencias internas a las fuentes suministradas;
   valida forma, longitud, fuentes, repeticiones, marcado y copia literal.
5. Hace una segunda llamada independiente al modelo para revisión editorial,
   factual y de idioma; solo publica con aprobación explícita y cero hallazgos.
6. Comprueba que las fuentes citadas respondan HTTP 200 sin redirecciones.
   Publica un HTML escapado en un directorio nuevo `guides/editor-<slug>/`.
   No sobrescribe guías existentes. Crea un índice propio enlazando artículos.
   El sitemap dinámico de la tienda descubre los directorios de guías; el cron
   IndexNow ya existente notificará cambios al leerlo. Recepción no garantiza
   indexación. No modifica robots, nginx, la tienda ni el MCP.
7. Conserva borradores, revisión, resumen usado, estados y reservas en privado.
   Actualiza `performance.json` y un histórico semanal con las métricas disponibles
   para artículos publicados, incluso cuando alcanzó la cuota mensual. El resumen
   GSC solo exporta diez páginas: una URL ausente se marca como desconocida, nunca
   cero. Las ventanas de 28 días se solapan; no prueba efectos causales.

Los controles automáticos no garantizan veracidad, originalidad ni resultados
SEO. Una revisión por el mismo modelo puede repetir un error. Esta primera
versión se limita a consejos de lectura basados en el contenido existente;
no crea comparativas de productos, pruebas propias, precios ni afirmaciones
sobre disponibilidad/envíos. No envía mensajes ni crea backlinks externos.

## Coste y fallos

Máximo nueve llamadas por mes (un plan, cuatro artículos, cuatro revisiones).
Cada llamada reserva al menos US$0,25 o una estimación conservadora mayor,
utilizando bytes UTF-8 de entrada y límite de salida con tarifas pico sin caché.
La suma reservada nunca supera US$5 con la configuración suministrada; no se
reembolsa la reserva aunque el consumo observado sea menor. Las peticiones
fallidas o ambiguas tampoco se repiten automáticamente. Una interrupción puede
consumir un intento sin producir un artículo: cuatro publicaciones no están
garantizadas. No hay reintentos de pago ilimitados ni herramientas web de pago.

Es un límite estimado del worker bajo las tarifas configuradas, no un tope de
facturación de la cuenta DeepSeek. Las tarifas del proveedor pueden cambiar;
utiliza una clave/proyecto dedicado y mantén un saldo de como máximo US$5 sin
recargas automáticas durante el piloto. Los precios deben revisarse en
https://api-docs.deepseek.com/quick_start/pricing/ (verificados el 1-11-2026:
entrada pico US$0,30/M y salida pico US$1,20/M para `deepseek-flash`).
Contrato de API: https://api-docs.deepseek.com/api/create-chat-completion/.

El proceso toma un bloqueo exclusivo. Reserva cada llamada antes de enviarla y
cada semana antes de generar; errores quedan retenidos. Si cae entre escribir
el archivo y registrar la publicación, el siguiente proceso comprueba su hash
antes de reconciliarlo. No vuelve a generar o sobrescribir automáticamente.

## Instalación en el VPS

La fusión de este directorio NO instala el servicio: el despliegue habitual no
copia `deploy/seo-editor/`. Descargar este directorio desde la revisión aprobada
en un checkout temporal del VPS, conservando los secretos exclusivamente allí.
No usar un checkout antiguo para sustituir el MCP instalado.

```sh
sudo sh deploy/seo-editor/install.sh
```

El instalador no activa el timer, no genera artículos y no llama a DeepSeek.
Una actualización preserva configuración, clave y estado. Si el usuario del
servicio no puede leer `/var/lib/tbw-seo-reports/latest.json`, concede acceso de
lectura al directorio y a las futuras exportaciones (grupo o ACL heredada), sin
abrir el informe completo privado de `/var/lib/tbw-seo-agent/`.

Crear la clave directamente en una terminal SSH del VPS sin mostrarla ni ponerla
en argumentos, historial, chat o repositorio:

```sh
sudo bash -c 'umask 077; read -r -s -p "DeepSeek API key: " TBW_DS_KEY; printf "\n"; printf "%s" "$TBW_DS_KEY" > /etc/tbw-seo-editor/deepseek-key; unset TBW_DS_KEY'
```

Editar `/etc/tbw-seo-editor/config.json` en el VPS y cambiar `enabled` a `true`
cuando se hayan comprobado modelo, presupuesto, permisos y lectura del informe.
Mantener el archivo root-owned y solo editable por root. La clave debe ser
root-owned, modo 600. El directorio `/etc/tbw-seo-editor` utiliza modo 711
para que el worker lea `config.json` (644) sin poder listar la carpeta ni leer
la clave. Para corregir una instalación inicial con modo 700, ejecutar
`chmod 711 /etc/tbw-seo-editor`. systemd la entrega al worker mediante LoadCredential;
no se comparte con el servicio de la tienda.

Primera ejecución (puede consumir API y publicar un artículo):

```sh
sudo systemctl start tbw-seo-editor.service
sudo systemctl status tbw-seo-editor.service --no-pager
sudo journalctl -u tbw-seo-editor.service -n 10 --no-pager
```

Revisar la URL devuelta y comprobar que el sitemap la contiene. Después:

```sh
sudo systemctl enable --now tbw-seo-editor.timer
sudo systemctl list-timers tbw-seo-editor.timer --no-pager
sudo -u tbw-editor python3 /opt/tbw-seo-editor/editor.py --status
```

Los estados/logs solo muestran códigos, URLs, semanas y reservas; no imprime
claves, cabeceras, respuestas de errores de API o datos de clientes. Los
borradores completos quedan en `/var/lib/tbw-seo-editor/`, fuera de la web.

## Parada y mantenimiento

`sudo systemctl disable --now tbw-seo-editor.timer` detiene futuras ejecuciones;
si hay una activa, detener también `tbw-seo-editor.service`. Poner `enabled=false`
impide nuevas llamadas en ejecuciones manuales. Los artículos ya publicados
permanecen. Antes de retirar uno, conservar su copia privada y gestionar la URL;
no borrar la base para reiniciar cuotas. No tiene permiso para escribir la base
de la tienda ni para modificar guías no generadas mediante su lógica.

La operación ordinaria no necesita un chat ni GitHub Actions. Verificar el
journal/timer y el estado es responsabilidad operativa del dueño; esta versión
no manda alertas por correo ni agrega un panel MCP. El reporte guardado con cada
artículo permite comparar posteriormente GSC; no une pedidos con artículos ni
promete ventas. Los archivos generados no están en Git: incluir `guides/editor-*`
en los backups del VPS y preservarlos si se cambia a un despliegue con borrado.

## Pruebas

`python3 -m unittest discover -s deploy/seo-editor -p 'test_*.py' -v`

Solo temporales, fuentes ficticias y DeepSeek simulado. No requieren credencial,
red, datos de producción ni dependencias de la tienda.
