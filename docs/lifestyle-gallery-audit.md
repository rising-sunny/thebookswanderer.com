# Lifestyle gallery audit

All 49 active products in the catalog snapshot have been visually reviewed. Added 28 AI-assisted environmental mockups; retained existing environmental/use-context images for the other 21. Original product photographs, hero images, text, pricing and variants remain unchanged. No social publication occurs.

The first release covered 17 products while remote supplier photos were blocked. After network access was applied, all remaining references were downloaded and reviewed. Eleven additional galleries received mockups; 17 already contained styled surfaces, in-use shots, or real room context.

## Reviewed AI additions

- letters-from-the-library
- reading-society-pouch
- reading-society-notebook
- commonplace-book
- usb-clip-reading-light
- reading-society-tote
- book-club-companion
- the-lost-manuscript
- erasable-highlighters
- color-the-classics-printed
- color-the-classics
- a-literary-year-2027-wall-calendar
- reading-passport-hardcover
- reading-passport
- library-ephemera-sticker-sheet
- readers-2027-desk-calendar
- reading-log-bookmarks
- book-tree-christmas-ornament
- bookshelf-lantern-light
- baker-street-book-nook-kit
- book-lovers-advent-calendar
- modern-bookends-pair
- antique-animal-bookends
- adjustable-reading-stand
- paper-butterfly-bookmark-set
- hollow-kitten-bookmark
- kindle-magnetic-sleeve
- heart-book-page-holder

## Existing contextual photography retained

- bedside-book-rest
- japanese-a5-book-cover
- cherry-blossom-highlighters
- pearlescent-book-tabs
- wizard-of-oz-bookmark-tin-woodman
- wizard-of-oz-bookmark-cowardly-lion
- wizard-of-oz-jigsaw-puzzle
- reading-passport-printed
- christmas-magnetic-bookmarks
- heart-bookshelf-ornament
- twilight-library-book-nook-kit
- washable-kraft-book-cover
- palace-kitten-bookmarks
- stacked-books-table-lamp
- wooden-reading-tracker
- silicone-page-clip-bookmark
- butterfly-metal-bookmark
- wooden-finger-book-holder
- stained-glass-stickers
- animal-book-clips
- washi-sticker-book

## Applying on the VPS

After assets are deployed, run the existing Run server script workflow with script=apply_lifestyle_mockups.py and empty args for a dry-run. Then args=--apply adds missing reviewed photos. Repeating --apply must report zero changes. Asset SHA-256 checks prevent applying missing or replaced images. Gallery writes use a transaction and compare the previous value to avoid overwriting intervening edits. Before writes, backups are saved in server/data/lifestyle-gallery-backups/ with mode 0600.

The manifest is server/scripts/lifestyle_mockups_20261020.json. Original references came from the live product API, the store images and supplier listing images; image_gen generated the environments and product mockups. JPEG exports only re-encode generated pixels. Original generated files remain in the cloud workspace.

To restore a gallery, use its backup before value only after confirming the current value equals the backup after value. Do not blindly restore over subsequent edits.
