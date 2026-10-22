# One-time Reading Society photo post

`scripts/static_social_post.py` publishes one existing product photo to the
Facebook Page The Books Wanderer and linked Instagram @thebooks.wanderer.
It does not invoke the reel publisher. The existing daily reel schedule remains
in effect; this command adds one static post to each account.

Run without arguments for a read-only preview. Publish explicitly with:

```sh
server/.venv/bin/python server/scripts/static_social_post.py --server-root /var/www/thebookswanderer.com/server --publish
```

Credentials are read from that server root's `.env` (`FB_PAGE_ID`,
`FB_PAGE_TOKEN`). They are sent only to Meta through a Bearer header. Product
and image downloads receive no credentials. The product must still be the
Reading Society tote; the image must be an owned, publicly reachable JPEG that
meets the conservative Instagram size and aspect ratio checks. The script
does not transform or upload new store assets.

The fixed campaign is `reading_society_tote_photo_20261019`. A private journal
under `server/data/static-social-posts/` records each network's progress.
Completed posts are skipped on rerun. The Instagram container is reused while
processing. Each write is persisted as uncertain before the request is sent;
an interrupted or rejected write blocks further attempts until an operator
reconciles it with Meta. Do not delete the journal to retry. This deliberately
favors avoiding duplicates over automatic recovery. The optional permalink
lookup cannot cause a second publication.

Validation uses mocked HTTP only:

```sh
server/.venv/bin/python -m unittest discover -s server/tests -p test_static_social_post.py -v
```

The script has not published anything during development. Live image format,
public retrieval by Meta, and actual publication are verified on the VPS.
