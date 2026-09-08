# Anuncio 01 — The Books Wanderer

**Estado:** creado en `PAUSED`. Activar lo decide el dueño.
**Fecha:** 2026-08-02
**Cuenta:** `1636887674121801` (Stunning Revelations 3, **CLP**)
**Página:** `1200587819810293`
**Píxel:** `907494619068513`

| Objeto | ID |
|---|---|
| Campaña | `120249986543080256` |
| Ad set | `120249986544110256` |
| Creatividad | `911872478014927` |
| Anuncio | `120249986555000256` |
| Vídeo en la biblioteca | `1578051987187139` |

Presupuesto **CBO a nivel de campaña**: `daily_budget=5000`. En CLP no hay
subunidad, así que 5000 son 5.000 pesos, no 50.

Vídeo servido desde `assets/ad/tbw-ad-01.mp4`; regenerable con
`server/scripts/build_ad_video.py`.

---

## 1. Público objetivo

### País: solo Reino Unido

De los 30 destinos que CJ puede servir, GB gana por tres razones medidas, no intuidas:

| | |
|---|---|
| **Envío** | $4.20, uno de los más baratos del catálogo |
| **Plazo** | 4-9 días — el grupo rápido. Chile, pese a ser el país del dueño, tarda 15-45 |
| **Demanda probada** | La biblioteca de anuncios de Meta muestra competencia activa vendiendo este producto exacto ahí |

La evidencia de demanda es lo que decanta: *Myhawaiianshirts* corre **seis variantes creativas** de un anuncio de marcapáginas de gatos en GB, y *Brightonuk-E* anuncia un "Hollow Cat Metal Bookmark" — el mismo producto que el catálogo de TBW. Nadie mantiene seis creatividades vivas de algo que no convierte.

**Por qué no España**, que era la alternativa: CPMs más baratos y copy en el idioma nativo del dueño, pero cero evidencia de que el mercado exista. Se aprende más rápido, a ciegas.

**Por qué no Estados Unidos:** envío más caro ($5.97), plazo más largo y los CPM más altos del mundo. Con 5.000 CLP/día el presupuesto se evapora antes de aprender nada.

**Ventaja regulatoria de GB:** no es UE, así que el anuncio no necesita los campos `dsa_beneficiary` / `dsa_payor` que la Digital Services Act exige para targeting europeo.

> ⚠️ **Corregido el 2026-08-25 — esto es FALSO.** Ads Manager exige *Advertiser* y *Payer* también para un ad set solo-GB: el panel de revisión bloquea con "Please add: Advertiser (selected locations)" / "Please add: Payer (selected locations)". La API los acepta sin quejarse al crear y `ads_get_errors` devuelve vacío, así que el fallo **solo aparece al revisar en Ads Manager**. Ver Anuncio 04.

### Edad y género: mujeres, 25-54

La categoría de accesorios de lectura y regalo es abrumadoramente femenina. El tramo 18-24 domina BookTok pero convierte peor en compra; 25-54 concentra el poder adquisitivo.

Con Advantage+ Audience activo (por defecto), Meta trata estos valores como **sugerencia, no como límite duro**, y ampliará si encuentra mejores resultados fuera. Es lo deseable con presupuesto pequeño.

### Intereses: ninguno, deliberadamente

Aquí se corrigió el plan inicial. La documentación de la API es explícita:

> *"Do NOT invent interest IDs. Omit interests and use broad targeting via geo_locations (recommended)"*

Los IDs de intereses son números de 13-16 dígitos del Targeting Search API. Sin IDs verificados, inventarlos hace que la llamada falle o segmente algo equivocado.

Y con **5.000 CLP/día (~USD 5)** la segmentación amplia es además la mejor opción técnica: cada capa de filtro encarece el CPM y ralentiza el aprendizaje. Menos de 1.000 impresiones diarias no dan para trocear un público.

### Idioma: sin restricción

En Reino Unido, filtrar por inglés es redundante y solo recorta alcance.

---

## 2. Objetivo: tráfico, no ventas

El píxel tiene ~23 PageViews y **cero compras**. Meta necesita del orden de 50 conversiones semanales para salir de la fase de aprendizaje; pedirle compras con ese historial es pedirle que adivine, y el presupuesto se va explorando.

