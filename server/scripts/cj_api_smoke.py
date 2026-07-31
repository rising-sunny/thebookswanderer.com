"""
Smoke-test CJ API from any machine with CJ_API_KEY in server/.env.

  cd server
  .venv/Scripts/python scripts/cj_api_smoke.py
  .venv/Scripts/python scripts/cj_api_smoke.py CJJT1393689
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


async def main() -> None:
    from services import cj

    if not cj.is_configured():
        print("FAIL: CJ_API_KEY missing in .env")
        print("  Copy server/.env.example → server/.env and set CJ_API_KEY")
        raise SystemExit(1)

    sku = (sys.argv[1] if len(sys.argv) > 1 else "CJJT1393689").strip()
    print("auth…")
    tok = await cj.get_access_token()
    print("  accessToken ok", f"({len(tok)} chars)")

    print("query productSku=", sku, "features=enable_video…")
    details = await cj.get_product_details(
        product_sku=sku,
        features=["enable_video"],
    )
    print("  pid", details.get("pid"))
    print("  name", details.get("productNameEn"))
    print("  variants", len(details.get("variants") or []))
    print("  productVideo", details.get("productVideo"))

    pid = details.get("pid")
    if pid:
        print("queryVideosByProductId…")
        try:
            vids = await cj.query_videos_by_product_id(str(pid))
            print("  videos", len(vids))
            for v in vids[:5]:
                print(
                    "   -",
                    v.get("videoNumber"),
                    "dur=",
                    v.get("duration"),
                    (v.get("videoUrl") or "")[:70],
                )
        except cj.CJError as e:
            print("  videos skip:", e)

    print("OK — CJ API reachable from this machine")


if __name__ == "__main__":
    asyncio.run(main())
