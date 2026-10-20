# Prodigi Live evaluation: products and US quotes

This client is deliberately separate from storefront checkout, supplier routing,
product publication, and the MCP. It allows only:

- `GET https://api.prodigi.com/v4.0/products/{sku}`
- `POST https://api.prodigi.com/v4.0/quotes`

The transport rejects other method/path combinations before sending credentials.
It does not create, read, change, cancel or submit orders. There is no generic
HTTP command in the CLI and no database access. The quote is a supplier estimate,
not an order or authorization to manufacture.

## Secure setup

Configure `PRODIGI_API_KEY` as a protected runtime secret. Do not put it in the
repository, a quote JSON file, chat messages, command arguments, shell history,
or a public frontend. For a managed Codex environment, use its secrets/configuration
UI and allow HTTPS access to `api.prodigi.com`, then apply that configuration.
The current environment does not yet have this secret or destination configured.
For the VPS, use the existing protected server configuration process; do not
change existing provider keys or rotate the key as part of this addition.
The CLI uses the inherited runtime environment, not automatic `.env` discovery.

## Product lookup

Run from the repository root with the shop Python environment:

```sh
python server/scripts/prodigi_check.py --product GLOBAL-CAN-10X10
```

This SKU is an example from Prodigi's documentation, not a verified active store
product. A successful response verifies that the configured Live key can read
that SKU. Check its available attributes, variants, `shipsTo` and required print
areas before preparing a quote. There is no documented full catalog search/list
in this v4 reference, so product discovery starts with the public catalog/SKU list.

## US/USD quote

After verifying the SKUs and attributes, use a JSON list of quote items:

```sh
python server/scripts/prodigi_check.py --quote-items server/docs/prodigi/quote-us.example.json
```

The example contains the documented canvas and fine-art print SKUs at 10x10.
They have not been queried Live yet. Adapt copies, attributes and print areas
based on Product Details. Quote assets contain print-area names, not image URLs.
This initial client quotes only US destinations in USD; no customer addresses or
artwork are uploaded. It omits shippingMethod to request the provider's available
quote options. Preserve `CreatedWithIssues` warnings, especially US sales-tax
warnings. Review `costSummary`, shipment costs and `fulfillmentLocation`; delivery
to the US does not by itself establish production in the US. Do not treat the
returned estimate as a final tax-inclusive retail price or guaranteed margin.

The CLI prints the provider's quote/product result plus explicit disabled-order
and disabled-publication flags. Authentication errors and invalid responses are
reported without upstream bodies or key values; redirects are never followed.
No automatic retries of 429 responses are performed.

## Validation

```sh
python -m unittest discover -s server/tests -p test_prodigi.py -v
```

Six offline tests cover the two allowed operations, US/USD payloads, retained
warnings, rejected order paths and injected order fields, invalid quantities,
missing credentials, malformed responses, timeouts and safe authentication errors.
No tests require supplier credentials or send network requests.

Status: source prepared and offline-tested; not deployed, not MCP-accessible,
and no Live validation completed. Next step after secret/network setup: product
lookup, then quotes for the verified variants, with no order submission.

Reference: https://www.prodigi.com/print-api/docs/reference/