- **Objetivo de campaña:** `OUTCOME_TRAFFIC`
- **Optimización:** `LANDING_PAGE_VIEWS` — cuenta a quien carga la página, no a quien hace clic y se va
- **Facturación:** por impresiones

Cuando haya ventas reales y el CAPI esté alimentando importes, se migra a `OFFSITE_CONVERSIONS`.

---

## 3. Creatividad: vídeo

Generado con ffmpeg desde el catálogo real, **1080x1350 (4:5)**, el formato que Facebook recomienda para el feed y que ocupa más pantalla en móvil que un cuadrado.

Estructura: portada de marca → seis productos con zoom lento, nombre y precio → cierre con la URL.

Los seis: marcapáginas gatito, mariposas de papel, sujetalibros de madera, funda Kindle, lámpara de libros apilados y registro de lectura. Mezcla de $7.99 y $9.99, y variedad visual suficiente para que no parezca el mismo objeto seis veces.

### Copy

**Texto principal:**
> Small things that make reading a ritual.
>
> Bookmarks that survive a bag. A holder that keeps the page open while your other hand holds the coffee. A sleeve that doesn't fight the Kindle inside it.
>
> We keep the shelf small on purpose — every piece is picked by hand.
>
> Shipping is priced per destination and the real delivery estimate shows before you buy. No flat rate, no surprises at checkout.

**Titular:** Reading accessories, from $7.99
**Descripción:** Free of clutter. Full of character.
**Botón:** SHOP_NOW

El copy no promete envío gratis ni plazos que no se cumplen: son exactamente las afirmaciones que hubo que retirar del sitio, y repetirlas en un anuncio es peor, porque Meta las revisa.

---

## 4. Qué falta antes de activar

- [ ] Método de pago verificado en la cuenta (estuvo desactivada por facturación)
- [ ] Más publicaciones en la Página — hay dos
- [ ] Revisar el vídeo entero antes de que lo vea nadie
- [x] 5.000 CLP/día aceptado por la API sin queja de mínimo

**Nunca activar desde el panel de sugerencias de Ads Manager**: su slider viene por defecto en **$10.000/día**.

## 5. Notas de la implementación

`ads_creative_upload_video` del MCP **no está habilitada todavía para esta
cuenta** — devuelve "gradually rolled out". El vídeo se subió por la Graph API
a `/act_<id>/advideos`, que el token de usuario ya podía usar gracias a
`ads_management`. Si en el futuro la herramienta se habilita, ambas vías valen.

`promoted_object` con solo `pixel_id` **es rechazado** en campañas de tráfico
(`error_subcode 1885014`). Para `OUTCOME_TRAFFIC` hay que omitirlo; solo se
vuelve obligatorio al migrar a `OFFSITE_CONVERSIONS`.

**Nunca activar desde el panel de sugerencias de Ads Manager**: su slider viene por defecto en **$10.000/día**.

---

# Anuncio 02 — Estados Unidos

**Estado:** creado en `PAUSED` el 2026-08-02.

| Objeto | ID |
|---|---|
| Campaña | `120249991557130256` |
| Ad set | `120249991559160256` |
| Anuncio | `120249991560650256` |
| Creatividad | `911872478014927` — **la misma que GB** |

Campaña separada, no un ad set más dentro de la de GB. Con CBO, añadirlo allí
habría partido los mismos 5.000 CLP entre dos países; así cada mercado tiene su
propio presupuesto y su propio aprendizaje.

## Misma creatividad, a propósito

Reutiliza el vídeo y el copy de GB sin un solo cambio. Es lo que convierte esto
en una comparación limpia: **la única variable que cambia es el país**. Si el
copy también cambiara, un resultado distinto no diría si fue el mercado o el
texto.

Los precios en el vídeo van en dólares, así que en EE.UU. se leen nativos.

## Economía, frente a Reino Unido

| | GB | US |
|---|---|---|
| Envío | $4.20 | **$5.97** |
| Plazo | 4-9 días | 5-11 días |
| Ticket | $12.19 | $13.96 |
| Margen de contribución | ~$6.28 | **~$6.45** |
| CPM relativo | medio | **el más alto del mundo** |

