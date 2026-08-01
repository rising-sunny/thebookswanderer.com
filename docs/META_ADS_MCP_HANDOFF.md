# Handoff: Meta Ads MCP · The Books Wanderer

**Propósito:** que otra IA agéntica (o el mismo operador en otra sesión) pueda **continuar la configuración de Meta Ads MCP** para la página de Facebook de **The Books Wanderer**, sin depender del contexto de Grok si se alcanza el límite diario.

**Fecha de contexto:** 2026-08-01  
**Sitio:** https://thebookswanderer.com  
**Repo:** `C:\repos\thebookswanderer.com` (GitHub: `rising-sunny/thebookswanderer.com`)  
**Marca hermana con Meta ya operativo:** https://mathrelaxing.store · repo `C:\repos\mathrelaxing.store`

---

## 1. Estado actual (qué ya está hecho)

| Ítem | Estado |
|------|--------|
| Página Facebook **The Books Wanderer** | En creación / recién creada por el dueño |
| Assets de marca para FB (perfil + portada) | En `assets/social/` (perfil nítido desde `logo.png`; portada HTML) |
| Meta App / Business Manager de MathRelaxing | Existen y se usan en producción para ads de MR |
| MCP **Ads oficial de Meta** registrado en Grok | Sí: `meta-ads` → `https://mcp.facebook.com/ads` en `~/.grok/config.toml` |
| MCP **Ads** registrado en Claude Code | Sí: `.mcp.json` en la raíz del repo (project scope, sin secretos) |
| OAuth MCP Meta en Grok | **Pendiente** — el doctor falla con `OAuth authorization required`; no existe `~/.grok/mcp_credentials.json` |
| OAuth MCP Meta en Claude Code | **Pendiente** — requiere `/mcp` en terminal interactiva y login de Meta en navegador |
| Pixel / Ad Account dedicados a TBW | **Aún no configurados** (recomendado crearlos) |
| Código de Marketing API en TBW (como `meta_ads.py` de MR) | **No portado** — la vía preferida ahora es **MCP oficial**, no reimplementar API |

### Config Grok ya escrita

```toml
# ~/.grok/config.toml
[mcp_servers.meta-ads]
url = "https://mcp.facebook.com/ads"
enabled = true
```

Comprobación conocida:

```text
grok mcp doctor meta-ads
→ server started
→ handshake failed: OAuth authorization required
```

Endpoint responde `401` con scopes:

```text
ads_management ads_read catalog_management business_management
pages_show_list instagram_basic ads_mcp_management
```

---

## 2. Objetivo de la tarea

1. Completar **autenticación OAuth** del Ads MCP oficial de Meta en el cliente de IA que use el operador (Grok, Claude, Cursor, etc.).
2. Asegurar que la **Página The Books Wanderer** y (idealmente) un **Ad Account + Pixel** de TBW estén en el **mismo Business Manager** que MathRelaxing.
3. Hacer una **prueba de solo lectura** (listar cuentas, páginas, campañas) sin gastar presupuesto.
4. Solo si el dueño lo pide: crear campañas en **PAUSED**, nunca ACTIVE sin confirmación explícita.

---

## 3. Principio de credenciales (importante)

**Se puede reutilizar** la misma Meta App y el mismo Business Manager de MathRelaxing.

**No se debe copiar ciegamente** a TBW:

| Variable / asset MR | ¿Reutilizar en TBW? |
|---------------------|---------------------|
| `META_APP_ID` / `META_APP_SECRET` | Sí (misma app) |
| Business Manager | Sí |
| `META_PAGE_ID` de MathRelaxing | **No** — otra página |
| `META_PIXEL_ID` de mathrelaxing.store | **No** — otro dominio |
| `META_AD_ACCOUNT_ID` de MR | Preferible **cuenta de ads aparte** para TBW |
| Tokens guardados de MR | Regenerar / ampliar acceso a assets TBW |

Referencia de implementación API (solo si hace falta código, no es el plan A):

- `C:\repos\mathrelaxing.store\routers\meta_ads.py`
- Env típicos: `META_APP_ID`, `META_APP_SECRET`, `META_AD_ACCOUNT_ID`, `META_PAGE_ID`, `META_PIXEL_ID`, token files en VPS

Plan A de este handoff: **Meta Ads MCP** (`https://mcp.facebook.com/ads`), no reescribir el router de MR.

Documentación Meta:

