#!/usr/bin/env python3
"""Create the four Pride and Prejudice posters (Hugh Thomson, 1894) in Printify.

Reuses create_printify_poster.py (copy of the annotated poster: same blueprint, print provider and placement)
and only changes the artwork, title, description and tags. Nothing is published and no order is made.

  python scripts/create_printify_austen_posters.py            # dry run: prints the plan for each poster
  python scripts/create_printify_austen_posters.py --apply    # uploads the print files and creates the products

The print files live in /assets/products/<slug>/ on the live site (deploy first).
"""
from __future__ import annotations

import asyncio
import re
import sys

import create_printify_poster as base

# Thomson's plates are about 1,300 px wide in the scan: the four sizes below keep the line art crisp.
SIZES = {(11, 14), (12, 16), (16, 20), (18, 24)}
TAIL = (" Illustration by Hugh Thomson from the 1894 George Allen edition, in the public domain (scan from the New York "
        "Public Library). Museum-style matte paper on a warm paper tone; sizes from 11 x 14 to 18 x 24 in; frame not "
        "included. Printed to order in the US; check your destination for delivery availability and the total.")
TAGS = ["poster", "jane austen", "pride and prejudice", "literary quote", "book lover gift", "vintage illustration"]
POSTERS = [
    ("austen-poster-she-is-tolerable",
     "Pride and Prejudice Poster, \"She Is Tolerable\" Darcy Quote, Hugh Thomson 1894 Illustration, Matte Print",
     "The line that starts it all: \"She is tolerable; but not handsome enough to tempt me.\" Mr. Darcy at the Meryton "
     "ball, overheard by Elizabeth Bennet, drawn by Hugh Thomson." + TAIL),
    ("austen-poster-noble-mien",
     "Pride and Prejudice Poster, Mr. Darcy Enters the Ball, Hugh Thomson 1894 Illustration, Matte Print",
     "\"Mr. Darcy soon drew the attention of the room by his fine, tall person, handsome features, noble mien.\" "
     "Darcy arrives at the Meryton assembly, in Hugh Thomson's pen drawing." + TAIL),
    ("austen-poster-never-knew-myself",
     "Pride and Prejudice Poster, \"Till This Moment I Never Knew Myself\" Elizabeth Quote, Thomson 1894, Matte Print",
     "\"Till this moment I never knew myself.\" Elizabeth Bennet, after reading Darcy's letter: Hugh Thomson's sword and "
     "scales from the head of chapter 36." + TAIL),
    ("austen-poster-first-page",
     "Pride and Prejudice Poster, \"It Is a Truth Universally Acknowledged\" Opening Page, Thomson 1894, Matte Print",
     "The first page of Pride and Prejudice as Hugh Thomson dressed it in 1894: a peacock, the hand-lettered title and "
     "the most famous opening sentence in English." + TAIL),
]


async def main(apply: bool) -> int:
    base.SIZES = SIZES
    base.TAGS = TAGS
    for slug, title, description in POSTERS:
        print(f"\n== {slug}")
        base.BASE = f"https://thebookswanderer.com/assets/products/{slug}"
        base.TITLE, base.DESCRIPTION = title, description
        code = await base.main(apply)
        if code:
            return code
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main("--apply" in sys.argv)))
    except Exception as exc:  # provider messages can carry signed URLs
        print(re.sub(r"https?://\S+", "[url]", str(exc)), file=sys.stderr)
        raise SystemExit(1)
