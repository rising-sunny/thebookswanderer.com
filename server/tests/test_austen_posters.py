"""The Austen poster script builds four Printify products from the annotated poster, with only the sizes the art can carry."""
import asyncio
import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from services import printify

spec = importlib.util.spec_from_file_location("create_printify_austen_posters", ROOT / "scripts" / "create_printify_austen_posters.py")
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

TITLES = ["11″ x 14″ / Matte", "12\" x 16\" / Matte", "12″ x 18″ / Matte", "16″ x 20″ / Matte", "16″ x 24″ / Matte", "18″ x 24″ / Matte", "24″ x 36″ / Matte"]
SOURCE = {
    "blueprint_id": 282, "print_provider_id": 99, "title": "src", "description": "d", "tags": [],
    "variants": [{"id": 100 + i, "title": t, "price": 2500, "is_enabled": True} for i, t in enumerate(TITLES)],
    "print_areas": [
        {"variant_ids": [100, 103], "placeholders": [{"position": "front", "images": [{"id": "x", "x": .5, "y": .5, "scale": 1, "angle": 0, "width": 3600, "height": 4500}]}]},
        {"variant_ids": [101, 105], "placeholders": [{"position": "front", "images": [{"id": "x", "x": .5, "y": .5, "scale": 1, "angle": 0, "width": 3600, "height": 4800}]}]},
        {"variant_ids": [102, 104, 106], "placeholders": [{"position": "front", "images": [{"id": "x", "x": .5, "y": .5, "scale": 1, "angle": 0, "width": 2400, "height": 3600}]}]},
    ],
}


class AustenPostersTests(TestCase):
    def test_slug_files_exist_in_the_repository(self):
        for slug, title, description in script.POSTERS:
            self.assertLessEqual(len(title), 140)
            for key in ("3x4", "4x5"):
                self.assertTrue((ROOT.parent / "assets" / "products" / slug / f"print-{key}.jpg").is_file(), (slug, key))

    def test_apply_creates_four_products_with_only_the_allowed_sizes(self):
        calls = []

        async def fake(method, path, body=None):
            calls.append((method, path, body))
            if method == "GET": return SOURCE
            if path.endswith("uploads/images.json") or path.endswith("/uploads/images.json"): return {"id": f"up{len(calls)}", "width": 1, "height": 1}
            return {"id": f"prod{len(calls)}"}

        with patch.object(printify, "_request", fake), patch.object(printify, "configured", lambda: True), \
                patch.object(printify, "shop_id", lambda: "shop"), redirect_stdout(io.StringIO()):
            self.assertEqual(asyncio.run(script.main(True)), 0)
        created = [c for c in calls if c[0] == "POST" and c[1].endswith("/products.json")]
        self.assertEqual(len(created), 4)
        for (_, _, body), (slug, title, _) in zip(created, script.POSTERS):
            self.assertEqual(body["title"], title)
            self.assertEqual(body["tags"], script.TAGS)
            enabled = [v["id"] for v in body["variants"] if v["is_enabled"]]
            self.assertEqual(sorted(enabled), [100, 101, 103, 105])   # 11x14, 12x16, 16x20, 18x24 only
        uploads = [c[2]["url"] for c in calls if c[1].endswith("uploads/images.json")]
        self.assertTrue(all(u.endswith(("print-3x4.jpg", "print-4x5.jpg")) for u in uploads))
        self.assertEqual(len(uploads), 8)

    def test_dry_run_creates_nothing(self):
        calls = []

        async def fake(method, path, body=None):
            calls.append(method); return SOURCE

        with patch.object(printify, "_request", fake), patch.object(printify, "configured", lambda: True), \
                patch.object(printify, "shop_id", lambda: "shop"), redirect_stdout(io.StringIO()):
            self.assertEqual(asyncio.run(script.main(False)), 0)
        self.assertEqual(set(calls), {"GET"})


if __name__ == "__main__":
    main()
