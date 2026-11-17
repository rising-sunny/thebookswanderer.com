#!/usr/bin/env python3
"""Create the reader-quiz lead campaign in the MathRelaxing ad account, always PAUSED.

  python scripts/meta_create_quiz_campaign.py            # dry run: prints the payloads, sends nothing
  python scripts/meta_create_quiz_campaign.py --apply    # creates campaign, ad set, two creatives and two ads

Options: --countries US,GB  --budget 700 (account-currency minor units per day: 700 = 7 USD)
         --start 2026-11-26  --end 2026-12-09  --account act_...  --page ...  --pixel ...

Every call goes through services.supplier_api.call, so the owner's gate applies: objects are created PAUSED
(the owner turns them on in Ads Manager) and the daily budget may not exceed TBW_META_ADS_MAX_DAILY_BUDGET.
It needs the two ad images to be public first (assets/ads/), and prints the ids it creates.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

SITE = "https://thebookswanderer.com"
QUIZ = SITE + "/guides/what-kind-of-reader-are-you/"
DEFAULT_ACCOUNT = "act_2206299143461363"   # MathRelaxing, USD
DEFAULT_PAGE = "1200587819810293"          # The Books Wanderer
DEFAULT_PIXEL = "1455294560116297"         # dataset "The Books Wanderer pixel" in that account
CAMPAIGN = "TBW | Leads | Quiz lector | EN"

ADS = {
    "a": {
        "image": "quiz-ad-a-typographic-1080x1350.jpg",
        "message": ("Six quick questions, five reader types. Find out if you are a Cozy Nester, an Annotator, a Wanderer, "
                    "a Challenger or a Classic Romantic, and get a free printable reader card with bookmarks made for you."),
        "headline": "What kind of reader are you?",
        "description": "Free printable reader card",
    },
    "b": {
        "image": "quiz-ad-b-cards-1080x1350.jpg",
        "message": ("Which reader are you? Take the two-minute quiz and we will send a free printable reader card for your "
                    "type: bookmarks, small rituals and a checklist."),
        "headline": "Find your reader type",
        "description": "2-minute quiz, free printable",
    },
}


def landing(variant: str) -> str:
    return (f"{QUIZ}?utm_source=meta&utm_medium=paid_social&utm_campaign=quiz_leads_nov26&utm_content=ad_{variant}")


def build(account: str, page: str, pixel: str, countries: list[str], budget: int, start: str, end: str,
          campaign_id: str = "<campaign_id>", adset_id: str = "<adset_id>",
          creative_ids: dict[str, str] | None = None) -> list[tuple[str, str, dict]]:
    """The calls in order: (label, path, body). Ids that do not exist yet are placeholders."""
    creative_ids = creative_ids or {k: f"<creative_{k}_id>" for k in ADS}
    steps: list[tuple[str, str, dict]] = [
        ("campaign", f"/{account}/campaigns", {
            "name": CAMPAIGN, "objective": "OUTCOME_LEADS", "status": "PAUSED", "special_ad_categories": [],
            "daily_budget": budget, "bid_strategy": "LOWEST_COST_WITHOUT_CAP"}),
        ("ad set", f"/{account}/adsets", {
            "name": f"{'+'.join(countries)} | Advantage+ | Women 25-65 | Quiz", "campaign_id": campaign_id, "status": "PAUSED",
            "billing_event": "IMPRESSIONS", "optimization_goal": "OFFSITE_CONVERSIONS", "destination_type": "WEBSITE",
            "promoted_object": {"pixel_id": pixel, "custom_event_type": "LEAD"},
            "targeting": {"geo_locations": {"countries": countries}, "age_min": 25, "age_max": 65, "genders": [2],
                          "targeting_automation": {"advantage_audience": 1}},
            "start_time": f"{start}T08:00:00+0000", "end_time": f"{end}T23:59:00+0000"}),
    ]
    for key, ad in ADS.items():
        link = landing(key)
        steps.append((f"creative {key}", f"/{account}/adcreatives", {
            "name": f"Quiz {key.upper()} | {ad['headline']}",
            "object_story_spec": {"page_id": page, "link_data": {
                "link": link, "message": ad["message"], "name": ad["headline"], "description": ad["description"],
                "picture": f"{SITE}/assets/ads/{ad['image']}",
                "call_to_action": {"type": "LEARN_MORE", "value": {"link": link}}}}}))
    for key in ADS:
        steps.append((f"ad {key}", f"/{account}/ads", {
            "name": f"Quiz {key.upper()}", "adset_id": adset_id, "status": "PAUSED",
            "creative": {"creative_id": creative_ids[key]}}))
    return steps


async def images_are_public() -> list[str]:
    import httpx
    missing = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for ad in ADS.values():
            url = f"{SITE}/assets/ads/{ad['image']}"
            if (await client.head(url)).status_code != 200:
                missing.append(url)
    return missing


async def apply(args) -> int:
    from services import supplier_api as s

    missing = await images_are_public()
    if missing:
        print("The ad images are not public yet, deploy them first:", *missing, sep="\n  ")
        return 1
    ids: dict[str, str] = {}

    async def post(label: str, path: str, body: dict) -> str | None:
        try:
            r = await s.call("meta", "POST", path, body)
        except Exception as exc:  # noqa: BLE001
            print(f"  {label}: {type(exc).__name__}: {str(exc)[:200]}")
            return None
        data = r.get("data")
        if r.get("status", 500) >= 400 or not isinstance(data, dict) or "id" not in data:
            print(f"  {label}: Meta said no ({r.get('status')}): {str(data)[:400]}")
            return None
        print(f"  {label}: created {data['id']}")
        return str(data["id"])

    first = build(args.account, args.page, args.pixel, args.countries, args.budget, args.start, args.end)
    campaign = await post(*first[0])
    if not campaign:
        return 1
    adset = await post(*build(args.account, args.page, args.pixel, args.countries, args.budget, args.start, args.end,
                               campaign_id=campaign)[1])
    if not adset:
        print(f"Campaign {campaign} exists, paused and empty. Fix the error above and rerun, or delete it in Ads Manager.")
        return 1
    creatives: dict[str, str] = {}
    for key in ADS:
        step = next(x for x in first if x[0] == f"creative {key}")
        cid = await post(*step)
        if not cid:
            print(f"Stopped at creative {key}. Created so far: campaign {campaign}, ad set {adset}.")
            return 1
        creatives[key] = cid
    final = build(args.account, args.page, args.pixel, args.countries, args.budget, args.start, args.end,
                  campaign_id=campaign, adset_id=adset, creative_ids=creatives)
    for step in final:
        if step[0] in {f"ad {key}" for key in ADS}:   # not "ad set": startswith("ad ") would create it twice
            await post(*step)
    print("\nAll objects are PAUSED. Review them in Ads Manager and turn them on there.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="create the objects (default: dry run)")
    ap.add_argument("--account", default=DEFAULT_ACCOUNT)
    ap.add_argument("--page", default=DEFAULT_PAGE)
    ap.add_argument("--pixel", default=DEFAULT_PIXEL)
    ap.add_argument("--countries", default="US,GB", type=lambda v: [c.strip().upper() for c in v.split(",") if c.strip()])
    ap.add_argument("--budget", type=int, default=700, help="daily budget in minor units (700 = 7 USD)")
    ap.add_argument("--start", default="2026-11-26")
    ap.add_argument("--end", default="2026-12-09")
    args = ap.parse_args()
    if not args.apply:
        for label, path, body in build(args.account, args.page, args.pixel, args.countries, args.budget, args.start, args.end):
            print(f"\n# {label}: POST {path}\n{json.dumps(body, indent=2, ensure_ascii=False)}")
        print("\nDry run: nothing was sent. Add --apply to create everything PAUSED.")
        return 0
    return asyncio.run(apply(args))


if __name__ == "__main__":
    raise SystemExit(main())
