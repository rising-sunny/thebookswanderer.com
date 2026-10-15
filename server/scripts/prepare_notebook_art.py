"""Stage the two approved public-domain museum reproductions for notebook production.

Imports original image bytes and source metadata only. No listing, customer order,
provider product, or payment is created.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
NGA_IMAGE = 'https://api.nga.gov/iiif/d8fee2a3-3cc9-48ff-99a8-1755c07b12e2/full/full/0/default.jpg?attachment_filename=great_cinereous_owl_1945.8.351.jpg'


def install_image(client, source, slug, metadata):
    parsed = urlparse(source)
    if parsed.scheme != 'https' or parsed.hostname not in ('api.nga.gov', 'images.metmuseum.org', 'collectionapi.metmuseum.org'):
        raise ValueError('Unexpected museum image source')
    response = client.get(source)
    response.raise_for_status()
    data = response.content
    if len(data) > 48 * 1024 * 1024:
        raise ValueError('Museum image exceeds import limit')
    with Image.open(io.BytesIO(data)) as image:
        print(json.dumps({'museum_host':parsed.hostname,'format':image.format,'pixels':list(image.size)}),flush=True)
        if image.format != 'JPEG' or min(image.size) < 1000 or max(image.size) < 1500:
            raise ValueError('Original museum image is not suitable for printing')
        metadata['pixels'] = list(image.size)
        image.verify()
    metadata.update(image_source=source, sha256=hashlib.sha256(data).hexdigest())
    folder = ROOT / 'assets/products' / slug
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'artwork-original.jpg'
    pending = target.with_suffix('.tmp');pending.write_bytes(data);pending.replace(target)
    (folder / 'artwork-source.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'slug': slug, 'pixels': metadata['pixels'], 'sha256': metadata['sha256'], 'path': str(target.relative_to(ROOT))}), flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--import-art',action='store_true');args=parser.parse_args()
    if not args.import_art:
        print('Dry run: approved NGA owl and Met Lake Suwa; use --import-art to stage original reproductions.')
        return
    with httpx.Client(timeout=120, follow_redirects=False, headers={'User-Agent':'TheBooksWanderer/1.0 (public-domain print design)'}) as client:
        # The institution's object page explicitly marks this media public domain.
        install_image(client,NGA_IMAGE,'commonplace-book',{
            'title':'Great Cinereous Owl','artist':'Robert Havell after John James Audubon','date':'1837',
            'institution':'National Gallery of Art','accession':'1945.8.351',
            'source_page':'https://www.nga.gov/artworks/32492-great-cinereous-owl',
            'rights':'Public domain; object page states media is free and in the public domain',
            'credit':'National Gallery of Art, Washington. Gift of Mrs. Walter B. James.',
            'artwork_generated':False})
        r=client.get('https://collectionapi.metmuseum.org/public/collection/v1/objects/56240');r.raise_for_status();obj=r.json()
        print(json.dumps({k:obj.get(k) for k in ('objectID','title','artistDisplayName','isPublicDomain','artistWikidata_URL')}),flush=True)
        if obj.get('objectID')!=56240 or obj.get('isPublicDomain') is not True or 'Lake Suwa' not in obj.get('title','') or 'Hokusai' not in obj.get('artistDisplayName',''):
            raise ValueError('Met artwork identity or public-domain designation changed')
        install_image(client,obj['primaryImage'],'reading-society-notebook',{
            'title':obj['title'],'artist':obj['artistDisplayName'],'date':obj.get('objectDate'),
            'institution':'The Metropolitan Museum of Art','accession':obj.get('accessionNumber'),
            'source_page':'https://www.metmuseum.org/art/collection/search/56240',
            'rights':'Public Domain; Met Open Access CC0','rights_policy':'https://www.metmuseum.org/hubs/open-access',
            'credit':obj.get('creditLine'),'artwork_generated':False})
    print('Original public-domain artwork staged. No listings activated or orders created.')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(type(exc).__name__+': museum import failed; no product activated.')
        raise SystemExit(1)
