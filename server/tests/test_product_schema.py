"""Offline SEO and storefront regression tests; no production DB/API calls.

Run from the repository root:
    server/.venv/bin/python -m unittest discover -s server/tests -v
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
import ssr
import i18n
from database import Base, get_db
from fastapi.testclient import TestClient
from models import Product, ProductVariant
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class Markup(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.documents = []
        self.microdata = []
        self.buffer = None
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if any(key in attrs for key in ("itemscope", "itemtype", "itemprop")):
            self.microdata.append(attrs)
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.buffer = ""

    def handle_data(self, data):
        if self.buffer is not None:
            self.buffer += data

    def handle_endtag(self, tag):
        if tag == "script" and self.buffer is not None:
            self.documents.append(json.loads(self.buffer))
            self.buffer = None

    def product(self):
        products = [doc for doc in self.documents if doc.get("@type") == "Product"]
        assert len(products) == 1, products
        return products[0]


DETAIL = {
    "id": 1, "slug": "reading-accessory", "title": "Reading accessory",
    "description": "An accessory for reading.", "price_usd": 9.99,
    "price_max_usd": 19.99, "image_url": "/assets/logo.webp",
    "supplier": "cj", "from_country": "CN", "cj_sku": "SUPPLIER-SKU",
    "variants": [
        {"id": 10, "name": "Small", "price_usd": 9.99, "cj_sku": "SKU-S",
         "image_url": "/assets/logo.webp"},
        {"id": 20, "name": "Large", "price_usd": 19.99, "cj_sku": "SKU-L",
         "image_url": "/assets/logo-hero.webp"},
    ],
}
CANONICAL = ssr.PUBLIC_BASE + "/products/reading-accessory"


class ProductSchemaTests(unittest.TestCase):
    def setUp(self):
        self.detail = copy.deepcopy(DETAIL)
        self.free_shipping = patch.object(main, "FREE_SHIPPING", True)
        self.free_shipping.start()
        self.addCleanup(self.free_shipping.stop)

    def render(self, **kwargs):
        page = ssr.render_product_page(self.detail, canonical=CANONICAL, **kwargs)
        return page, Markup(page)

    def test_one_product_without_duplicate_microdata(self):
        page, markup = self.render()
        self.assertEqual(markup.product()["@id"], CANONICAL + "#product")
        self.assertEqual(markup.microdata, [])
        self.assertIn('$9.99–$19.99 USD', page)
        self.assertEqual([d["@type"] for d in markup.documents], ["Product", "BreadcrumbList"])

    def test_variant_offers_have_exact_prices_skus_and_urls(self):
        _, markup = self.render()
        offers = markup.product()["offers"]
        self.assertEqual([o["@type"] for o in offers], ["Offer", "Offer"])
        self.assertEqual([o["price"] for o in offers], ["9.99", "19.99"])
        self.assertEqual([o["sku"] for o in offers], ["SKU-S", "SKU-L"])
        self.assertEqual([o["url"] for o in offers],
                         [CANONICAL + "?variant=10", CANONICAL + "?variant=20"])
        self.assertEqual(len({o["@id"] for o in offers}), 2)
        for offer in offers:
            self.assertEqual(offer["priceCurrency"], "USD")
            self.assertEqual(offer["availability"], "https://schema.org/InStock")
            self.assertIn("hasMerchantReturnPolicy", offer)
            self.assertIn("shippingDetails", offer)

    def test_selected_variant_matches_visible_price_and_image(self):
        page, markup = self.render(variant_id=20)
        product = markup.product()
        self.assertIn('<strong>$19.99 USD</strong>', page)
        self.assertEqual(product["sku"], "SKU-L")
        self.assertEqual(product["offers"]["price"], "19.99")
        self.assertEqual(product["offers"]["url"], CANONICAL + "?variant=20")
        self.assertEqual(product["image"][0], ssr.PUBLIC_BASE + "/assets/logo-hero.webp")

    def test_unknown_variant_preserves_available_offers(self):
        _, markup = self.render(variant_id=999)
        self.assertEqual(len(markup.product()["offers"]), 2)

    def test_same_price_variants_still_have_individual_offers(self):
        self.detail["price_max_usd"] = 9.99
        self.detail["variants"][1]["price_usd"] = 9.99
        page, markup = self.render()
        self.assertIn('<strong>$9.99 USD</strong>', page)
        self.assertEqual(len(markup.product()["offers"]), 2)

    def test_unvarianted_product_has_one_offer(self):
        self.detail.update(variants=[], price_max_usd=9.99)
        _, markup = self.render()
        offer = markup.product()["offers"]
        self.assertEqual(offer["@type"], "Offer")
        self.assertEqual(offer["url"], CANONICAL)
        self.assertEqual(offer["price"], "9.99")

    def test_unpriced_product_does_not_invent_an_offer(self):
        self.detail.update(variants=[], price_usd=None, price_max_usd=None)
        _, markup = self.render()
        self.assertNotIn("offers", markup.product())

    def test_no_fabricated_identifiers_or_social_proof(self):
        _, markup = self.render()
        product = markup.product()
        for key in ("brand", "mpn", "gtin", "gtin8", "gtin12", "gtin13", "gtin14",
                    "review", "aggregateRating"):
            self.assertNotIn(key, product)
        self.assertEqual(product["sku"], "SUPPLIER-SKU")

    def test_return_policy_does_not_claim_free_postage_or_keep_method(self):
        _, markup = self.render()
        policy = markup.product()["offers"][0]["hasMerchantReturnPolicy"]
        self.assertEqual(policy["merchantReturnDays"], 14)
        self.assertEqual(policy["returnPolicyCategory"],
                         "https://schema.org/MerchantReturnFiniteReturnWindow")
        self.assertNotIn("returnMethod", policy)
        self.assertNotIn("returnFees", policy)
        public = (ssr.SITE_ROOT / "shipping-returns.html").read_text()
        self.assertIn("14 days from delivery", public)
        self.assertIn("return postage would be yours to pay", public)
        self.assertIn("30 days of delivery", public)

    def test_only_us_has_a_known_included_rate_without_invented_times(self):
        _, markup = self.render()
        shipping = markup.product()["offers"][0]["shippingDetails"]
        self.assertEqual({s["shippingDestination"]["addressCountry"] for s in shipping},
                         {"US"})
        for row in shipping:
            self.assertEqual(row["shippingRate"],
                             {"@type": "MonetaryAmount", "value": 0, "currency": "USD"})
            self.assertNotIn("deliveryTime", row)

    def test_printify_and_cj_us_only_advertise_confirmed_us_rate(self):
        for supplier in ("printify", "cj"):
            with self.subTest(supplier=supplier):
                self.detail.update(supplier=supplier, from_country="US")
                _, markup = self.render()
                offer = markup.product()["offers"][0]
                self.assertIn("IN", offer["hasMerchantReturnPolicy"]["applicableCountry"])
                self.assertEqual([s["shippingDestination"]["addressCountry"]
                                  for s in offer["shippingDetails"]], ["US"])

    def test_lulu_does_not_advertise_free_international_rates(self):
        self.detail["supplier"] = "lulu"
        with patch.dict("os.environ", {"LULU_SHIP_COUNTRIES": "US,GB"}), \
                patch.object(main, "FREE_SHIPPING", False):
            _, markup = self.render()
        offer = markup.product()["offers"][0]
        self.assertIn("IN", offer["hasMerchantReturnPolicy"]["applicableCountry"])
        self.assertEqual({s["shippingDestination"]["addressCountry"]
                          for s in offer["shippingDetails"]}, {"US"})

    def test_paid_shipping_omits_unverified_rates(self):
        with patch.object(main, "FREE_SHIPPING", False):
            _, markup = self.render()
        for offer in markup.product()["offers"]:
            self.assertNotIn("shippingDetails", offer)

    def test_digital_does_not_invent_shipping_or_no_refund_policy(self):
        self.detail["supplier"] = "digital"
        _, markup = self.render()
        for offer in markup.product()["offers"]:
            self.assertNotIn("shippingDetails", offer)
            self.assertNotIn("hasMerchantReturnPolicy", offer)

    def test_spanish_keeps_one_product_and_local_variant_urls(self):
        canonical = ssr.PUBLIC_BASE + "/es/products/reading-accessory"
        page = ssr.render_product_page(self.detail, canonical=canonical, variant_id=20)
        page = i18n.localize(page, "es", "/products/reading-accessory")
        markup = Markup(page)
        self.assertEqual(markup.microdata, [])
        self.assertEqual(markup.product()["offers"]["url"], canonical + "?variant=20")
        self.assertEqual(markup.product()["offers"]["hasMerchantReturnPolicy"]["merchantReturnLink"],
                         ssr.PUBLIC_BASE + "/es/shipping-returns.html")

    def test_jsonld_cannot_be_broken_by_description_script_end(self):
        self.detail["description"] = 'Text </script><script>alert("x")</script>'
        page, markup = self.render()
        self.assertEqual(markup.product()["description"], self.detail["description"])
        self.assertNotIn('<script>alert("x")</script>', page)


class StorefrontRegressionTests(unittest.TestCase):
    def setUp(self):
        research_dir = tempfile.TemporaryDirectory()
        self.addCleanup(research_dir.cleanup)
        research_env = patch.dict(os.environ, {"COLLABORATORS_DATA_DIR": research_dir.name})
        research_env.start()
        self.addCleanup(research_env.stop)
        # Dependency overrides leave the actual catalog and store.db untouched.
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            for pid, supplier in enumerate(("cj", "printify", "lulu", "digital"), 1):
                p = Product(id=pid, slug=supplier + "-fixture", title=supplier + " fixture",
                            image_url="/assets/logo.webp", supplier=supplier, price_usd=9.99,
                            category="Bookmarks", description="Regression fixture")
                p.variants = [ProductVariant(id=pid * 10, name="Small", price_usd=9.99,
                                             image_url="/assets/logo.webp", cj_sku="SMALL"),
                              ProductVariant(id=pid * 10 + 1, name="Large", price_usd=19.99,
                                             image_url="/assets/logo-hero.webp", cj_sku="LARGE")]
                db.add(p)
            db.commit()

        def test_db():
            with self.sessions() as db:
                yield db

        self.previous_overrides = main.app.dependency_overrides.copy()
        main.app.dependency_overrides[get_db] = test_db
        self.addCleanup(self.restore)
        self.startup = patch.object(main, "init_db")
        self.startup.start()
        self.client = TestClient(main.app)
        self.client.__enter__()

    def restore(self):
        self.client.__exit__(None, None, None)
        self.startup.stop()
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(self.previous_overrides)
        self.engine.dispose()

    def test_storefront_and_catalog_routes(self):
        for path in ("/", "/es/", "/products/", "/es/products/", "/collections", "/sitemap.xml"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content)
        self.assertTrue(self.client.get("/api/health").json()["ok"])
        self.assertEqual(self.client.get("/api/products").json()["count"], 4)

    def test_product_pages_and_api_for_all_supplier_types(self):
        for pid, supplier in enumerate(("cj", "printify", "lulu", "digital"), 1):
            for prefix in ("", "/es"):
                with self.subTest(supplier=supplier, prefix=prefix):
                    response = self.client.get(f"{prefix}/products/{supplier}-fixture?variant={pid * 10 + 1}")
                    self.assertEqual(response.status_code, 200)
                    product = Markup(response.text).product()
                    self.assertEqual(product["offers"]["price"], "19.99")
                    self.assertIn(f"?variant={pid * 10 + 1}", product["offers"]["url"])
                    self.assertIn('<strong>$19.99 USD</strong>', response.text)
            detail = self.client.get(f"/api/products/{pid}").json()
            self.assertEqual(len(detail["variants"]), 2)

    def test_cart_preview_and_invalid_quantity(self):
        response = self.client.post("/api/cart/preview", json={"items": [
            {"product_id": 1, "variant_id": 11, "quantity": 2}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product_total"], 39.98)
        response = self.client.post("/api/cart/preview", json={"items": [
            {"product_id": 1, "quantity": 0}]})
        self.assertEqual(response.status_code, 422)

    def test_missing_product_and_legacy_redirect(self):
        self.assertEqual(self.client.get("/products/unknown").status_code, 404)
        response = self.client.get("/product.html?slug=cj-fixture", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.headers["location"].endswith("/products/cj-fixture"))

    def test_feed_variant_prices_match_landing_pages_without_fake_brand(self):
        response = self.client.get("/api/feeds/google-products.xml")
        self.assertEqual(response.status_code, 200)
        root = ET.fromstring(response.text)
        ns = {"g": "http://base.google.com/ns/1.0"}
        items = root.findall("channel/item")
        self.assertEqual(len(items), 6)  # digital excluded; three physical products x two variants
        for item in items:
            self.assertIsNone(item.find("g:brand", ns))
            link = item.findtext("link")
            page = self.client.get(link.replace(main.PUBLIC_BASE, ""))
            offer = Markup(page.text).product()["offers"]
            self.assertEqual(item.findtext("g:price", namespaces=ns), offer["price"] + " USD")
            if "printify" in link:
                self.assertEqual([s.findtext("g:country", namespaces=ns)
                                  for s in item.findall("g:shipping", ns)], ["US"])

    def test_paid_shipping_feed_does_not_advertise_free_cj_or_printify(self):
        with patch.object(main, "FREE_SHIPPING", False):
            root = ET.fromstring(self.client.get("/api/feeds/google-products.xml").text)
        ns = {"g": "http://base.google.com/ns/1.0"}
        for item in root.findall("channel/item"):
            rows = item.findall("g:shipping", ns)
            if "lulu" in item.findtext("link"):
                self.assertTrue(rows)
            else:
                self.assertEqual(rows, [])

    def test_feed_descriptions_use_the_product_page_shipping_wording(self):
        legacy = ("Free shipping to the United States, United Kingdom, Canada, Australia, "
                  "Germany, France, the Netherlands and Ireland.")
        with self.sessions() as db:
            db.get(Product, 3).description = "A printed journal. " + legacy
            db.commit()
        root = ET.fromstring(self.client.get("/api/feeds/google-products.xml").text)
        texts = [i.findtext("description") for i in root.findall("channel/item")
                 if "lulu" in i.findtext("link")]
        self.assertTrue(texts)
        for text in texts:
            self.assertNotIn("Canada", text)
            self.assertIn("Other destinations quoted before payment.", text)
        page = self.client.get("/api/products/by-slug/lulu-fixture").json()["description"]
        self.assertIn(texts[0].split(" Standard")[0], page)


if __name__ == "__main__":
    unittest.main()
