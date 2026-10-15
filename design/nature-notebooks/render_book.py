from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import threading,os
from playwright.sync_api import sync_playwright
ROOT=Path('work/nature-notebooks').resolve();DEST=Path('assets/products/commonplace-book').resolve()
css='''*{box-sizing:border-box}body{margin:0;width:1200px;height:1500px;background:#eee7d8;color:#224b3b;overflow:hidden;font-family:Georgia,serif} .label{position:absolute;top:72px;left:0;width:100%;text-align:center;font:16px Arial;letter-spacing:5px}.foot{position:absolute;bottom:64px;width:100%;text-align:center;font:20px Arial;letter-spacing:3px}.stage{position:absolute;inset:180px 80px 150px;display:flex;align-items:center;justify-content:center;perspective:2200px}.cover{position:relative;transform:rotateY(-11deg) rotateZ(-4deg);filter:drop-shadow(22px 32px 25px #776a4c66)}.cover img{display:block;width:610px;height:auto;border-radius:1px 4px 4px 1px}.cover:after{content:'';position:absolute;right:-10px;top:6px;bottom:1px;width:10px;background:repeating-linear-gradient(#eee 0px,#eee 1px,#fdfdfb 1px,#fdfdfb 3px);transform:skewY(-33deg);transform-origin:top left;border-radius:0 2px 2px 0}.spread{display:flex;gap:6px;filter:drop-shadow(4px 20px 22px #776a4c44);transform:rotate(-2deg)}.spread img{width:485px;display:block}.spread:after{content:'';position:absolute;left:50%;width:26px;height:100%;background:linear-gradient(90deg,transparent,#0000000c,transparent);transform:translateX(-50%)}.caption{position:absolute;top:117px;width:100%;text-align:center;font-size:37px;font-weight:normal;letter-spacing:-.7px}.duo{display:flex;gap:30px;align-items:center;transform:rotate(-3deg)}.duo img{width:445px;box-shadow:12px 18px 22px #776a4c33}'''
scenes={
'main_en.jpg':('<div class="cover"><img src="front-cover.png"></div>','THE BOOKS WANDERER','', 'A5 PAPERBACK  ·  160 PAGES  ·  UNDATED'),
'open_en.jpg':('<div class="spread"><img src="page-collect.png"><img src="page-connect.png"></div>','LOOK INSIDE','Keep the words. Follow the thread.','SIXTY ENTRY PAIRS  ·  ENGLISH EDITION'),
'notes_en.jpg':('<div class="spread"><img src="page-index.png"><img src="page-dots.png"></div>','AN INDEX OF YOUR OWN','Make room for connections.','INDEX  ·  RULED NOTES  ·  DOT GRID'),
'covers_en.jpg':('<div class="duo"><img src="back-cover.png"><img src="front-cover.png"></div>','THE READING SOCIETY','A collection of your own.','MATTE COLOUR COVER  ·  BLACK-AND-WHITE INTERIOR'),
}
class Quiet(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
os.chdir(ROOT)
server=ThreadingHTTPServer(('127.0.0.1',8767),Quiet);threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1200,'height':1500},device_scale_factor=1)
 for filename,(content,label,title,footer) in scenes.items():
  html=f'<html><head><meta charset="utf-8"><style>{css}</style></head><body><div class="label">{label}</div><div class="caption">{title}</div><div class="stage">{content}</div><div class="foot">{footer}</div></body></html>'
  (ROOT/'scene.html').write_text(html)
  page.goto('http://127.0.0.1:8767/scene.html?name='+filename,wait_until='networkidle');page.screenshot(path=str(DEST/filename),type='jpeg',quality=93)
 browser.close()
server.shutdown()
print('Rendered four book previews from the actual print files.')
