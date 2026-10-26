"""Homepage publication checks with an isolated database; no external writes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
import ssr
from database import Base
from models import Product, ProductVariant
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request


class HomepageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        for index, slug in enumerate(ssr.HOME_EDIT_SLUGS):
            product = Product(slug=slug, title=f'Live title {index}',
                              image_url=f'/assets/live-{index}.jpg', category='book-accessories',
                              price_usd=1, active=True)
            product.variants = [ProductVariant(name='Current', price_usd=31.25 + index),
                                ProductVariant(name='Retired', price_usd=0.01, active=False)]
            self.db.add(product)
        self.db.add(Product(slug='extra-piece', title='Extra live piece', price_usd=15, active=True))
        self.db.add(Product(slug='unpublished', title='PRIVATE DRAFT', price_usd=10, active=False))
        self.db.commit()

    def page(self, path='/'):
        request = Request({'type': 'http', 'method': 'GET', 'path': path,
                           'scheme': 'http', 'server': ('testserver', 80),
                           'headers': [], 'query_string': b''})
        response = main.home_page_ssr(request, self.db)
        self.assertEqual(response.status_code, 200)
        return response.body.decode()

    def test_live_prices_titles_images_and_only_six_featured_products(self):
        page = self.page()
        self.assertEqual(page.count('data-ssr-card="1"'), 6)
        self.assertIn('US$31.25', page)
        self.assertIn('Live title 0', page)
        self.assertIn('/assets/live-0.jpg', page)
        self.assertNotIn('US$27.99', page)  # never the prototype price snapshot
        self.assertNotIn('PRIVATE DRAFT', page)
        # the newest products open the shelf, marked as new
        self.assertLess(page.index('Extra live piece'), page.index('Live title 0'))
        self.assertIn('<span class="tag">New</span>', page)
        self.assertNotIn('US$0.01', page)

    def test_retired_product_is_replaced_and_price_changes_are_immediate(self):
        notebook = self.db.query(Product).filter_by(slug='reading-society-notebook').one()
        notebook.active = False
        book = self.db.query(Product).filter_by(slug='commonplace-book').one()
        book.variants[0].price_usd = 42.75
        self.db.commit()
        page = self.page()
        self.assertEqual(page.count('data-ssr-card="1"'), 6)
        self.assertNotIn('href="/products/reading-society-notebook"', page)
        self.assertIn('Extra live piece', page)
        self.assertIn('US$42.75', page)

    def test_localized_navigation_christmas_and_search_metadata(self):
        for path in ('/', '/es/'):
            with self.subTest(path=path):
                page = self.page(path)
                self.assertNotIn('tbw_test', page)
                self.assertNotIn('noindex', page)
                self.assertIn('id="featured"', page)
                self.assertIn('href="/assets/products/home-atelier/home.css?v=2"', page)
                self.assertIn('src="/track.js?v=6"', page)
                self.assertIn('src="/cart.js?v=4"', page)
                self.assertIn('id="newsletterForm"', page)
                self.assertIn('hreflang="en"', page)
                self.assertIn('hreflang="es"', page)
                if path == '/es/':
                    self.assertIn('<html lang="es">', page)
                    self.assertIn('La Navidad está cerca', page)
                    self.assertIn('Un poco más de magia', page)
                    self.assertIn('href="/es/products/commonplace-book"', page)
                    self.assertIn('data-lang-switch="en"', page)
                    self.assertIn('href="/reto-de-lectura-2027/"', page)
                    self.assertIn('href="/guides/regalos-pequenos-para-lectores/"', page)
                    self.assertIn('rel="canonical" href="https://thebookswanderer.com/es/"', page)
                else:
                    self.assertIn('Christmas is coming', page)
                    self.assertIn('data-lang-switch="es"', page)

    def test_empty_catalog_and_product_text_are_safe(self):
        product = self.db.query(Product).filter_by(slug='reading-society-notebook').one()
        product.title = '<script>alert("bad")</script>'
        self.db.commit()
        page = self.page()
        self.assertNotIn('<script>alert("bad")</script>', page)
        self.assertIn('&lt;script&gt;', page)
        self.db.query(Product).update({'active': False})
        self.db.commit()
        self.assertIn('Nothing on this shelf just yet.', self.page())


if __name__ == '__main__':
    unittest.main()
