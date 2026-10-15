# Reading Society release

This release adds only `reading-society-tote` (Printify) and
`book-club-companion` (Lulu). Retail prices are USD 27.99 and USD 24.99.
The book is an English, 100-page, undated A5 paperback for twelve gatherings.

Deploy the scripts and assets with the normal Deploy workflow before running:

```sh
gh workflow run run-script.yml -f script=publish_reader_collection.py -f args=--validate
# Inspect successful supplier validation and all four manufacturer mockups.
gh workflow run run-script.yml -f script=publish_reader_collection.py -f args=--apply
```

Without arguments, the publisher only prints the proposed products. Validation
installs the print files, downloads four manufacturer mockups, checks the tote's
original artwork/available variant and live costs, and requires both Lulu PDF
validations to reach NORMALIZED. Apply checks that evidence and file hashes
again, then atomically upserts the two slugs. Repeating apply does not duplicate
the products or their variants. It does not order prints or initiate payments.

The repository contains only an eight-page public sample and an encrypted CMS
bundle of the complete print PDFs. The existing server transport key is reused;
its private key and the normalized-release reports remain under
`DIGITAL_DIR/.release-private/`. Decrypted full PDFs remain outside the web root
and use the existing signed `/api/print-files/` endpoint for supplier access.
No credentials or signed print URLs belong in logs or the repository.

The tote is fulfilled through its Printify product and variant IDs; the book
uses the specified Lulu package and private interior/cover filenames. Existing
free-shipping behavior is retained (tote US only; book configured Lulu countries).
Technical file validation does not replace inspection of a physical sample.

Offline regression checks:

```sh
server/.venv/bin/python -m unittest discover -s server/tests -v
```
