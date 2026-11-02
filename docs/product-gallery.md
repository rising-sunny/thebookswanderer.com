# Galerías de productos desde el VPS

La página `/admin/product-media/` utiliza la sesión existente de `/admin/live`.
Su enlace «Imágenes de productos» aparece en el panel. Selecciona un producto,
elige hasta tres archivos PNG/JPEG/WebP y pulsa «Añadir a la galería».
El guardado se refleja inmediatamente en las fichas publicadas; un borrador
sigue siendo un borrador. No se modifican precios, variantes ni la portada.

Las imágenes de IA deben tener el aviso legible integrado dentro del archivo,
en español o inglés según su audiencia. El formulario exige confirmarlo: no
detecta IA ni verifica el texto mediante OCR. Las tres ilustraciones de la
mini biblioteca llevan ambos idiomas. Los archivos se guardan completos, sin
recortes ni eliminación de sus pies de nota. Envíos de fotos reales e imágenes
de IA deben hacerse por separado para registrar su origen correctamente.

Los límites son 8 MB y 24 megapíxeles por imagen, tres por envío y 24 en la
galería. El formato se comprueba a partir del contenido, no del nombre. Se
rechazan animaciones, SVG y archivos dañados. El nombre público se calcula
por SHA-256: repetir exactamente el archivo no crea otro elemento. Una
pestaña con una revisión antigua debe recargarse antes de guardar.

Las imágenes subidas se sirven bajo `assets/products/uploads/<id>/` en el VPS;
el despliegue actual copia archivos sin borrar este directorio. Sus respaldos
de galería quedan fuera de la web en `/var/lib/tbw-product-media/` (directorio
700, archivos 600). Cada respaldo registra el producto, la portada conservada,
la galería anterior, la propuesta nueva y el tipo declarado. Un respaldo es un
registro del intento de cambio; si falla la comparación de versiones no se
aplica a la base. «Quitar de la galería» solo desvincula una imagen añadida por
este gestor: conserva el archivo y nunca quita la foto principal ni fotos
originales del proveedor. La limpieza de archivos se realiza aparte.

`deploy/remote-setup.sh` crea esos directorios y añade una ubicación nginx
específica con 25 MB de cuerpo para el formulario. No requiere nuevas claves
ni configurar un proveedor. El panel administra archivos existentes; no genera
imágenes mediante una API de IA. La generación autónoma sería otro servicio.

## Las tres imágenes de la mini biblioteca

Se generaron con las dos referencias que aportó el dueño, con aviso visible
en español e inglés. Los WebP conservan la resolución completa (1254 × 1254)
y el pie de nota, y se incluyen con SHA-256 en
`assets/products/miniature-library-ai/manifest.json`.

Después de fusionar y terminar el despliegue, ejecuta en el VPS:

```sh
cd /var/www/thebookswanderer.com/server
runuser -u www-data -- .venv/bin/python scripts/install_mini_library_ai_images.py
runuser -u www-data -- .venv/bin/python scripts/install_mini_library_ai_images.py --apply
```

La primera orden muestra la vista previa; la segunda añade las imágenes.
El instalador comprueba el ID 73, slug, PID CJ y estado publicado, además de
los hashes de los archivos. No compra, importa ni publica productos, no cambia
sus precios ni envía mensajes a redes sociales. La repetición es idempotente.
No importa archivos de producción al entorno de desarrollo.

Para restaurar una galería, el administrador del VPS debe revisar el respaldo
privado y aplicar `before_gallery_json` solamente si la galería actual aún
coincide con `after_gallery_json`. No se restauran bases completas ni se
sobrescriben cambios posteriores de otros productos.
