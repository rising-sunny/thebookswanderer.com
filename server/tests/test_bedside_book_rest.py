"""Offline supplier-variant and publication guards; no orders or payments."""
import asyncio
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Product,ProductVariant
import publish_bedside_book_rest as rest


def details():
    return {'pid':rest.PID,'productSku':'CJYD2913942','variants':[
        {'vid':'other','variantSku':'OTHER','variantKey':'Walnut','variantSellPrice':1},
        {'vid':rest.VID,'variantSku':rest.SKU,'variantKey':'Wood Color','variantSellPrice':2.05}]}


class Publication(unittest.TestCase):
    def setUp(self):
        engine=create_engine('sqlite://');self.addCleanup(engine.dispose);Base.metadata.create_all(engine)
        self.db=sessionmaker(bind=engine)();self.addCleanup(self.db.close)
        self.spec=json.loads(rest.SPEC.read_text())

    def test_rerun_preserves_other_listing_and_supplier_and_variant_ids(self):
        other=Product(slug='existing',title='Existing',active=True,price_usd=9.99)
        self.db.add(other);self.db.commit()
        first=rest.stage_product(self.db,self.spec,2.05,publish=True);self.db.commit()
        ids=(first.id,first.default_variant().id)
        again=rest.stage_product(self.db,self.spec,2.05,publish=True);self.db.commit()
        self.assertEqual((again.id,again.default_variant().id),ids)
        self.assertEqual((again.cj_pid,again.default_variant().cj_vid,again.default_variant().cj_sku),(rest.PID,rest.VID,rest.SKU))
        self.assertEqual((again.active,again.price_usd,again.default_variant().price_usd),(True,24.99,24.99))
        self.assertEqual(self.db.query(Product).count(),2);self.assertEqual(self.db.query(ProductVariant).count(),1)
        self.assertEqual((other.active,other.price_usd),(True,9.99))

    def test_wrong_supplier_reference_or_unapproved_price_cannot_be_written(self):
        for key,value in [('vid','wrong'),('sku','OTHER'),('price_usd',29.99)]:
            spec=copy.deepcopy(self.spec);spec[key]=value
            with self.assertRaises(ValueError):rest.stage_product(self.db,spec,2.05,publish=True)
        self.assertEqual(self.db.query(Product).count(),0)

    def test_duplicate_product_and_slug_collision_block_publication(self):
        self.db.add(Product(slug='existing',title='Existing',cj_pid=rest.PID));self.db.commit()
        with self.assertRaisesRegex(ValueError,'different store listing'):rest.stage_product(self.db,self.spec,2.05,publish=True)
        self.db.rollback()
        self.db.add(Product(slug=rest.SLUG,title='Another product',supplier='lulu',cj_pid='other'));self.db.commit()
        with self.assertRaisesRegex(ValueError,'another supplier'):rest.stage_product(self.db,self.spec,2.05,publish=True)

    def test_supplier_variant_or_cost_change_blocks_selection(self):
        self.assertEqual(rest.selected_variant(details())['vid'],rest.VID)
        for key,value in [('variantSku','OTHER'),('variantKey','Walnut'),('variantSellPrice',4),('variantSellPrice',float('nan'))]:
            d=details();d['variants'][1][key]=value
            with self.assertRaises(ValueError):rest.selected_variant(d)

    def test_reviewed_images_and_bilingual_copy_are_consistent(self):
        spec=rest.read_spec()
        self.assertEqual(len([spec['image_url'],*spec['gallery']]),2)
        translations=json.loads((rest.ROOT/'i18n/products_es.json').read_text())
        self.assertEqual(translations[rest.SLUG],spec['es'])


class SupplierGates(unittest.IsolatedAsyncioTestCase):
    async def test_no_stock_blocks_before_freight(self):
        with patch.object(rest.cj,'get_product_details',AsyncMock(return_value=details())),patch.object(rest.cj,'_request',AsyncMock(return_value=[{'countryCode':'CN','totalInventoryNum':0}])),patch.object(rest.cj,'freight_calculate',AsyncMock()) as freight,patch.object(rest.asyncio,'sleep',AsyncMock()):
            with self.assertRaisesRegex(ValueError,'no available China stock'):await rest.validate_supplier()
            freight.assert_not_awaited()

    async def test_actual_checkout_carrier_must_fit_landed_cost_limit(self):
        options=[{'logisticName':'Cheap but slow','logisticPrice':12,'totalPostageFee':12,'logisticAging':'12-20'}, {'logisticName':'Faster','logisticPrice':14.50,'totalPostageFee':14.50,'logisticAging':'4-6'}]
        with patch.object(rest.cj,'get_product_details',AsyncMock(return_value=details())),patch.object(rest.cj,'_request',AsyncMock(return_value=[{'countryCode':'CN','totalInventoryNum':10}])),patch.object(rest.cj,'freight_calculate',AsyncMock(return_value=options)),patch.object(rest.asyncio,'sleep',AsyncMock()):
            with self.assertRaisesRegex(ValueError,'Checkout carrier exceeds'):await rest.validate_supplier()


if __name__=='__main__':unittest.main()
