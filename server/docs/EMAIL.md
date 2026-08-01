# Transactional email — The Books Wanderer

Customers receive email when:

| Event | When | Function |
|--------|------|----------|
| **Order confirmed** | PayPal payment captured | `send_order_paid` |
| **Being prepared** | Order submitted to CJ | `send_order_fulfillment_started` |
| **Shipped** | Admin calls ship API | `send_order_shipped` |
| **Cart reminder** | Admin/cron calls reminder API | `send_cart_reminder` |

The shop owner also gets a copy of **new paid orders** (`MAIL_NOTIFY_TO`).

Checkout **never fails** if email is down or unconfigured.

---

## 1. Associate a mailbox with the domain

Pick one approach:

### A) Resend (recommended for transactional)

1. Create account at [resend.com](https://resend.com)
2. Add domain `thebookswanderer.com` and set DNS (SPF, DKIM, DMARC)
3. Create API key
4. In `server/.env` on the VPS:

```env
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USER=resend
SMTP_PASSWORD=re_xxxxxxxx
SMTP_STARTTLS=1
MAIL_FROM=orders@thebookswanderer.com
MAIL_FROM_NAME=The Books Wanderer
MAIL_REPLY_TO=hello@thebookswanderer.com
MAIL_NOTIFY_TO=your-personal@email.com
```

### B) Google Workspace / Gmail

1. Use Google Workspace on the domain, or a Gmail app password
2. SMTP: `smtp.gmail.com:587`, user = full email, password = app password

### C) Cloudflare Email Routing + Resend

- Routing receives mail at `@thebookswanderer.com` → your inbox  
- Resend **sends** transactional mail (needs DNS as above)

---

## 2. Deploy env on VPS

```bash
ssh root@5.78.125.169
nano /var/www/thebookswanderer.com/server/.env
# paste SMTP_* and MAIL_* 
systemctl restart thebookswanderer
curl -sS https://thebookswanderer.com/api/health
# expect "email": true
```

---

## 3. Test

```bash
# Replace SECRET and email
curl -sS -X POST "https://thebookswanderer.com/api/admin/email/test?admin_key=SECRET&to=you@example.com"
```

---

## 4. Mark order shipped (customer tracking email)

```bash
curl -sS -X POST https://thebookswanderer.com/api/admin/orders/ship \
  -H 'Content-Type: application/json' \
  -d '{
    "admin_key": "SECRET",
    "order_id": 12,
    "carrier": "CJPacket",
    "tracking_number": "XX123",
    "tracking_url": "https://...",
    "send_email": true
  }'
```

List recent orders:

```bash
curl -sS "https://thebookswanderer.com/api/admin/orders?admin_key=SECRET"
```

---

## 5. Abandoned cart (“carrito abandonado”)

The store cart lives in **browser localStorage**, so the server does not see carts automatically.

Options:

1. **Manual / CRM**: when you know an email + lines, call:

```bash
curl -sS -X POST https://thebookswanderer.com/api/admin/email/cart-reminder \
  -H 'Content-Type: application/json' \
  -d '{
    "admin_key": "SECRET",
    "email": "customer@example.com",
    "customer_name": "Alex",
    "lines": [{"title": "Kindle Magnetic Sleeve — Pink", "quantity": 1}]
  }'
```

2. **Later product**: save email on checkout start, or add “email my cart” — then a cron can call the same API.

---

## 6. Code map

| Path | Role |
|------|------|
| `server/services/email.py` | SMTP + templates |
| `server/main.py` → checkout return | paid + fulfillment emails |
| `POST /api/admin/orders/ship` | shipped email |
| `POST /api/admin/email/test` | SMTP smoke test |
| `POST /api/admin/email/cart-reminder` | abandoned cart |
