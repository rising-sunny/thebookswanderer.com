# Museum-art notebook editions

Owner-approved real historical illustrations, published as two complementary
products for the US market. No generated artwork or physical sample order.

| Product | Supplier / edition | Retail |
| --- | --- | --- |
| `commonplace-book` | Lulu A5 paperback, 160 B&W interior pages, matte colour cover | USD 24.99 |
| `reading-society-notebook` | Printify blueprint 485, District Photo 28, variant 65223; 150 lined pages | USD 27.99 |

Standard US shipping is included. The notebook is US-only, using the existing
Printify destination restrictions. The paperback uses the existing Lulu routes.
The Commonplace Book's entire printed interior is English; the notebook's
cover text is English and its supplier interior is standard lined paper.

## Museum provenance

Original museum JPEG bytes are retained unchanged, with institutional source,
rights statement, dimensions and SHA-256 in each `artwork-source.json`.

- **Great Cinereous Owl**, 1837, Robert Havell after John James Audubon.
  National Gallery of Art, Washington; Gift of Mrs. Walter B. James, 1945.8.351.
  https://www.nga.gov/artworks/32492-great-cinereous-owl
  Object page explicitly marks the media free and in the public domain.
  Original reproduction: 2681 × 4096 px, placed at approximately 843 ppi.
- **Lake Suwa in Shinano Province**, ca. 1830–32, Katsushika Hokusai.
  The Metropolitan Museum of Art, Henry L. Phillips Collection,
  Bequest of Henry L. Phillips, 1939; JP2965, object 56240.
  https://www.metmuseum.org/art/collection/search/56240
  Public Domain / Open Access CC0: https://www.metmuseum.org/hubs/open-access
  Original reproduction: 1948 × 1347 px, placed at approximately 401 ppi.

The complete image compositions, original paper tones and historical marks
are preserved. Attribution appears in the paperback and on the notebook's
back cover and in both product listings. The museum artworks are not claimed
as original illustrations by the store. Product image renderings come from
the actual Lulu print PDFs or Printify's actual manufacturer mockups.

## Interior and print files

Commonplace Book: 9 frontmatter pages (including four topic-index pages),
60 facing-page entry pairs on pages 10–129, 16 additional ruled pages,
12 dot-grid pages, and 3 final thread maps. Even-numbered collection pages
face odd-numbered response pages. An eight-page PDF sample shows actual pages.
A5 trim is 148 × 210 mm. Cover size is the current Lulu API result:
888 × 613 pt for package `0583X0827BWSTDPB060UW444MXX`, 160 interior pages.

Full print PDFs are transported only as a CMS-encrypted ZIP. The existing
server-held transport private key remains in the private digital folder.
Checksums in the release specification, bundle manifest and installed files
must agree. Public sample and product images are separate from full print files.

Printify's 4065 × 2850 pixel placeholder is the full wrap, including turn-in
areas, back, spine and front. Native 300 dpi PNG, centred at scale 1, angle 0.
Manufacturer mockups verify the final appearance. Reserve the lower-right back
cover for the manufacturer's small barcode, disclosed in customer copy.

## Build and release

Design source lives in `design/nature-notebooks/` and uses ReportLab, PyMuPDF,
Pillow, Playwright and the installed Liberation fonts. Run from the repository
root after staging the approved original images:

```sh
python design/nature-notebooks/build_interior.py
python design/nature-notebooks/build_covers.py
python design/nature-notebooks/render_book.py
```

Temporary build files go to `work/nature-notebooks/`. The final encrypted
bundle, customer images/sample, supplier IDs, checksums and bilingual copy
are versioned. Regenerating print files requires updating the specification,
re-encrypting and completing supplier validation again.

After deploying through GitHub Actions:

```sh
gh workflow run run-script.yml -f script=publish_nature_notebooks.py -f args=--validate
gh workflow run run-script.yml -f script=publish_nature_notebooks.py -f args=--apply
```

Validation installs the encrypted PDFs, downloads reviewed supplier mockups,
requires both Lulu PDFs to normalize and match 160 pages, and verifies the
exact Printify product, enabled/available variant, artwork, placement and retail.
Publication rechecks all gates and atomically upserts only these two listings.
It preserves product/variant IDs on reruns and rejects supplier/slug collisions.
Live cost limits are USD 15.50 including Lulu fulfillment/shipping/tax for the
reviewed DC sample destination and USD 18.50 for Printify production plus US
shipping. Payment processing fees are excluded from those limits.

No customer order, sample, supplier production payment, social post or email
is created by either mode. Without arguments the publisher is a dry run.