El margen por pedido es ligeramente mejor en EE.UU. porque el recargo de envío
suma más en términos absolutos. Lo que empeora es el coste de llegar: los CPM
estadounidenses son los más caros que existen, así que con el mismo presupuesto
se compran bastantes menos impresiones.

**La pregunta que responde este test:** ¿compensa el margen algo mayor el coste
de adquisición mucho mayor? Solo se sabe midiendo.

## Aviso de gasto

5.000 CLP/día **adicionales**. Con las dos campañas activas el gasto diario pasa
de ~5 a ~10,5 USD.

---

# Anuncio 03 — España

**Estado:** creado en `PAUSED` el 2026-08-02.

| Objeto | ID |
|---|---|
| Campaña | `120249991722490256` |
| Ad set | `120249991725050256` |
| Anuncio | `120249991736830256` |
| Creatividad | `27719895547666761` — **propia, en español** |
| Vídeo | `2039858179963490` |

Único de los tres con creatividad distinta. GB y US comparten la inglesa para
que la comparación entre ellos sea limpia; España cambia el idioma porque ahí
está justamente su ventaja.

## Por qué España

El CPC no sale solo de un CPM barato: `CPC = CPM ÷ (CTR × 1000)`. España no es
el CPM más bajo de los destinos rápidos — Polonia lo es, a $3.65 de envío — pero
es el único donde el dueño escribe el copy en su idioma nativo sin coste ni
traductor. Un anuncio en inglés a Polonia tiene un CTR malo que se come la
ventaja del CPM.

Envío $4.73, plazo 4-9 días: mismo grupo rápido que Reino Unido.

## Traducción: solo portada y cierre

Los nombres de producto y los precios se quedan en inglés. Es lo que el
comprador va a encontrar al aterrizar, y traducirlos en el vídeo crearía un
desajuste peor que dejarlos.

Los acentos van escritos: `páginas`, `pequeños`, `Envío`. Un primer render los
omitió por precaución de codificación, pero drawtext con DejaVu los pinta sin
problema — y "pequenos" delata el texto como generado, que es exactamente lo
contrario de lo que se busca al anunciarse en el idioma del mercado.

## El riesgo que hay que medir

**La web está íntegramente en inglés.** El anuncio en español gana el clic y
luego aterriza en un sitio que el visitante quizá no lee con comodidad. Por eso
el copy lo dice explícitamente al final — *"La tienda está en inglés"* — en vez
de dejar que lo descubra tras pagar el clic.

Si España da buen CTR y mala conversión, esa es la causa más probable, y la
solución sería traducir el sitio, no cambiar el anuncio.

## DSA

España es UE, así que el ad set lleva `dsa_beneficiary` y `dsa_payor`
declarados. GB y US no los necesitan.

---

# Anuncio 04 — Butterfly Metal Bookmark (producto único)

**Estado:** creado en `PAUSED` el 2026-08-25. Activar lo decide el dueño.
**Cuenta:** `1696378237957660` (Stunning Revelations, **CLP**) — **no** la 3 de los anuncios 01-03.
**Página:** `1200587819810293` (The Books Wanderer)
**Píxel:** ninguno asignado a esta cuenta (ver §Riesgos)

| Objeto | ID |
|---|---|
| Campaña | `120249021202600244` |
| Ad set | `120249021205760244` |
| Creatividad | `1430211368959939` |
| Anuncio | `120249021270250244` |
| Vídeo en la biblioteca | `2305525400183827` |
| Hash de miniatura | `e6335cd07e1dda0890fab749815014f9` |

Presupuesto **CBO a nivel de campaña**: `daily_budget=5000` → 5.000 CLP, igual que 01-03.

## Cambio de cuenta

Los anuncios 01-03 viven en `1636887674121801` (Stunning Revelations 3), hoy
`UNSETTLED` y `is_queryable=false`. La `1696378237957660` es la única del portfolio
que está **ACTIVE + queryable + con método de pago**, así que es donde se puede
publicar. Ambas cuelgan del mismo BM `614062214558484`, por lo que la Página de TBW
sigue disponible: `ads_get_ad_account_pages` solo devuelve "Stunning Revelations",
pero `ads_get_pages_for_business` sí lista la de TBW, y la creatividad la acepta.

