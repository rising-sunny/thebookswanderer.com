#!/usr/bin/env python3
"""Install the private photo publisher. Never publishes a post."""
import getpass
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import httpx
from dotenv import dotenv_values

FILES = json.loads('{"server/scripts/static_social_post.py": "#!/usr/bin/env python3\\n\\"\\"\\"Publish one approved Reading Society image to Facebook and Instagram.\\n\\nDry run by default. Credentials remain on the VPS. A durable journal blocks\\nautomatic retries after an uncertain write; it never runs the daily reel job.\\n\\"\\"\\"\\nimport argparse\\nimport fcntl\\nimport hashlib\\nimport io\\nimport json\\nimport os\\nfrom pathlib import Path\\nimport tempfile\\nimport time\\nfrom urllib.parse import urljoin, urlsplit\\n\\nimport httpx\\nfrom dotenv import dotenv_values\\nfrom PIL import Image\\n\\nSTORE = \\"https://thebookswanderer.com\\"\\nGRAPH = \\"https://graph.facebook.com/v21.0\\"\\nPAGE = \\"1200587819810293\\"\\nINSTAGRAM = \\"17841443635177157\\"\\nCAMPAIGN = \\"reading_society_tote_photo_20261019\\"\\nSLUG = \\"reading-society-tote\\"\\nTEXT = (\\"Good books. Long conversations.\\\\n\\\\n\\"\\n        \\"Meet The Reading Society tote. Make a little room for the paperback \\"\\n        \\"that goes everywhere with you.\\\\n\\\\nWhat are you reading lately?\\")\\nFB_TEXT = TEXT + \\"\\\\n\\\\n\\" + STORE + \\"/products/\\" + SLUG\\nIG_TEXT = TEXT + (\\"\\\\n\\\\nExplore via the link in our bio.\\\\n\\\\n\\"\\n                  \\"#TheBooksWanderer #TheReadingSociety #BookLovers #ReadingLife\\")\\n\\n\\nclass SafeError(Exception):\\n    pass\\n\\n\\ndef owned_url(value):\\n    if not isinstance(value, str) or not value.strip():\\n        raise SafeError(\\"El producto no tiene una imagen p\\u00fablica.\\")\\n    url = urljoin(STORE + \\"/\\", value)\\n    parsed = urlsplit(url)\\n    if (parsed.scheme != \\"https\\" or parsed.hostname != \\"thebookswanderer.com\\"\\n            or parsed.username or parsed.password or parsed.port not in (None, 443)\\n            or parsed.query or parsed.fragment):\\n        raise SafeError(\\"La imagen debe ser una URL HTTPS de la tienda sin par\\u00e1metros.\\")\\n    return url\\n\\n\\ndef preflight(client):\\n    response = client.get(STORE + \\"/api/products/by-slug/\\" + SLUG)\\n    if response.status_code != 200:\\n        raise SafeError(f\\"Producto no disponible: HTTP {response.status_code}.\\")\\n    product = response.json()\\n    if not isinstance(product, dict):\\n        raise SafeError(\\"Respuesta de producto no v\\u00e1lida.\\")\\n    title = str(product.get(\\"title\\") or product.get(\\"name\\") or \\"\\")\\n    if \\"tote\\" not in title.lower() or \\"reading society\\" not in title.lower():\\n        raise SafeError(\\"El producto actual no coincide con la tote Reading Society.\\")\\n    image_url = owned_url(product.get(\\"image_url\\"))\\n    with client.stream(\\"GET\\", image_url) as response:\\n        if response.status_code != 200:\\n            raise SafeError(f\\"Imagen no disponible: HTTP {response.status_code}.\\")\\n        content = bytearray()\\n        for chunk in response.iter_bytes():\\n            content.extend(chunk)\\n            if len(content) > 8 * 1024 * 1024:\\n                raise SafeError(\\"La imagen supera 8 MB.\\")\\n    with Image.open(io.BytesIO(content)) as picture:\\n        width, height = picture.size\\n        if (picture.format != \\"JPEG\\" or not 320 <= width <= 1440\\n                or not 0.8 <= width / height <= 1.91):\\n            raise SafeError(\\"La imagen requiere un JPEG de 320\\u20131440 px de ancho \\"\\n                            \\"y proporci\\u00f3n entre 4:5 y 1.91:1.\\")\\n        picture.verify()\\n    return {\\"product\\": title, \\"image_url\\": image_url,\\n            \\"image_sha256\\": hashlib.sha256(content).hexdigest(),\\n            \\"facebook_caption\\": FB_TEXT, \\"instagram_caption\\": IG_TEXT}\\n\\n\\ndef graph(client, token, method, path, **kwargs):\\n    response = client.request(method, GRAPH + \\"/\\" + path,\\n                              headers={\\"Authorization\\": \\"Bearer \\" + token}, **kwargs)\\n    try:\\n        data = response.json()\\n    except ValueError:\\n        raise SafeError(f\\"Meta devolvi\\u00f3 una respuesta no v\\u00e1lida: HTTP {response.status_code}.\\")\\n    if response.status_code != 200 or not isinstance(data, dict) or \\"error\\" in data:\\n        error = data.get(\\"error\\", {}) if isinstance(data, dict) else {}\\n        raise SafeError(f\\"Meta: HTTP {response.status_code}; c\\u00f3digo {error.get(\'code\')}; \\"\\n                        f\\"subc\\u00f3digo {error.get(\'error_subcode\')}. Detalles ocultos.\\")\\n    return data\\n\\n\\ndef save(path, value):\\n    descriptor, temporary = tempfile.mkstemp(prefix=\\".social-\\", dir=path.parent)\\n    try:\\n        with os.fdopen(descriptor, \\"w\\") as handle:\\n            json.dump(value, handle, ensure_ascii=False, indent=2)\\n            handle.flush()\\n            os.fsync(handle.fileno())\\n        os.replace(temporary, path)\\n        directory = os.open(path.parent, os.O_RDONLY)\\n        try:\\n            os.fsync(directory)\\n        finally:\\n            os.close(directory)\\n    finally:\\n        if os.path.exists(temporary):\\n            os.unlink(temporary)\\n\\n\\ndef write_once(path, journal, network, operation, action):\\n    record = journal[network]\\n    record[\\"state\\"] = \\"uncertain\\"\\n    record[\\"operation\\"] = operation\\n    save(path, journal)\\n    result = action()\\n    identifier = result.get(\\"id\\")\\n    if not isinstance(identifier, str) or not identifier.strip():\\n        raise SafeError(\\"Meta no confirm\\u00f3 un ID. No repitas la publicaci\\u00f3n.\\")\\n    return result\\n\\n\\ndef publish(client, token, payload, path, journal):\\n    for network in (\\"facebook\\", \\"instagram\\"):\\n        if journal[network][\\"state\\"] == \\"uncertain\\":\\n            raise SafeError(f\\"Hay una escritura incierta en {network}. \\"\\n                            \\"Conserva el registro; revisaremos Meta antes de repetir.\\")\\n    page = graph(client, token, \\"GET\\", PAGE,\\n                 params={\\"fields\\": \\"id,name,instagram_business_account\\"})\\n    if (page.get(\\"id\\") != PAGE\\n            or page.get(\\"instagram_business_account\\", {}).get(\\"id\\") != INSTAGRAM):\\n        raise SafeError(\\"La p\\u00e1gina o la cuenta vinculada no coincide.\\")\\n    ig = graph(client, token, \\"GET\\", INSTAGRAM, params={\\"fields\\": \\"id,username\\"})\\n    if ig.get(\\"username\\") != \\"thebooks.wanderer\\":\\n        raise SafeError(\\"La cuenta Instagram no coincide.\\")\\n    fb = journal[\\"facebook\\"]\\n    if fb[\\"state\\"] != \\"published\\":\\n        result = write_once(path, journal, \\"facebook\\", \\"publish_photo\\", lambda: graph(\\n            client, token, \\"POST\\", PAGE + \\"/photos\\", data={\\n                \\"url\\": payload[\\"image_url\\"], \\"message\\": FB_TEXT, \\"published\\": \\"true\\"}))\\n        fb.update(state=\\"published\\", photo_id=result[\\"id\\"],\\n                  post_id=result.get(\\"post_id\\"),\\n                  url=\\"https://www.facebook.com/\\" + str(result.get(\\"post_id\\") or result[\\"id\\"]))\\n        save(path, journal)\\n        print(\\"Facebook: foto publicada. \\" + fb[\\"url\\"], flush=True)\\n    record = journal[\\"instagram\\"]\\n    if record[\\"state\\"] == \\"published\\":\\n        return\\n    if not record.get(\\"container_id\\"):\\n        result = write_once(path, journal, \\"instagram\\", \\"create_image_container\\", lambda: graph(\\n            client, token, \\"POST\\", INSTAGRAM + \\"/media\\", data={\\n                \\"image_url\\": payload[\\"image_url\\"], \\"caption\\": IG_TEXT}))\\n        record.update(state=\\"container_created\\", container_id=result[\\"id\\"])\\n        save(path, journal)\\n    for _ in range(10):\\n        status = graph(client, token, \\"GET\\", record[\\"container_id\\"],\\n                       params={\\"fields\\": \\"status_code\\"}).get(\\"status_code\\")\\n        if status == \\"FINISHED\\":\\n            break\\n        if status in (\\"ERROR\\", \\"EXPIRED\\", \\"PUBLISHED\\"):\\n            raise SafeError(f\\"Contenedor Instagram: {status}. Conserva el registro para revisi\\u00f3n.\\")\\n        time.sleep(3)\\n    else:\\n        raise SafeError(\\"Instagram sigue procesando la foto. Puedes repetir el mismo comando: \\"\\n                        \\"reutilizar\\u00e1 el contenedor y omitir\\u00e1 Facebook.\\")\\n    result = write_once(path, journal, \\"instagram\\", \\"publish_image\\", lambda: graph(\\n        client, token, \\"POST\\", INSTAGRAM + \\"/media_publish\\",\\n        data={\\"creation_id\\": record[\\"container_id\\"]}))\\n    record.update(state=\\"published\\", media_id=result[\\"id\\"])\\n    save(path, journal)\\n    print(\\"Instagram: imagen publicada. ID: \\" + result[\\"id\\"], flush=True)\\n    # Publication is already persisted even if this optional permalink lookup fails.\\n    try:\\n        info = graph(client, token, \\"GET\\", result[\\"id\\"], params={\\"fields\\": \\"permalink,media_type\\"})\\n        record.update(url=info.get(\\"permalink\\"), media_type=info.get(\\"media_type\\"))\\n        save(path, journal)\\n    except (SafeError, httpx.HTTPError):\\n        pass\\n\\n\\ndef main():\\n    parser = argparse.ArgumentParser(description=__doc__)\\n    parser.add_argument(\\"--publish\\", action=\\"store_true\\")\\n    parser.add_argument(\\"--server-root\\", type=Path,\\n                        default=Path(\\"/var/www/thebookswanderer.com/server\\"))\\n    args = parser.parse_args()\\n    with httpx.Client(timeout=30, follow_redirects=False) as client:\\n        if not args.publish:\\n            print(json.dumps({\\"mode\\": \\"preview\\", **preflight(client)}, ensure_ascii=False, indent=2))\\n            return\\n        env = dotenv_values(args.server_root / \\".env\\")\\n        token = (env.get(\\"FB_PAGE_TOKEN\\") or \\"\\").strip()\\n        if (env.get(\\"FB_PAGE_ID\\") or \\"\\").strip() != PAGE or not token:\\n            raise SafeError(\\"Faltan credenciales de la p\\u00e1gina esperada en .env.\\")\\n        directory = args.server_root / \\"data\\" / \\"static-social-posts\\"\\n        directory.mkdir(mode=0o700, parents=True, exist_ok=True)\\n        lock = os.open(directory / (CAMPAIGN + \\".lock\\"), os.O_CREAT | os.O_RDWR, 0o600)\\n        with os.fdopen(lock, \\"w\\") as handle:\\n            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)\\n            path = directory / (CAMPAIGN + \\".json\\")\\n            if path.exists():\\n                journal = json.loads(path.read_text())\\n            else:\\n                journal = {\\"campaign\\": CAMPAIGN, \\"payload\\": preflight(client),\\n                           \\"facebook\\": {\\"state\\": \\"ready\\"}, \\"instagram\\": {\\"state\\": \\"ready\\"}}\\n                save(path, journal)\\n            if not all(journal[key][\\"state\\"] == \\"published\\" for key in (\\"facebook\\", \\"instagram\\")):\\n                fresh = preflight(client)\\n                if fresh != journal[\\"payload\\"]:\\n                    raise SafeError(\\"El producto o la imagen cambi\\u00f3. Revisa el registro antes de publicar.\\")\\n                publish(client, token, journal[\\"payload\\"], path, journal)\\n            print(json.dumps({key: journal[key] for key in (\\"campaign\\", \\"facebook\\", \\"instagram\\")},\\n                             ensure_ascii=False, indent=2))\\n\\n\\nif __name__ == \\"__main__\\":\\n    try:\\n        main()\\n    except KeyboardInterrupt:\\n        raise SystemExit(\\"Interrumpido. Conserva el registro antes de repetir.\\")\\n    except Exception as exc:\\n        message = str(exc) if isinstance(exc, SafeError) else type(exc).__name__\\n        raise SystemExit(\\"Publicaci\\u00f3n detenida: \\" + message + \\"\\\\nNo borres el registro de publicaci\\u00f3n.\\")\\n", "server/scripts/social_publisher_api.py": "\\"\\"\\"Private HTTPS photo publisher; run with one uvicorn worker behind nginx.\\"\\"\\"\\nimport fcntl\\nimport hashlib\\nimport importlib.util\\nimport io\\nimport json\\nimport os\\nfrom pathlib import Path\\nimport re\\nimport secrets\\n\\nfrom fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request\\nfrom fastapi.responses import JSONResponse\\nimport httpx\\nfrom PIL import Image\\nfrom pydantic import BaseModel, ConfigDict, Field\\nfrom dotenv import dotenv_values\\n\\nROOT = Path(os.environ.get(\\"TBW_SERVER_ROOT\\", \\"/var/www/thebookswanderer.com/server\\"))\\nDATA = Path(os.environ.get(\\"TBW_SOCIAL_DATA\\", \\"/var/lib/tbw-social-publisher\\"))\\nKEY = Path(os.environ.get(\\"TBW_SOCIAL_KEY_FILE\\", \\"/etc/tbw-social-publisher/key\\"))\\nCORE = Path(__file__).with_name(\\"static_social_post.py\\")\\napp = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)\\n\\n\\n@app.on_event(\\"startup\\")\\ndef reconcile_interrupted_jobs():\\n    # A restart never resubmits a write whose outcome could be unknown.\\n    for path in DATA.glob(\\"*.json\\"):\\n        record = json.loads(path.read_text())\\n        if record.get(\\"job\\") == \\"publishing\\":\\n            record[\\"job\\"] = \\"review_required\\"\\n            record[\\"error\\"] = \\"ServiceInterrupted\\"\\n            core().save(path, record)\\n\\n\\ndef core():\\n    # Each request gets its own namespace; no shared caption or campaign globals.\\n    spec = importlib.util.spec_from_file_location(\\"private_photo_core\\", CORE)\\n    module = importlib.util.module_from_spec(spec)\\n    spec.loader.exec_module(module)\\n    return module\\n\\n\\ndef authorize(request: Request):\\n    try:\\n        key = KEY.read_text().strip()\\n    except OSError:\\n        raise HTTPException(503, \\"Publicador no configurado\\")\\n    supplied = request.headers.get(\\"authorization\\", \\"\\")\\n    if len(key) < 32 or not secrets.compare_digest(supplied.encode(), (\\"Bearer \\" + key).encode()):\\n        raise HTTPException(401, \\"No autorizado\\")\\n\\n\\ndef credentials():\\n    env = dotenv_values(Path(os.environ.get(\\"TBW_SOCIAL_META_ENV\\", str(ROOT / \\".env\\"))))\\n    token = (env.get(\\"FB_PAGE_TOKEN\\") or \\"\\").strip()\\n    if not token or (env.get(\\"FB_PAGE_ID\\") or \\"\\").strip() != core().PAGE:\\n        raise HTTPException(503, \\"Faltan credenciales Meta de la p\\u00e1gina esperada\\")\\n    return token\\n\\n\\nclass Draft(BaseModel):\\n    model_config = ConfigDict(extra=\\"forbid\\")\\n    campaign: str = Field(pattern=r\\"^[a-z0-9][a-z0-9_-]{2,79}$\\")\\n    slug: str = Field(pattern=r\\"^[a-z0-9][a-z0-9-]{1,119}$\\")\\n    facebook_caption: str = Field(min_length=1, max_length=2000)\\n    instagram_caption: str = Field(min_length=1, max_length=2200)\\n\\n\\ndef journal_path(campaign):\\n    if not re.fullmatch(r\\"[a-z0-9][a-z0-9_-]{2,79}\\", campaign):\\n        raise HTTPException(422, \\"Referencia no v\\u00e1lida\\")\\n    return DATA / (campaign + \\".json\\")\\n\\n\\ndef image_preflight(client, draft, module):\\n    response = client.get(module.STORE + \\"/api/products/by-slug/\\" + draft.slug)\\n    if response.status_code != 200:\\n        raise ValueError(\\"Producto no disponible\\")\\n    product = response.json()\\n    if not isinstance(product, dict) or not (product.get(\\"name\\") or product.get(\\"title\\")):\\n        raise ValueError(\\"Producto no v\\u00e1lido\\")\\n    url = module.owned_url(product.get(\\"image_url\\"))\\n    content = bytearray()\\n    with client.stream(\\"GET\\", url) as image:\\n        if image.status_code != 200:\\n            raise ValueError(\\"Imagen no disponible\\")\\n        for chunk in image.iter_bytes():\\n            content.extend(chunk)\\n            if len(content) > 8 * 1024 * 1024:\\n                raise ValueError(\\"Imagen mayor de 8 MB\\")\\n    with Image.open(io.BytesIO(content)) as picture:\\n        width, height = picture.size\\n        if picture.format != \\"JPEG\\" or not 320 <= width <= 1440 or not 0.8 <= width / height <= 1.91:\\n            raise ValueError(\\"Se requiere JPEG compatible con Instagram; no se modifica la imagen\\")\\n        picture.verify()\\n    return {\\"product\\": product.get(\\"name\\") or product.get(\\"title\\"), \\"image_url\\": url,\\n            \\"image_sha256\\": hashlib.sha256(content).hexdigest(),\\n            \\"facebook_caption\\": draft.facebook_caption, \\"instagram_caption\\": draft.instagram_caption}\\n\\n\\n@app.get(\\"/health\\", dependencies=[Depends(authorize)])\\ndef health():\\n    credentials()\\n    return {\\"service\\": \\"tbw-social-publisher\\", \\"ready\\": True, \\"format\\": \\"photo\\",\\n            \\"networks\\": [\\"facebook\\", \\"instagram\\"], \\"publishes_on_health_check\\": False}\\n\\n\\n@app.post(\\"/drafts\\", dependencies=[Depends(authorize)])\\ndef create_draft(draft: Draft):\\n    module = core()\\n    path = journal_path(draft.campaign)\\n    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)\\n    descriptor = os.open(DATA / \\".drafts.lock\\", os.O_CREAT | os.O_RDWR, 0o600)\\n    with os.fdopen(descriptor, \\"w\\") as lock:\\n        fcntl.flock(lock, fcntl.LOCK_EX)\\n        if path.exists():\\n            previous = json.loads(path.read_text())\\n            if previous[\\"request\\"] != draft.model_dump():\\n                raise HTTPException(409, \\"La referencia ya tiene otro contenido\\")\\n            return previous\\n        try:\\n            with httpx.Client(timeout=20, follow_redirects=False) as client:\\n                payload = image_preflight(client, draft, module)\\n        except Exception:\\n            raise HTTPException(422, \\"No se pudo validar el producto y su JPEG p\\u00fablico. No se public\\u00f3 nada.\\")\\n        record = {\\"campaign\\": draft.campaign, \\"request\\": draft.model_dump(), \\"payload\\": payload,\\n                  \\"job\\": \\"draft\\", \\"facebook\\": {\\"state\\": \\"ready\\"}, \\"instagram\\": {\\"state\\": \\"ready\\"}}\\n        module.save(path, record)\\n        return record\\n\\n\\n@app.get(\\"/jobs/{campaign}\\", dependencies=[Depends(authorize)])\\ndef status(campaign: str):\\n    path = journal_path(campaign)\\n    if not path.exists():\\n        raise HTTPException(404, \\"Referencia no encontrada\\")\\n    return json.loads(path.read_text())\\n\\n\\ndef run_job(campaign):\\n    path = journal_path(campaign)\\n    module = core()\\n    journal = json.loads(path.read_text())\\n    draft = Draft(**journal[\\"request\\"])\\n    module.FB_TEXT = draft.facebook_caption\\n    module.IG_TEXT = draft.instagram_caption\\n    try:\\n        token = credentials()\\n        with httpx.Client(timeout=25, follow_redirects=False) as client:\\n            fresh = image_preflight(client, draft, module)\\n            if fresh != journal[\\"payload\\"]:\\n                raise ValueError(\\"El producto o la imagen cambi\\u00f3 desde la preparaci\\u00f3n\\")\\n            module.publish(client, token, journal[\\"payload\\"], path, journal)\\n        journal[\\"job\\"] = \\"published\\"\\n    except Exception as exc:\\n        journal[\\"job\\"] = \\"review_required\\"\\n        journal[\\"error\\"] = type(exc).__name__\\n    module.save(path, journal)\\n\\n\\n@app.post(\\"/jobs/{campaign}/publish\\", dependencies=[Depends(authorize)])\\ndef submit(campaign: str, tasks: BackgroundTasks):\\n    path = journal_path(campaign)\\n    descriptor = os.open(DATA / \\".submit.lock\\", os.O_CREAT | os.O_RDWR, 0o600)\\n    with os.fdopen(descriptor, \\"w\\") as lock:\\n        fcntl.flock(lock, fcntl.LOCK_EX)\\n        if not path.exists():\\n            raise HTTPException(404, \\"Prepara el borrador antes de publicar\\")\\n        journal = json.loads(path.read_text())\\n        if journal[\\"job\\"] != \\"draft\\":\\n            return journal\\n        credentials()\\n        journal[\\"job\\"] = \\"publishing\\"\\n        core().save(path, journal)\\n        tasks.add_task(run_job, campaign)\\n        return JSONResponse({\\"campaign\\": campaign, \\"job\\": \\"publishing\\",\\n                             \\"status_path\\": \\"/jobs/\\" + campaign}, status_code=202)\\n", "server/tests/test_static_social_post.py": "import importlib.util\\nimport io\\nimport json\\nfrom pathlib import Path\\nimport tempfile\\nimport unittest\\n\\nimport httpx\\nfrom PIL import Image\\n\\nspec = importlib.util.spec_from_file_location(\\n    \\"static_social_post\\", Path(__file__).parents[1] / \\"scripts/static_social_post.py\\")\\nsocial = importlib.util.module_from_spec(spec)\\nspec.loader.exec_module(social)\\n\\n\\nclass PhotoPostTests(unittest.TestCase):\\n    def run_flow(self, failure=None):\\n        calls = []\\n\\n        def handle(request):\\n            calls.append((request.method, request.url.path, request.content))\\n            path = request.url.path\\n            if request.method == \\"POST\\" and failure == path:\\n                raise httpx.ReadTimeout(\\"hidden\\", request=request)\\n            responses = {\\n                \\"/v21.0/\\" + social.PAGE: {\\"id\\": social.PAGE,\\n                    \\"instagram_business_account\\": {\\"id\\": social.INSTAGRAM}},\\n                \\"/v21.0/\\" + social.INSTAGRAM: {\\"username\\": \\"thebooks.wanderer\\"},\\n                \\"/v21.0/\\" + social.PAGE + \\"/photos\\": {\\"id\\": \\"photo\\", \\"post_id\\": \\"post\\"},\\n                \\"/v21.0/\\" + social.INSTAGRAM + \\"/media\\": {\\"id\\": \\"container\\"},\\n                \\"/v21.0/container\\": {\\"status_code\\": \\"FINISHED\\"},\\n                \\"/v21.0/\\" + social.INSTAGRAM + \\"/media_publish\\": {\\"id\\": \\"media\\"},\\n                \\"/v21.0/media\\": {\\"permalink\\": \\"https://instagram.com/p/example/\\", \\"media_type\\": \\"IMAGE\\"},\\n            }\\n            return httpx.Response(200, json=responses[path])\\n\\n        with tempfile.TemporaryDirectory() as temporary:\\n            path = Path(temporary) / \\"journal.json\\"\\n            journal = {\\"facebook\\": {\\"state\\": \\"ready\\"}, \\"instagram\\": {\\"state\\": \\"ready\\"}}\\n            payload = {\\"image_url\\": social.STORE + \\"/photo.jpg\\"}\\n            with httpx.Client(transport=httpx.MockTransport(handle)) as client:\\n                if failure:\\n                    with self.assertRaises(httpx.ReadTimeout):\\n                        social.publish(client, \\"private\\", payload, path, journal)\\n                    journal = json.loads(path.read_text())\\n                    count = len(calls)\\n                    with self.assertRaises(social.SafeError):\\n                        social.publish(client, \\"private\\", payload, path, journal)\\n                    self.assertEqual(count, len(calls))\\n                else:\\n                    social.publish(client, \\"private\\", payload, path, journal)\\n                    social.publish(client, \\"private\\", payload, path, journal)\\n                    self.assertEqual(journal[\\"instagram\\"][\\"media_type\\"], \\"IMAGE\\")\\n            return calls\\n\\n    def test_success_and_retry_publish_only_one_photo_per_network(self):\\n        writes = [call for call in self.run_flow() if call[0] == \\"POST\\"]\\n        self.assertEqual(len(writes), 3)\\n        self.assertFalse(any(b\\"REELS\\" in call[2] or \\"video\\" in call[1] for call in writes))\\n\\n    def test_uncertain_facebook_write_blocks_retry(self):\\n        self.run_flow(\\"/v21.0/\\" + social.PAGE + \\"/photos\\")\\n\\n    def test_uncertain_instagram_publish_does_not_repeat_facebook(self):\\n        self.run_flow(\\"/v21.0/\\" + social.INSTAGRAM + \\"/media_publish\\")\\n\\n    def test_preflight_checks_jpeg_without_sending_credentials(self):\\n        output = io.BytesIO()\\n        Image.new(\\"RGB\\", (1024, 1024)).save(output, \\"JPEG\\")\\n\\n        def handle(request):\\n            self.assertNotIn(\\"authorization\\", request.headers)\\n            if request.url.path.startswith(\\"/api/\\"):\\n                return httpx.Response(200, json={\\"name\\": \\"The Reading Society Tote\\",\\n                                                \\"image_url\\": \\"/photo.jpg\\"})\\n            return httpx.Response(200, content=output.getvalue())\\n\\n        with httpx.Client(transport=httpx.MockTransport(handle)) as client:\\n            self.assertEqual(social.preflight(client)[\\"image_url\\"], social.STORE + \\"/photo.jpg\\")\\n\\n    def test_foreign_or_credential_bearing_image_url_is_rejected(self):\\n        for url in (\\"https://example.com/a.jpg\\", \\"https://private@thebookswanderer.com/a.jpg\\",\\n                    \\"http://thebookswanderer.com/a.jpg\\", \\"/a.jpg?token=private\\"):\\n            with self.subTest(url=url), self.assertRaises(social.SafeError):\\n                social.owned_url(url)\\n\\n\\nif __name__ == \\"__main__\\":\\n    unittest.main()\\n", "server/tests/test_social_publisher_api.py": "import importlib.util\\nimport json\\nfrom pathlib import Path\\nimport tempfile\\nimport unittest\\nfrom unittest.mock import patch\\n\\nfrom fastapi.testclient import TestClient\\n\\nspec = importlib.util.spec_from_file_location(\\n    \\"publisher_api\\", Path(__file__).parents[1] / \\"scripts/social_publisher_api.py\\")\\napi = importlib.util.module_from_spec(spec)\\nspec.loader.exec_module(api)\\n\\n\\nclass PublisherApiTests(unittest.TestCase):\\n    def setUp(self):\\n        self.tmp = tempfile.TemporaryDirectory()\\n        self.addCleanup(self.tmp.cleanup)\\n        directory = Path(self.tmp.name)\\n        self.root = patch.object(api, \\"ROOT\\", directory)\\n        self.data = patch.object(api, \\"DATA\\", directory)\\n        key = directory / \\"key\\"\\n        key.write_text(\\"x\\" * 40)\\n        (directory / \\".env\\").write_text(\\"FB_PAGE_TOKEN=test-only\\\\nFB_PAGE_ID=1200587819810293\\\\n\\")\\n        self.key = patch.object(api, \\"KEY\\", key)\\n        for item in (self.root, self.data, self.key):\\n            item.start()\\n            self.addCleanup(item.stop)\\n        self.headers = {\\"Authorization\\": \\"Bearer \\" + \\"x\\" * 40}\\n        self.client = TestClient(api.app)\\n        self.body = {\\"campaign\\": \\"test_photo_001\\", \\"slug\\": \\"reading-society-tote\\",\\n                     \\"facebook_caption\\": \\"Caption FB\\", \\"instagram_caption\\": \\"Caption IG\\"}\\n\\n    def draft(self):\\n        with patch.object(api, \\"image_preflight\\", return_value={\\"image_url\\": \\"https://thebookswanderer.com/a.jpg\\"}):\\n            return self.client.post(\\"/drafts\\", headers=self.headers, json=self.body)\\n\\n    def test_unauthenticated_requests_cannot_read_or_write(self):\\n        self.assertEqual(self.client.get(\\"/health\\").status_code, 401)\\n        self.assertEqual(self.client.post(\\"/drafts\\", json=self.body).status_code, 401)\\n\\n    def test_health_is_read_only_and_does_not_expose_credentials(self):\\n        with patch.object(api.httpx.HTTPTransport, \\"handle_request\\", side_effect=AssertionError(\\"No network\\")):\\n            result = self.client.get(\\"/health\\", headers=self.headers)\\n        self.assertEqual(result.status_code, 200)\\n        self.assertNotIn(\\"test-only\\", result.text)\\n\\n    def test_existing_reference_cannot_change_caption(self):\\n        self.assertEqual(self.draft().status_code, 200)\\n        self.body[\\"facebook_caption\\"] = \\"Changed\\"\\n        self.assertEqual(self.draft().status_code, 409)\\n\\n    def test_repeated_publish_submits_only_once(self):\\n        self.draft()\\n        with patch.object(api, \\"run_job\\") as runner:\\n            for _ in range(2):\\n                self.client.post(\\"/jobs/test_photo_001/publish\\", headers=self.headers)\\n            self.assertEqual(runner.call_count, 1)\\n\\n    def test_invalid_refs_and_unknown_fields_are_rejected(self):\\n        self.body[\\"campaign\\"] = \\"../escape\\"\\n        self.assertEqual(self.draft().status_code, 422)\\n        self.body[\\"campaign\\"] = \\"valid_ref\\"\\n        self.body[\\"token\\"] = \\"unwanted\\"\\n        self.assertEqual(self.draft().status_code, 422)\\n\\n    def test_restart_does_not_resend_interrupted_job(self):\\n        self.draft()\\n        path = api.journal_path(\\"test_photo_001\\")\\n        record = json.loads(path.read_text())\\n        record[\\"job\\"] = \\"publishing\\"\\n        api.core().save(path, record)\\n        api.reconcile_interrupted_jobs()\\n        with patch.object(api, \\"run_job\\") as runner:\\n            self.client.post(\\"/jobs/test_photo_001/publish\\", headers=self.headers)\\n            runner.assert_not_called()\\n        self.assertEqual(json.loads(path.read_text())[\\"job\\"], \\"review_required\\")\\n\\n    def test_worker_uses_the_saved_captions_and_records_success(self):\\n        self.draft()\\n        module = api.core()\\n        def publish(client, token, payload, path, journal):\\n            self.assertEqual(module.FB_TEXT, \\"Caption FB\\")\\n            self.assertEqual(module.IG_TEXT, \\"Caption IG\\")\\n            journal[\\"facebook\\"][\\"state\\"] = \\"published\\"\\n            journal[\\"instagram\\"][\\"state\\"] = \\"published\\"\\n        with patch.object(api, \\"core\\", return_value=module), \\\\\\n             patch.object(api, \\"image_preflight\\", return_value={\\"image_url\\": \\"https://thebookswanderer.com/a.jpg\\"}), \\\\\\n             patch.object(module, \\"publish\\", side_effect=publish):\\n            api.run_job(\\"test_photo_001\\")\\n        record = json.loads(api.journal_path(\\"test_photo_001\\").read_text())\\n        self.assertEqual(record[\\"job\\"], \\"published\\")\\n\\n    def test_worker_failure_keeps_uncertain_state_for_review(self):\\n        self.draft()\\n        module = api.core()\\n        def interrupted(client, token, payload, path, journal):\\n            journal[\\"facebook\\"][\\"state\\"] = \\"uncertain\\"\\n            module.save(path, journal)\\n            raise TimeoutError(\\"hidden\\")\\n        with patch.object(api, \\"core\\", return_value=module), \\\\\\n             patch.object(api, \\"image_preflight\\", return_value={\\"image_url\\": \\"https://thebookswanderer.com/a.jpg\\"}), \\\\\\n             patch.object(module, \\"publish\\", side_effect=interrupted):\\n            api.run_job(\\"test_photo_001\\")\\n        record = json.loads(api.journal_path(\\"test_photo_001\\").read_text())\\n        self.assertEqual(record[\\"job\\"], \\"review_required\\")\\n        self.assertEqual(record[\\"facebook\\"][\\"state\\"], \\"uncertain\\")\\n\\n\\nif __name__ == \\"__main__\\":\\n    unittest.main()\\n"}')


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Falló la comprobación: " + " ".join(args[:2]))
    return result


