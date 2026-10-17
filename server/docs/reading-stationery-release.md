# Reading stationery, October 2026

Two US-only Printify products, fulfilled through the existing checkout integration:

| Store slug | Supplier product | Blueprint / provider / variant | Retail | Production + standard US shipping |
| --- | --- | --- | --- | --- |
| reading-society-pouch | 6ad32a768dad753234086750 | 1179 / District Photo 28 / 91328 | $22.99 | $6.95 + $5.69 = $12.64 |
| letters-from-the-library | 6ad32a7a28a1a95859014f6c | 1101 / Taylor 228 / 82165 | $29.99 | $11.10 + $7.39 = $18.49 |

Quotes exclude supplier taxes, payment fees, returns, design and advertising. Printify costs are checked again before activation. The pouch is sold empty, is not padded and does not fit an A5 notebook. Cards are ten identical flat 4.9 × 3.5 inch uncoated cards plus ten envelopes, with a lined English-language reverse. No postage is included.

Artwork source records live beside the public previews. The owl is Robert Havell after Audubon, *Great Cinereous Owl* (1837), National Gallery of Art, accession 1945.8.351, public domain. The cards reproduce Hokusai's *Lake Suwa in Shinano Province* (ca. 1830–32), Metropolitan Museum of Art, JP2965, Open Access / CC0. Full compositions are reproduced without generative alteration; layout and text are by The Books Wanderer. Effective source resolutions are 1078 dpi and 497 dpi respectively. Upload IDs, hashes and canvas dimensions are recorded in the release JSON.

Deploy the commit through the existing Deploy workflow. Run `publish_reading_stationery.py --prepare` through Run server script to validate supplier mappings and download the four manufacturer mockups per product. Review those mockups and run `--apply` to publish. The default mode only checks supplier configuration and costs. No mode orders samples, creates a customer order or sends a product to production.

The release is idempotent: existing matching product and variant IDs are preserved. Conflicting slugs or supplier mappings, unavailable variants, altered artwork, missing images and excessive landed cost block activation. Both DB writes share one transaction. Store listings appear in the existing dynamic catalogue, sitemap and shopping feed; autonomous marketing can discover them through its existing catalogue queries.