## Objetivo: tráfico, otra vez — y por un motivo nuevo

`OUTCOME_TRAFFIC` + `LANDING_PAGE_VIEWS`, facturación por impresiones.

En 01-03 la razón era el historial vacío del píxel. Aquí se suma otra: **el píxel de
TBW (`907494619068513`) no está asignado a esta cuenta**. `ads_get_datasets` sobre
`1696378237957660` solo devuelve `1357584955492947` ("Stunning Revelations 2"), que
es de otra marca y cuyo último evento es de 2026-03-08. Optimizar a conversiones aquí
mediría el funnel equivocado.

Sigue valiendo la nota de implementación de 01: `promoted_object` se omite en tráfico.

## Público

Reino Unido, mujeres, sin intereses. Idéntico a 01 salvo por la edad (ver abajo). Con Advantage+ Audience activo la API movió la edad a
`targeting_automation.advantage_audience` como *sugerencia*; el género sí quedó como
filtro duro (`genders:[2]`).

## Creatividad

Vídeo aportado por el dueño: `WASK-AI-CREATIVE-4310.mp4`, **generado con IA**,
720x1280 (9:16), 10,08 s, h264.

`ads_creative_upload_media` **no acepta vídeo local** — solo imágenes. El vídeo se
sirve desde el propio sitio y Meta lo descarga por URL, igual que en 01:

- `https://thebookswanderer.com/assets/ad/tbw-ad-02.mp4`
- `https://thebookswanderer.com/assets/ad/tbw-ad-02-thumb.jpg` (fotograma en t=1,5 s, ffmpeg)

A diferencia de lo documentado en 01, en esta cuenta la herramienta del MCP **sí está
habilitada**: no hizo falta la Graph API.

### Copy

**Texto principal:**
> A bookmark that earns its place in the book.
>
> Cut from metal, not card — so it won't bend, crease or disappear into the sofa.
> Five butterflies climb the spine, and the tassel keeps it easy to find.
>
> $15.99, with shipping already inside the price. Nothing added at checkout.

**Titular:** Butterfly Metal Bookmark — $15.99
**Descripción:** Free UK shipping, priced in.
**Botón:** SHOP_NOW

El envío gratis sí es afirmable ahora: el JSON-LD del producto declara
`shippingRate: 0 USD` para GB. Es lo que cambió desde 01, donde el copy tenía que
evitarlo.

## Riesgos abiertos

- **Instagram sin confirmar.** `ads_get_ig_accounts` responde "gradually rolled out"
  para esta cuenta, así que la creatividad se creó sin `instagram_user_id`. Aun así
  `ads_get_creatives` devuelve `effective_instagram_media_id`
  (`17965165857161779`), lo que indica que Meta sí generó el objeto de IG —
  probablemente vía la cuenta de Instagram conectada a la Página. **No está
  verificado** que entregue en Reels/Stories; confirmar en Ads Manager antes de
  activar, porque el vídeo es 9:16 y ahí es donde mejor rinde.
- **Precio en USD a público británico.** Mismo desajuste asumido en 01.
- **Defectos del vídeo:** el rótulo "Elevate your reading experience" aparece
  duplicado (arriba y abajo) y el texto del libro es ilegible, artefacto típico de
  generación por IA.

## Declaración de contenido generado con IA

`self_ai_disclosure` se fijó en **`OPT_IN`** (decisión del dueño, 2026-08-25).

El campo es inmutable: no existe herramienta que lo cambie después de crear la
creatividad, y `ads_creative_update` solo toca nombre, estado y etiquetas. Por eso
hubo que **crear una creatividad nueva** (`1430211368959939`) y un **anuncio nuevo**
(`120249021270250244`). Los originales sin declarar — creatividad `1410742447599568`
y anuncio `120249021211420244` — se borraron para que el ad set no quedara con dos
anuncios, de los cuales uno habría corrido sin declaración.

**Límite de verificación:** `ads_get_creatives` no expone `self_ai_disclosure` entre
sus campos, así que el valor guardado no se puede leer de vuelta por MCP. Lo que
consta es que la creación con `OPT_IN` fue aceptada sin error. Para confirmarlo de
verdad hay que mirarlo en Ads Manager.

## DSA: obligatorio en GB, al contrario de lo documentado en el Anuncio 01