def self_check(python):
    with tempfile.TemporaryDirectory(prefix="tbw-publisher-check-") as temporary:
        stage = Path(temporary)
        for relative, content in FILES.items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        run(str(python), "-m", "unittest", "discover", "-s", str(stage / "server/tests"),
            "-p", "test_*social*.py", "-v")
        print("Pruebas sin red: correctas.", flush=True)


def main():
    if sys.argv[1:] == ["--check"]:
        self_check(sys.executable)
        return
    if os.geteuid() != 0:
        raise RuntimeError("Ejecuta como root en la VPS")
    root = Path("/var/www/thebookswanderer.com/server")
    python = root / ".venv/bin/python"
    nginx = Path("/etc/nginx/sites-available/thebookswanderer.com")
    code = Path("/opt/tbw-social-publisher")
    keyfile = Path("/etc/tbw-social-publisher/key")
    metafile = keyfile.with_name("meta.env")
    data = Path("/var/lib/tbw-social-publisher")
    unit = Path("/etc/systemd/system/tbw-social-publisher.service")
    snippet = Path("/etc/nginx/snippets/tbw-social-publisher.conf")
    if not python.is_file() or not nginx.is_file():
        raise RuntimeError("No se encontró la tienda o su configuración Nginx esperada")
    env = dotenv_values(root / ".env")
    token = (env.get("FB_PAGE_TOKEN") or "").strip()
    if not token or (env.get("FB_PAGE_ID") or "").strip() != "1200587819810293":
        raise RuntimeError("Faltan las credenciales Meta de la página esperada")
    original = nginx.read_text()
    include = "include /etc/nginx/snippets/tbw-social-publisher.conf;"
    if include in original:
        updated = original
    else:
        pattern = r"(?m)^([ \t]*)location\s+/api/\s*\{"
        if not re.search(pattern, original):
            raise RuntimeError("Nginx no tiene el bloque /api/ esperado. No se modificó nada")
        updated = re.sub(pattern, lambda m: m[1] + include + "\n\n" + m.group(0), original)
    run("nginx", "-t")
    was_active = subprocess.run(["systemctl", "is-active", "--quiet", "tbw-social-publisher"],
                                capture_output=True).returncode == 0
    if not was_active:
        with socket.socket() as check:
            check.bind(("127.0.0.1", 8877))
    self_check(python)
    if not keyfile.exists():
        print("Crea en tu gestor de contraseñas una clave NUEVA de al menos 32 caracteres.")
        print("Guárdala: después la añadirás a la bóveda del entorno como SOCIAL_PUBLISHER_KEY.")
        key = getpass.getpass("Pega la clave nueva (no se mostrará): ")
        confirmation = getpass.getpass("Repite la clave: ")
        if key != confirmation or len(key) < 32 or not key.isascii() or any(c.isspace() for c in key):
            raise RuntimeError("La clave no coincide o debe tener 32 caracteres ASCII sin espacios")
    else:
        key = keyfile.read_text().strip()
        if len(key) < 32:
            raise RuntimeError("La clave existente no es válida; no se reemplazó")
    account = pwd.getpwnam("www-data")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = Path("/var/backups/tbw-social-publisher") / stamp
    backup.mkdir(parents=True, mode=0o700)
    tracked = [nginx, snippet, unit, metafile, code / "static_social_post.py", code / "social_publisher_api.py"]
    previous = {str(path): path.read_bytes() if path.exists() else None for path in tracked}
    for index, path in enumerate(tracked):
        if previous[str(path)] is not None:
            (backup / str(index)).write_bytes(previous[str(path)])
    (backup / "manifest.json").write_text(json.dumps([str(p) for p in tracked], indent=2))
    keyfile.parent.mkdir(mode=0o750, exist_ok=True)
    os.chown(keyfile.parent, 0, account.pw_gid)
    if not keyfile.exists():
        descriptor = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(key + "\n")
    os.chmod(keyfile, 0o640)
    os.chown(keyfile, 0, account.pw_gid)
    descriptor = os.open(metafile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    with os.fdopen(descriptor, "w") as handle:
        handle.write("FB_PAGE_ID=1200587819810293\nFB_PAGE_TOKEN=" + json.dumps(token) + "\n")
    os.chmod(metafile, 0o640)
    os.chown(metafile, 0, account.pw_gid)
    data.mkdir(mode=0o700, exist_ok=True)
    os.chown(data, account.pw_uid, account.pw_gid)
    code.mkdir(mode=0o755, exist_ok=True)
    try:
        for name in ("static_social_post.py", "social_publisher_api.py"):
            destination = code / name
            destination.write_text(FILES["server/scripts/" + name])
            destination.chmod(0o644)
        snippet.parent.mkdir(exist_ok=True)
        snippet.write_text('''# Managed by install-social-publisher.py
location ^~ /api/social-publisher/ {
    if ($scheme != https) { return 403; }
    client_max_body_size 16k;
    proxy_pass http://127.0.0.1:8877/;
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
    add_header Cache-Control "no-store" always;
}
''')
        unit.write_text(f'''[Unit]
Description=The Books Wanderer private photo publisher
After=network.target
[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory={code}
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=TBW_SOCIAL_META_ENV={metafile}
ExecStart={python} -m uvicorn social_publisher_api:app --app-dir {code} --host 127.0.0.1 --port 8877 --workers 1 --no-access-log
Restart=on-failure
RestartSec=3
TimeoutStopSec=15
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={data}
[Install]
WantedBy=multi-user.target
''')
        nginx.write_text(updated)
        run("nginx", "-t")
        run("systemctl", "daemon-reload")
        run("systemctl", "restart", "tbw-social-publisher")
        ready = False
        with httpx.Client(timeout=5, trust_env=False) as client:
            for _ in range(15):
                try:
                    response = client.get("http://127.0.0.1:8877/health",
                                          headers={"Authorization": "Bearer " + key})
                    if response.status_code == 200 and response.json().get("ready") is True:
                        denied = client.get("http://127.0.0.1:8877/health")
                        if denied.status_code != 401:
                            raise RuntimeError("La comprobación sin clave no fue rechazada")
                        ready = True
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
        if not ready:
            raise RuntimeError("El servicio privado no superó la comprobación local")
        run("systemctl", "reload", "nginx")
        run("systemctl", "enable", "tbw-social-publisher")
    except Exception:
        for path in tracked:
            content = previous[str(path)]
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        subprocess.run(["systemctl", "restart" if was_active else "stop", "tbw-social-publisher"],
                       capture_output=True)
        subprocess.run(["systemctl", "reload", "nginx"], capture_output=True)
        raise
    print("Instalado: https://thebookswanderer.com/api/social-publisher/health")
    print("Autenticación local comprobada: con clave 200, sin clave 401.")
    print("No se publicaron posts. La tienda y su .env no se modificaron ni reiniciaron.")
    print("Respaldo Nginx y servicio: " + str(backup))
    print("Siguiente paso: guarda la clave elegida como secreto de red SOCIAL_PUBLISHER_KEY,")
    print("limitado al dominio thebookswanderer.com. No pegues la clave en el chat.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        raise SystemExit("Instalación detenida: " + message)
