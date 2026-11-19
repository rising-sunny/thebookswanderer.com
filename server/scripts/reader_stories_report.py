"""Take the two private, same-age snapshots for the 2026 reading stories pilot."""

import argparse
import asyncio
import json
import os
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import median

import httpx
from daily_social_post import GRAPH, NY, ROOT, STATE
from dotenv import load_dotenv
from fastapi import HTTPException
from services import pinterest

load_dotenv(ROOT / ".env")
WINDOWS = {
    "2026-11-20": ("baseline", "2026-11-06", "2026-11-19"),
    "2026-12-04": ("trial", "2026-11-20", "2026-12-03"),
}
DESTINATION = Path("/var/lib/tbw-reader-stories")
PIN_RECEIPTS = Path("/var/lib/tbw-once/scheduled-pins")


def numeric_values(rows):
    result = {}
    for row in rows:
        values = row.get("values") or []
        if values and isinstance(values[-1].get("value"), (int, float)):
            result[row["name"]] = values[-1]["value"]
    return result


def meta_get(client, path, params):
    try:
        response = client.get(f"{GRAPH}/{path}", params=params)
        response.raise_for_status()
        return response.json(), None
    except httpx.HTTPStatusError as exc:
        return {}, exc.response.status_code
    except (httpx.RequestError, ValueError):
        return {}, "unavailable"


def social_rows(client, start, end):
    results = {"facebook": [], "instagram": []}
    for post in json.loads(STATE.read_text()):
        if not start <= post["date"] <= end:
            continue
        for platform, rows in results.items():
            post_id = post.get(platform)
            if not post_id:
                continue
            row = {"id": post_id, "date": post["date"], "slug": post["slug"]}
            if platform == "facebook":
                data, error = meta_get(
                    client,
                    f"{post_id}/video_insights",
                    {"metric": "fb_reels_total_plays,post_video_avg_time_watched"},
                )
                row.update(numeric_values(data.get("data", [])))
            else:
                data, error = meta_get(
                    client, str(post_id), {"fields": "like_count,comments_count"}
                )
                row.update(
                    {k: data[k] for k in ("like_count", "comments_count") if k in data}
                )
            if error:
                row["collection_error"] = error
            rows.append(row)
    return results


async def pin_rows(start, end):
    listed = json.loads(Path(__file__).with_name("scheduled_pins.json").read_text())
    rows = []
    for post in listed:
        day = (
            datetime.fromisoformat(post["publish_at"]).astimezone(NY).date().isoformat()
        )
        if not start <= day <= end:
            continue
        receipt = PIN_RECEIPTS / post["id"]
        if not receipt.exists():
            rows.append({"date": day, "campaign": post["id"], "published": False})
            continue
        pin_id = receipt.read_text().strip()
        row = {"date": day, "id": pin_id, "campaign": post["id"], "published": True}
        try:
            data = await pinterest.api_request(
                "GET",
                f"/pins/{pin_id}/analytics",
                params={
                    "start_date": day,
                    "end_date": end,
                    "metric_types": "IMPRESSION,SAVE,OUTBOUND_CLICK",
                },
            )
            row.update(data.get("all", {}).get("summary_metrics", {}))
        except (HTTPException, httpx.RequestError, ValueError) as exc:
            row["collection_error"] = getattr(exc, "status_code", "unavailable")
        rows.append(row)
    return rows


def landing_sessions(start, end):
    # Attribution persists across subsequent pageviews. Count only visits to a campaign landing URL.
    database = ROOT / "data" / "store.db"
    query = """
        SELECT source,campaign,COUNT(*),COUNT(DISTINCT session_id) FROM live_events
        WHERE event_type='pageview' AND datetime(ts) >= ? AND datetime(ts) < ?
        AND lower(source) IN ('facebook','instagram','pinterest') AND path LIKE '%utm_campaign=%'
        AND (ua_class IS NULL OR ua_class NOT IN ('datacenter','server'))
        GROUP BY source,campaign ORDER BY source,campaign
    """
    stop = date.fromordinal(date.fromisoformat(end).toordinal() + 1)

    def utc_midnight(day):
        return (
            datetime.combine(day, datetime.min.time(), NY)
            .astimezone(UTC)
            .strftime("%Y-%m-%d %H:%M:%S")
        )

    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        return [
            {"source": s, "campaign": c, "pageviews": pv, "browser_ids": ids}
            for s, c, pv, ids in db.execute(
                query, (utc_midnight(date.fromisoformat(start)), utc_midnight(stop))
            )
        ]


def summary(rows):
    metrics = {
        "facebook": ["fb_reels_total_plays", "post_video_avg_time_watched"],
        "instagram": ["like_count", "comments_count"],
        "pinterest": ["IMPRESSION", "SAVE", "OUTBOUND_CLICK"],
    }
    result = {}
    for platform, keys in metrics.items():
        group = [r for r in rows[platform] if r.get("published", True)]
        result[platform] = {"posts": len(group)}
        for key in keys:
            values = [r[key] for r in group if isinstance(r.get(key), (int, float))]
            result[platform][key] = {
                "observed": len(values),
                "median_per_post": median(values) if values else None,
            }
            if key != "post_video_avg_time_watched":
                result[platform][key]["sum"] = sum(values) if values else None
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preview",
        choices=WINDOWS,
        help="read a snapshot without writing the scheduled report",
    )
    args = parser.parse_args()
    today = args.preview or datetime.now(NY).date().isoformat()
    if today not in WINDOWS:
        return
    label, start, end = WINDOWS[today]
    dest = DESTINATION / (label + ".json")
    if (
        not args.preview
        and dest.exists()
        and not json.loads(dest.read_text()).get("incomplete")
    ):
        return
    with httpx.Client(
        headers={"Authorization": "Bearer " + os.environ["FB_PAGE_TOKEN"]}, timeout=20
    ) as client:
        rows = social_rows(client, start, end)
    rows["pinterest"] = asyncio.run(pin_rows(start, end))
    incomplete = any("collection_error" in r for group in rows.values() for r in group)
    report = {
        "window": [start, end],
        "snapshot_utc": datetime.now(UTC).isoformat(),
        "incomplete": incomplete,
        "summary": summary(rows),
        "posts": rows,
        "tagged_landings": landing_sessions(start, end),
    }
    if args.preview:
        print(json.dumps(report["summary"]))
        return
    temp = dest.with_suffix(".tmp")
    temp.write_text(json.dumps(report, indent=2) + "\n")
    temp.replace(dest)


if __name__ == "__main__":
    main()
