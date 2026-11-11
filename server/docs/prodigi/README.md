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

Seven offline tests cover the two allowed operations, US/USD payloads, retained
warnings, rejected order paths and injected order fields, invalid quantities,
missing credentials, malformed responses, timeouts and safe authentication errors.
No tests require supplier credentials or send network requests.

Status: source prepared and offline-tested; not deployed, not MCP-accessible,
and no Live validation completed. Next step after secret/network setup: product
lookup, then quotes for the verified variants, with no order submission.

Reference: https://www.prodigi.com/print-api/docs/reference/

## VPS credential file (preferred for this evaluation)

Set `PRODIGI_API_KEY_FILE=/etc/tbw-prodigi/api_key` for the CLI process. The
client reads this file instead of the key environment variable and fails closed
if it is unreadable. Store it root-owned with mode 0600 in a root-only 0700
directory outside the web root and repository. Run evaluation as an authorized
operator. No storefront service restart is required to save the key or run the
CLI. A later service deployment should use systemd LoadCredential rather than
widening this file's permissions.

Deploying this PR and saving the key are separate steps. Until the code is
installed, saving the key alone will not expose Prodigi through TBW's MCP.

## Home Decor and Art shortlist

The VPS operator successfully queried GLOBAL-CAN-10X10 Live and quoted one unit
for US delivery: USD 20 item + USD 24.80 Budget/Standard shipping, excluding
possible sales tax. This is operator-supplied output, not a request from this
execution environment. Other candidates below remain unverified Live.

Run `python server/scripts/prodigi_shortlist.py` with the same protected key-file
setting to inspect and quote these researched SKUs separately (one unit each):

- GLOBAL-FAP-11X14 and GLOBAL-FAP-12X16: enhanced matte art prints, 200gsm.
  https://www.prodigi.com/products/prints-and-posters/art-prints/enhanced-matte-art/
- GLOBAL-CFP-11X14: classic framed fine-art print.
  https://www.prodigi.com/products/wall-art/framed-prints/classic-frames/
- H-CUSHCOV-18X18: double-sided cushion cover, no insert.
  https://www.prodigi.com/products/home-and-living/cushions-and-pillows/cushion-covers/
- GLOBAL-TAP-XS: printed polyester tapestry, 26x36 inches.
  https://www.prodigi.com/products/home-and-living/home-decor/wall-tapestries/
- GLOBAL-TAP-WOV-27X37: woven wall hanging, rod not included.
  https://www.prodigi.com/products/home-and-living/home-decor/woven-wall-hangings/

Public catalog pages list US fulfillment as an option. The comparison first
checks Product Details for variants shipping to US, selects black where available
(otherwise the first US-deliverable variant), and reports all selected attributes.
Required print areas come from the API rather than a guessed default. It then
quotes one SKU at a time and preserves tax warnings, totals and actual quoted
fulfillment countries. It does not calculate guaranteed profit, choose retail
prices, create artwork, publish listings or create orders. A candidate is not
publication-ready until costs, artwork, mockups and the storefront integration
are reviewed. This is a supplier shortlist, not a catalog of finished designs.

The comparison adds three offline tests for US variant selection, required print
areas, skipping unavailable products, separate quoting, warnings and production
location reporting. Ten Prodigi tests pass in total.
