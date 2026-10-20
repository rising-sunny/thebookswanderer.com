# Lifestyle gallery audit

AI-assisted environmental mockups supplement the original product images. Original product photos, details, prices and variants are preserved. No social publication is performed.

## Reviewed additions

- letters-from-the-library
- reading-society-pouch
- reading-society-notebook
- commonplace-book
- usb-clip-reading-light
- reading-society-tote
- book-club-companion
- the-lost-manuscript
- color-the-classics-printed
- color-the-classics
- a-literary-year-2027-wall-calendar
- reading-passport-hardcover
- reading-passport
- library-ephemera-sticker-sheet
- readers-2027-desk-calendar
- kindle-magnetic-sleeve
- heart-book-page-holder

## Existing environmental photos retained

- bedside-book-rest
- japanese-a5-book-cover
- reading-passport-printed
- animal-book-clips

## Pending visual review of remote supplier photos

These products cannot yet be classified as needing additional images. Their remote supplier images were blocked by the environment network policy. Do not generate replacements from product names alone. The draft adds cf.cjdropshipping.com, oss-cf.cjdropshipping.com and images-api.printify.com; it must be applied before continuing this review.

- cherry-blossom-highlighters
- pearlescent-book-tabs
- erasable-highlighters
- wizard-of-oz-bookmark-tin-woodman
- wizard-of-oz-bookmark-cowardly-lion
- wizard-of-oz-jigsaw-puzzle
- christmas-magnetic-bookmarks
- reading-log-bookmarks
- heart-bookshelf-ornament
- book-tree-christmas-ornament
- bookshelf-lantern-light
- baker-street-book-nook-kit
- twilight-library-book-nook-kit
- book-lovers-advent-calendar
- modern-bookends-pair
- washable-kraft-book-cover
- antique-animal-bookends
- adjustable-reading-stand
- paper-butterfly-bookmark-set
- hollow-kitten-bookmark
- palace-kitten-bookmarks
- stacked-books-table-lamp
- wooden-reading-tracker
- silicone-page-clip-bookmark
- butterfly-metal-bookmark
- wooden-finger-book-holder
- stained-glass-stickers
- washi-sticker-book

## Applying on the VPS

After assets are deployed, run the existing Run server script workflow with script=apply_lifestyle_mockups.py and empty args for a dry-run. Then args=--apply adds the reviewed photos. A second --apply must report zero changes. Asset SHA-256 checks prevent applying missing or replaced images. Gallery writes use a transaction and compare the previous value to avoid overwriting intervening edits. Before writes, backups are saved in server/data/lifestyle-gallery-backups/ with mode 0600.

The manifest is server/scripts/lifestyle_mockups_20261020.json. Originals used as generation references came from the live product API/images; image_gen generated the environments and product mockups. JPEG exports only re-encode the generated pixels. The original generated files remain in the cloud workspace.

To restore a gallery, use its backup before value only after confirming the current value equals the backup after value. Do not blindly restore over subsequent edits.