- Overview: https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-mcp-server/ads-mcp-server-overview  
- Get started (app / use case MCP): https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-mcp-server/ads-mcp-server-get-started  
- AI connectors help (sin app propia): https://www.facebook.com/business/help/1456422242197840  
- Blog (use case “Create & manage ads with ads MCP server”): https://developers.facebook.com/blog/post/2026/07/16/meta-ads-mcp-server/

---

## 4. Checklist operativo (en orden)

### A. Meta Business (navegador, dueño)

1. Confirmar que la Página **The Books Wanderer** existe y el dueño es **Admin**.
2. En [Business Settings](https://business.facebook.com/settings):
   - **Reclamar / asignar** la Página al Business Manager de MathRelaxing (o el BM principal del dueño).
   - (Recomendado) Crear **Ad Account** “The Books Wanderer” o similar.
   - (Recomendado) Crear **Dataset / Pixel** para `thebookswanderer.com` e instalar base + eventos (Purchase vía servidor/PayPal más adelante).
3. Opcional pero limpio: en [developers.facebook.com/apps](https://developers.facebook.com/apps) → app existente → **Use cases** → añadir **Ads and monetization** → **Create & manage ads with ads MCP server**.
4. Subir perfil/portada si aún no están (archivos en `assets/social/`).

### B. Autenticar MCP en el cliente de IA

#### Si el cliente es **Grok Build / Grok TUI**

1. Verificar que exista:

   ```toml
   [mcp_servers.meta-ads]
   url = "https://mcp.facebook.com/ads"
   enabled = true
   ```

   Si no:

   ```bash
   grok mcp add --transport http meta-ads https://mcp.facebook.com/ads --scope user
   ```

2. En la TUI: comando **`/mcps`** → seleccionar **`meta-ads`** → tecla **`i`** (authenticate OAuth).
3. Completar login Facebook en el navegador; conceder acceso a **ad account(s)** y **Page(s)** deseadas (incluir The Books Wanderer cuando exista en el BM).
4. Refrescar con **`r`** en `/mcps`.
5. Validar:

   ```bash
   grok mcp doctor meta-ads
   ```

   Esperado: healthy / tools listables.

6. Tokens OAuth de Grok quedan en `~/.grok/mcp_credentials.json` (permisos locales; no commitear).

#### Si el cliente es **Claude Code**

El servidor **ya está declarado en el repo** (project scope), en `.mcp.json`:

```json
{
  "mcpServers": {
    "meta-ads": {
      "type": "http",
      "url": "https://mcp.facebook.com/ads"
    }
  }
}
```

Esto significa que **cualquier clon del repo** (otra máquina, otra sesión) ve el servidor sin
volver a configurarlo. No contiene secretos: solo la URL pública del MCP oficial de Meta.

Pasos para dejarlo operativo:

1. Abrir Claude Code en `C:\repos\thebookswanderer.com`. Al detectar `.mcp.json` por primera vez
   pide **aprobar el servidor del proyecto** → aceptar.
2. En una **terminal interactiva** de Claude Code (la app de escritorio/web no abre este panel),
   ejecutar `/mcp` → seleccionar `meta-ads` → **Authenticate**.
3. Completar el login de Facebook en el navegador y conceder acceso a **ad account(s)** y
   **Page(s)** deseadas (incluir The Books Wanderer cuando exista en el BM).
4. Verificar en `/mcp` que `meta-ads` aparece como **connected** y lista herramientas.

Alternativa a nivel usuario (si se quiere el MCP en todos los repos, no solo TBW):

```bash
claude mcp add --transport http --scope user meta-ads https://mcp.facebook.com/ads
```

Nota operativa: a 2026-08-01, en esta máquina el binario `claude` **no está en el PATH** del
shell (instalación nativa), así que ese comando hay que lanzarlo desde una terminal donde sí lo
esté. El `.mcp.json` del repo evita necesitarlo.

Cursor / otros: panel **MCP / Connectors** → URL `https://mcp.facebook.com/ads` → OAuth Meta.

**No hace falta** copiar `META_APP_SECRET` al cliente MCP si se usa el flujo OAuth oficial de Meta (recomendado).

### C. Primera sesión con el agente (solo lectura)

Pedir al agente, en este orden:

1. “Lista las herramientas MCP de meta-ads disponibles.”
2. “Lista ad accounts y páginas a las que tienes acceso.”
3. “Confirma si ves la Página The Books Wanderer y con qué ad account está vinculable.”
4. “Resume campañas existentes **sin modificar nada** (si solo hay MR, indícalo).”

### D. Solo con OK explícito del dueño

- Crear borradores de campaña **PAUSED**.
- Asociar creatives / URLs a `https://thebookswanderer.com`.
- **Nunca** activar gasto ni subir presupuestos sin confirmación escrita del dueño.

---

## 5. Datos de marca útiles para ads

| Campo | Valor |
|-------|--------|
| Nombre | The Books Wanderer |
| Web | https://thebookswanderer.com |
| Tono | Boutique literaria, crema / verde bosque / oro |
| Tagline | For those who wander between pages. |
| Logo | `assets/logo.png` (hi-res), `assets/logo-email.png` (email/ligero) |
| Perfil FB | `assets/social/facebook-profile.jpg` |
| Portada FB | `assets/social/facebook-cover.jpg` (fuente editable: `facebook-cover.html`) |
| Email tienda | orders@ / hello@ thebookswanderer.com (ver `server/.env` en VPS, no en git) |
| Live admin tienda | https://thebookswanderer.com/admin/live (usuario `tbw`; password en VPS `LIVE_ADMIN_*`) |

Catálogo: productos CJ + picks Amazon afiliados; checkout PayPal; tracking propio `track.js` + `/admin/live`.

---

## 6. Qué NO hacer

- No reutilizar el Pixel ni el `PAGE_ID` de MathRelaxing como si fueran de TBW.
- No hacer push de `.env`, tokens, ni `mcp_credentials.json`.
- No activar campañas de pago “para probar” sin presupuesto y OK del dueño.
- No mezclar reporting de MR y TBW en la misma ad account si se puede evitar (complicará atribución).
- No asumir que OAuth de Grok ya está hecho: a 2026-08-01 **no lo estaba**.

---

## 7. Criterios de “tarea completada”

- [ ] `meta-ads` MCP autenticado y healthy en el cliente de IA del dueño.
- [ ] Página **The Books Wanderer** visible vía MCP / BM.
- [ ] (Ideal) Ad account + Pixel TBW creados y enlazados al dominio.
- [ ] Prueba de lectura OK (cuentas / páginas / insights vacíos o de MR diferenciados).
- [ ] Documento actualizado abajo con IDs reales (Page ID, Ad Account ID, Pixel ID).

### Rellenar cuando se complete

```text
META_PAGE_ID_TBW=1200587819810293   # confirmado 2026-08-01, Esteban = Full access
META_AD_ACCOUNT_ID_TBW=           # SIN RESOLVER — ver bloqueo abajo
# Candidata era 1636887674121801 ("Stunning Revelations 3"), pero el 2026-08-01 se
# comprobó que las TRES cuentas del BM estan DESACTIVADAS por método de pago:
#   Stunning Revelations, Stunning Revelations 2, Stunning Revelations 3
#   Banner: "We couldn't charge this ad account's payment method."
# => No se puede publicar nada hasta arreglar facturación. Lectura vía MCP sí funciona.
# => NO crear una 4ª cuenta antes de resolver el pago: heredaría la causa raíz.
META_PIXEL_ID_TBW=907494619068513   # dataset "The Books Wanderer", creado 2026-08-01
                                    # CAPI habilitado a nivel BM al crearlo (afecta tambien
                                    # a los datasets existentes de stunning.revelations)
BM_ID=                              # pendiente (sacar de la URL de business.facebook.com/settings)
                                    # BM elegido por el dueño: "stunning.revelations" (decisión 2026-08-01).
                                    # No se reutiliza el BM de MathRelaxing: TBW queda aislado,
                                    # lo que además mantiene la atribución separada (ver §6).
APP_ID_REUSED=
MCP_CLIENT=          # grok | claude | cursor | other
OAUTH_DONE_AT=
NOTES=
```

---

## 8. Prompt listo para pegar en otra IA

Copia y pega:

```text
Continúa el handoff de Meta Ads MCP para The Books Wanderer.

Lee docs/META_ADS_MCP_HANDOFF.md en el repo C:\repos\thebookswanderer.com
(o rising-sunny/thebookswanderer.com).

Contexto: ya registramos en Grok el MCP oficial https://mcp.facebook.com/ads
como meta-ads, pero faltaba OAuth. Hay otra marca (mathrelaxing.store) con
Meta App + Business Manager + ads funcionando; reutilizamos App/BM, no Page/Pixel/AdAccount.

Tareas:
1) Verificar/ayudar a completar OAuth del MCP en el cliente disponible.
2) Guiar claim de la Página The Books Wanderer en Business Manager.
3) Recomendar/crear Ad Account + Pixel para thebookswanderer.com si faltan.
4) Primera prueba SOLO LECTURA vía MCP.
5) No crear ni activar campañas de pago sin confirmación explícita del dueño.

Al terminar, rellena la sección “Rellenar cuando se complete” del .md.
```

---

## 9. Relación con el resto del stack TBW

| Sistema | Rol |
|---------|-----|
| FastAPI en VPS (`/var/www/thebookswanderer.com`) | Tienda, PayPal, CJ, email Resend, SSR SEO |
| `/admin/live` | Analytics self-hosted (no es Meta) |
| `track.js` | Funnel on-site (pageview, cart, checkout, purchase) |
| Meta Pixel / CAPI (futuro) | Atribución de ads; complementar con purchase server-side |
| Meta Ads MCP | Gestión de campañas desde agente, sin pasar por Ads Manager a mano |

Cuando exista Pixel TBW, un siguiente proyecto natural es: eventos Purchase desde el flujo PayPal (`server/main.py` checkout return) vía Conversions API, alineado con el pixel.

### Implementación del píxel (2026-08-01)

El píxel **no** se pegó en el `<head>` de cada página. Va dentro de `track.js`, que ya se carga
en las 5 páginas HTML y en las dos plantillas SSR de `server/ssr.py`. Los eventos estándar de
Meta se derivan de las llamadas `tbwTrack()` que el funnel self-hosted ya emitía, vía el mapa
`META_EVENTS`. Añadir o renombrar un evento se hace en un solo sitio.

| `tbwTrack()` | Evento Meta |
|---|---|
| `pageview` | `PageView` |
| `product_view` | `ViewContent` |
| `add_to_cart` | `AddToCart` |
| `checkout_start` | `InitiateCheckout` |
| `payment_redirect` | `AddPaymentInfo` |
| `purchase` | `Purchase` |
| `cart_view` | *(ninguno — no hay estándar equivalente)* |

**Limitación conocida:** `purchase` se dispara en el retorno de PayPal (`checkout.js`) y ahí solo
hay `order_id` y `status`, **no el importe**. Por tanto `Purchase` llega a Meta **sin `value`**:
Meta registra la conversión pero no puede calcular ROAS. La solución correcta no es parchear el
cliente, es el **Purchase server-side vía CAPI** descrito arriba, donde el importe real sí está
disponible. Hasta entonces, optimizar por conversiones funciona; por valor, no.

Nota: `track.js` decía "No third-party scripts" en su cabecera. Dejó de ser cierto con el píxel;
el comentario se actualizó.

---

## 10. Contacto operativo

- Dueño / operador: Esteban (emails usados en el proyecto: `estebannavarro.rojo@gmail.com` notificaciones dueño; pruebas a `esteban.hopestarstore@gmail.com`).
- Preferencia de idioma con el dueño: **español**.
- Preferencia de seguridad ads: **pausado por defecto**, confirmación antes de gastar.

---

## 11. Historial de revisiones

- **2026-08-01 — creación** (sesión Grok). Estado: MCP `meta-ads` en `~/.grok/config.toml`, OAuth pendiente.
- **2026-08-01 — revisión** (sesión Claude Code). Verificado contra la máquina:
  - `~/.grok/config.toml` contiene `meta-ads` tal como se documentaba. ✔
  - **No** existe `~/.grok/mcp_credentials.json` → OAuth de Grok efectivamente sin hacer. ✔
  - Assets `assets/social/*` y `assets/logo*.png` presentes. ✔
  - `C:\repos\mathrelaxing.store\routers\meta_ads.py` presente (referencia API). ✔
  - Claude Code **no** tenía el MCP configurado → se añadió `.mcp.json` (project scope) en esta revisión.
  - `docs/` estaba sin commitear → se commitea en esta revisión.
  - Sección 7 (IDs reales) sigue vacía: nada de la parte 4.A (Business Manager) está hecho todavía.
- **2026-08-01 — sesión guiada con el dueño.** Avances:
  - Página TBW ya reclamada en el BM `stunning.revelations`, dueño con Full access. ✔
  - Píxel/dataset `907494619068513` creado e **instalado en el sitio** vía `track.js` (ver §9).
  - **Bloqueo encontrado:** las 3 cuentas de anuncios del BM estaban desactivadas por método de
    pago. El dueño reporta haberlo solucionado; **falta confirmar** que la etiqueta roja
    desapareció y que la cuenta admite publicar.
  - Pendiente: OAuth del MCP (§4.B), BM ID, moneda de la cuenta, y conectar el dataset a la
    cuenta de anuncios una vez esté activa.

---

*Fin del handoff. Actualiza la sección 7 al completar OAuth e IDs.*
