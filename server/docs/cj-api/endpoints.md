# CJ API 2.0 — endpoint cheatsheet (TBW subset)

Base: `https://developers.cjdropshipping.com/api2.0/v1`  
Header on all authenticated calls: `CJ-Access-Token: <token>`  
Content-Type for POST bodies: `application/json`

---

## Authentication

### getAccessToken

```
POST /authentication/getAccessToken
{ "apiKey": "<CJ_API_KEY>" }
```

### refreshAccessToken

```
POST /authentication/refreshAccessToken
{ "refreshToken": "<refresh>" }
```

---

## Product query

```
GET /product/query?pid=<pid>
GET /product/query?productSku=<SPU>
GET /product/query?variantSku=<variantSku>
GET /product/query?productSku=<SPU>&features=enable_video
GET /product/query?productSku=<SPU>&features=enable_combine
```

Useful `data` fields:

| Field | Notes |
|-------|--------|
| `pid` | Product id |
| `productSku` | SPU |
| `productNameEn` | English title (often raw; rewrite for store) |
| `bigImage` | Hero |
| `productImageSet` | Gallery URLs |
| `description` | HTML (do not paste raw into storefront) |
| `sellPrice` | Cost range or unit |
| `variants[]` | Options |
| `variants[].vid` | **Order / freight id** |
| `variants[].variantSku` | SKU |
| `variants[].variantKey` | e.g. color-size |
| `variants[].variantImage` | Option thumb (verify mapping!) |
| `variants[].variantSellPrice` | Unit cost USD |
| `productVideo` | Video id list when `features=enable_video` |

---

## Product list V2 (search)

```
GET /product/listV2?keyWord=<q>&page=1&size=20
GET /product/listV2?keyWord=<SPU>&features=enable_video
```

---

## Videos

```
POST /product/queryVideosByProductId
{ "productId": "<pid>" }
```

Each item may include:

| Field | Notes |
|-------|--------|
| `videoNumber` | e.g. `SPCJJT13936890002` |
| `videoId` / `id` | Hash |
| `videoUrl` | mp4 (download with Referer) |
| `coverURL` | Poster |
| `duration` | Seconds |
| `isFree` / `isBuy` | Licensing |

Download example:

```bash
curl -H "Referer: https://developers.cjdropshipping.com/" -O "<videoUrl>"
```

---

## Freight

```
POST /logistic/freightCalculate
{
  "startCountryCode": "CN",
  "endCountryCode": "US",
  "products": [{ "vid": "<vid>", "quantity": 1 }],
  "zip": "optional"
}
```

Each option typically:

| Field | Notes |
|-------|--------|
| `logisticName` | Carrier (we hide name on PDP; keep for ops) |
| `logisticPrice` | Cost USD |
| `logisticAging` | Transit days range string |

Store multiplies cost by `SHIPPING_MARKUP` (default 1.15).

---

## Create order

```
POST /shopping/order/createOrderV2
```

Relevant body shape (see live `_submit_to_cj` in `main.py`):

- `orderNumber` — our external reference  
- `shippingCountryCode`, address fields  
- `products`: `[{ "vid", "quantity", ... }]`  
- `payType`: `1` page pay · `2` balance · `3` create only  

---

## Error envelope

Often:

```json
{
  "code": 200,
  "success": true,
  "message": "Success",
  "data": { },
  "requestId": "..."
}
```

Non-200 `code` or `success: false` → treat as error.  
QPS / 429: slow down and retry.
