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