`dsa_beneficiary` y `dsa_payor` se fijaron en **"The Books Wanderer"** (decisión del
dueño, 2026-08-25), vía `ads_update_entity` sobre el ad set.

Lo importante para futuras campañas: **la API no avisa**. `ads_create_ad_set` aceptó el
ad set sin ellos y `ads_get_errors` devolvió `[]` en los tres niveles incluso mientras
Ads Manager mostraba el bloqueo en rojo. La única forma de detectarlo fue abrir el panel
de revisión. Conviene declararlos siempre, sea o no UE.

`dsa_beneficiary` / `dsa_payor` tampoco se pueden **leer** de vuelta: no están entre los
campos soportados de `ads_get_ad_entities` a nivel de ad set. Se confirman en Ads Manager.

## La edad no se aplicó: Advantage+ la absorbió entera

El ad set se creó pidiendo 25-54. La respuesta de creación los movió a
`targeting_automation.advantage_audience.age_min_suggestion / age_max_suggestion`, como
advierte la documentación de la herramienta. Pero al releer el ad set ya publicado, el
targeting guardado es:

```
age_min: 18, age_max: 65, targeting_automation: {advantage_audience: 1}
```

Las *sugerencias* desaparecieron. Ads Manager lo confirma: "Minimum age 18",
"Age suggestion 18 – 65+". Es decir, **el tramo 25-54 no está actuando ni como
sugerencia**; el ad set entrega a mujeres de 18 en adelante.

Decisión del dueño: dejarlo amplio, que es lo que el propio Anuncio 01 defiende para
presupuesto pequeño, y **renombrar el ad set** para que no describa algo que no hace:

`TBW | GB | Mujeres 25-54 | Amplio` → **`TBW | GB | Mujeres 18-65+ | Advantage+ amplio`**

Si en el futuro se quisiera un límite duro de edad, hay que pasar
`targeting_automation.advantage_audience = 0` explícitamente, a costa de desactivar la
expansión de audiencia.

## Placements confirmados (incluye Instagram)

El targeting efectivo del ad set lista `effective_publisher_platforms` con `facebook`,
`instagram`, `audience_network`, `messenger`, `whatsapp` y `threads`, y
`effective_instagram_positions` con `stream`, `story`, `reels`, `explore_home`,
`profile_feed` e `ig_search`. Queda zanjada la duda del apartado anterior: **sí entrega
en Instagram, Reels incluido**, pese a que `ads_get_ig_accounts` no esté disponible.

## Trampa: `location_types` por defecto bloquea la publicación (#1870194)

Al crear el ad set pasando solo `{"geo_locations":{"countries":["GB"]}}`, **Meta rellena
`location_types` con `["home"]`** — "personas que viven en". Ese tipo granular está
retirado, y el panel de revisión bloquea con:

> Your audience contains a location targeting option that has been removed (people
> living in, people traveling in or people recently in a location). (#1870194)

**No tiene arreglo por API.** Se probaron las tres vías y todas acaban en un valor
retirado, verificado releyendo el ad set:

| Enviado | Guardado por Meta |
|---|---|
| `location_types` omitido | `["home"]` — Meta lo reinserta |
| `["home","recent"]` | se guarda, pero el error persiste |
| — | `["travel_in"]` también figura como retirado en el mensaje |

El mensaje enumera los tres tipos (*living in, traveling in, recently in*) como
retirados, así que no queda ningún valor válido que enviar. **Se arregla con el botón
"Edit" del propio error en Ads Manager**, reconfirmando la ubicación; eso migra la
audiencia al modelo nuevo.

> ⚠️ Una vez migrado desde la interfaz, **no volver a actualizar `targeting` por API en
> este ad set**: `ads_update_entity` reemplaza el objeto entero y reinsertaría
> `location_types: ["home"]`, deshaciendo la migración.

Igual que con DSA, `ads_get_errors` devolvía `[]` mientras el panel bloqueaba. Ya son
**dos bloqueos consecutivos invisibles desde el MCP**. Conclusión operativa: después de
crear una campaña por MCP, **abrir siempre el panel de revisión en Ads Manager** antes de
darla por lista. La API no es fuente fiable de "esto se puede publicar".

### Cuidado al actualizar `targeting`

`ads_update_entity` **reemplaza el objeto entero**, no hace merge. Al corregir
`location_types` se perdió `user_age_unknown: true`, que Meta había puesto por defecto y
que estrecha la entrega en WhatsApp si falta. Hubo que restaurarlo en una segunda
llamada. Al tocar `targeting`, releer antes y reenviar todos los campos escribibles
(`geo_locations`, `genders`, `age_min`, `age_max`, `targeting_automation`,
`user_age_unknown`); los `effective_*` son derivados y no se envían.

## Ad transparency: no es un campo de texto, es un desplegable de identidades verificadas

Los campos *Advertiser* y *Payer* que pide el panel viven en **Ad transparency**, y no
aceptan texto libre: son un desplegable de **identidades ya verificadas ante Meta**. En
esta cuenta la única verificación completa es la personal del dueño; "The Books Wanderer"
no aparece porque nunca se verificó como entidad. Registrarla requiere "New verification"
y documentación de una entidad legal real.

Escribirlos por API **no funciona**: `ads_update_entity` acepta `dsa_beneficiary` /
`dsa_payor` (pasan su lista blanca — un campo inventado sí es rechazado con `VALIDATION`),
devuelve `success: true`, y el panel sigue pidiéndolos. Tampoco se pueden leer:
`ads_get_ad_entities` los marca *unsupported* y `ads_get_field_context` los devuelve en
`unknown_fields`. **Hacerlo en la interfaz.**

Aviso a tener presente: el propio recuadro advierte que nombre, ubicación y credenciales
del anunciante **se publican en la Ad Library de Meta**. Con una identidad personal, eso
significa el nombre real del dueño, público.

Nota: Ads Manager muestra a este ad set el aviso "Ad sets that include the European
Region", lo que sugiere que Meta trata GB dentro de esa agrupación a efectos de
transparencia — coherente con que exija Advertiser/Payer pese a que GB no sea UE.

### El error de ubicación NO depende del país (comprobado)

Se planteó esquivarlo cambiando de mercado. Se creó un ad set desechable en la misma
campaña apuntando a `["US","CA","AU"]` y Meta lo guardó igual:

```
geo_locations: { countries: ["US","CA","AU"], location_types: ["home"] }
```

Ad set de prueba borrado tras la comprobación. Conclusión: **cualquier ad set creado por
MCP nace con el valor retirado**, sea cual sea el país. Cambiar de mercado no evita
`#1870194`; solo la restricción de Advertiser/Payer era geográfica.

Implicación para el futuro: en esta cuenta, **los ad sets conviene crearlos desde Ads
Manager**, no por MCP, mientras la API siga escribiendo `location_types` obsoleto. El MCP
sigue siendo cómodo para campaña, creatividad y anuncio.

## Causa raíz del #1870194: una audiencia guardada, no el ad set

**Resuelto por el dueño el 2026-08-25.** El `location_types` obsoleto no venía del ad set:
venía de una **audiencia guardada** que el ad set tenía aplicada. Por eso ninguna de las
correcciones funcionaba — se reinyectaba desde la audiencia en cada validación.

La solución fue **crear una audiencia nueva** añadiendo simplemente United Kingdom. El
error desapareció al instante.

Qué se intentó antes, sin éxito, para no repetirlo:

| Intento | Resultado |
|---|---|
| `location_types: ["home","recent"]` por API | Se guarda, error persiste |
| Omitir `location_types` por API | Meta reinserta `["home"]` |
| Menú de la ubicación en Ads Manager | Solo granularidad de áreas, sin tipo |
| Quitar la ubicación | Bloqueado: "A single location can't be removed" |
| Añadir Irlanda → quitar GB → re-añadir GB → quitar Irlanda | Error persiste tras recarga |
| "Switch to original audience options" | No resuelve, y **apaga Advantage+ audience** |

**Lección:** ante `#1870194`, mirar primero si hay una audiencia guardada aplicada. El
campo del ad set es un síntoma, no la causa.

**Ojo con el draft:** la API lee el objeto **publicado**, no el borrador. Mientras haya
"Unpublished edits", `ads_get_ad_entities` devuelve el estado antiguo y no sirve para
verificar cambios hechos en la interfaz.
