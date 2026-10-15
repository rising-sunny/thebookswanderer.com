"""Place unaltered public-domain reproductions in the two exact print layouts."""
from pathlib import Path
import json
import fitz
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader,simpleSplit
from PIL import Image
BASE=Path('work/nature-notebooks');W,H=A5
for name,file in [('Serif','LiberationSerif-Regular.ttf'),('SerifItalic','LiberationSerif-Italic.ttf'),('Sans','LiberationSans-Regular.ttf'),('SansBold','LiberationSans-Bold.ttf')]:
 pdfmetrics.registerFont(TTFont(name,'/usr/share/fonts/truetype/liberation/'+file))
CREAM=HexColor('#F6F0E3');GREEN=HexColor('#294538');INK=HexColor('#31392E');GOLD=HexColor('#B79A66')
def tracked(c,text,x,y,size=8,space=1.3,color=GREEN):
 t=c.beginText();t.setFont('Sans',size);t.setCharSpace(space);t.setTextOrigin(x-(pdfmetrics.stringWidth(text,'Sans',size)+(len(text)-1)*space)/2,y);t.textOut(text);t.setCharSpace(0);c.setFillColor(color);c.drawText(t)
def para(c,text,x,y,width,size=10,leading=16,color=GREEN,font='Sans'):
 c.setFont(font,size);c.setFillColor(color)
 for raw in text.split('\n'):
  for line in simpleSplit(raw,font,size,width) or ['']:
   c.drawString(x,y,line);y-=leading
 return y

def place_art(c,file,x,y,width,height):
 with Image.open(file) as im:iw,ih=im.size
 scale=min(width/iw,height/ih);pw,ph=iw*scale,ih*scale
 dpi=min(iw/(pw/72),ih/(ph/72))
 if dpi<300:raise ValueError('Source artwork resolution below 300 dpi at placed size')
 c.drawImage(ImageReader(str(file)),x+(width-pw)/2,y+(height-ph)/2,pw,ph,mask='auto')
 print(file.name,'placed at',round(dpi),'dpi')
 return dpi

def render_extract(pdf,rect,file):
 d=fitz.open(pdf);d[0].get_pixmap(matrix=fitz.Matrix(2.5,2.5),clip=rect,alpha=False).save(file)

def book_cover():
 dims=json.loads(Path('design/nature-notebooks/print-layout.json').read_text())['lulu_cover'];cw,ch=float(dims['width']),float(dims['height']);bleed=9;spine=cw-2*bleed-2*W;fx=bleed+W+spine
 path=BASE/'commonplace-book-cover.pdf';c=canvas.Canvas(str(path),pagesize=(cw,ch),pageCompression=1,initialFontName='Sans');c.setTitle('The Commonplace Book — Owl Edition cover');c.setAuthor('The Books Wanderer')
 c.setFillColor(CREAM);c.rect(0,0,cw,ch,stroke=0,fill=1)
 c.setFillColor(GREEN);c.rect(bleed+W,0,spine,ch,stroke=0,fill=1)
 c.saveState();c.translate(bleed+W+spine/2,ch/2);c.rotate(90);tracked(c,'THE COMMONPLACE BOOK',0,-3,size=8.5,space=1.6,color=CREAM);c.restoreState()
 center=fx+W/2
 tracked(c,'THE BOOKS WANDERER',center,ch-52,size=7,space=1.7)
 c.setFont('Serif',31);c.setFillColor(GREEN);c.drawCentredString(center,ch-96,'The Commonplace')
 c.setFont('SerifItalic',40);c.drawCentredString(center,ch-140,'Book')
 c.setStrokeColor(GOLD);c.setLineWidth(.55);c.line(fx+55,ch-160,fx+W-55,ch-160)
 dpi=place_art(c,Path('assets/products/commonplace-book/artwork-original.jpg'),fx+43,87,W-86,350)
 c.setFillColor(GREEN);c.setFont('SerifItalic',12);c.drawCentredString(center,66,'Words, ideas & connections')
 tracked(c,'A COLLECTION OF YOUR OWN',center,43,size=6.5,space=1.3)
 x=bleed+39;width=W-78;y=ch-65
 tracked(c,'THE READING SOCIETY',bleed+W/2,y,size=7,space=1.5);y-=65
 y=para(c,'Keep the words.\nFollow the thread.',x,y,width,size=27,leading=33,font='Serif')-26
 y=para(c,'A commonplace book is a personal collection: passages that stay with you, observations worth saving, and ideas that begin a conversation with one another.',x,y,width,size=11,leading=17)-21
 y=para(c,'Inside, find sixty facing-page entry pairs for sources and your response, a topic index, ruled and dot-grid notes, and space to trace the connections that emerge.',x,y,width,size=10,leading=16)-23
 y=para(c,'160 pages · A5 paperback\nUndated · English edition',x,y,width,size=9,leading=15)-25
 c.setStrokeColor(GOLD);c.line(x,144,x+width,144)
 para(c,'Cover artwork: Great Cinereous Owl, 1837.\nRobert Havell after John James Audubon.\nNational Gallery of Art, Washington.\nPublic-domain reproduction.',x,123,width,size=7.2,leading=11)
 para(c,'thebookswanderer.com',x,54,width,size=8,leading=12)
 c.save()
 render_extract(path,fitz.Rect(fx,ch-bleed-H,fx+W,ch-bleed),BASE/'front-cover.png')
 render_extract(path,fitz.Rect(bleed,ch-bleed-H,bleed+W,ch-bleed),BASE/'back-cover.png')
 return {'cover_points':[cw,ch],'spine_points':spine,'owl_placed_dpi':dpi}

def notebook_cover():
 folder=Path('assets/products/reading-society-notebook');art=folder/'artwork-original.jpg'
 if not art.exists():return None
 # District Photo's full wrap placeholder is exactly 4065 x 2850 at 300 dpi.
 cw,ch=4065*72/300,2850*72/300;turn=.75*72;pw,ph=5.75*72,8*72;spine=.55*72;fx=turn+pw+spine;fy=turn
 path=BASE/'reading-society-notebook-artwork.pdf';c=canvas.Canvas(str(path),pagesize=(cw,ch),pageCompression=1,initialFontName='Sans');c.setTitle('The Reading Society Notebook — Lake Suwa cover');c.setAuthor('The Books Wanderer')
 c.setFillColor(GREEN);c.rect(0,0,cw,ch,stroke=0,fill=1)
 c.setFillColor(CREAM);c.rect(turn,fy,pw,ph,stroke=0,fill=1);c.rect(fx,fy,pw,ph,stroke=0,fill=1)
 center=fx+pw/2
 tracked(c,'THE BOOKS WANDERER',center,fy+ph-38,size=7,space=1.7)
 c.setFillColor(GREEN);c.setFont('Serif',26);c.drawCentredString(center,fy+ph-91,'The Reading Society')
 c.setFont('SerifItalic',40);c.drawCentredString(center,fy+ph-139,'Notebook')
 c.setStrokeColor(GOLD);c.setLineWidth(.6);c.line(fx+38,fy+ph-165,fx+pw-38,fy+ph-165)
 dpi=place_art(c,art,fx+32,fy+155,pw-64,242)
 c.setFillColor(GREEN);c.setFont('SerifItalic',14);c.drawCentredString(center,fy+103,'Notes between chapters.')
 tracked(c,'LAKE SUWA · KATSUSHIKA HOKUSAI',center,fy+62,size=6.2,space=1)
 tracked(c,'150 LINED PAGES',center,fy+37,size=6.6,space=1.3)
 c.saveState();c.translate(turn+pw+spine/2,ch/2);c.rotate(90);tracked(c,'THE READING SOCIETY',0,-3,size=8,space=1.5,color=CREAM);c.restoreState()
 x=turn+39;width=pw-78;y=fy+ph-50
 tracked(c,'THE READING SOCIETY',turn+pw/2,y,size=7,space=1.5);y-=68
 y=para(c,'For thoughts that\nneed a little room.',x,y,width,size=27,leading=33,font='Serif')-29
 y=para(c,'A notebook for reading notes, ideas, lists, and the things you want to remember between one chapter and the next.',x,y,width,size=11,leading=17)-32
 y=para(c,'150 lined pages\nMatte hardcover\nPrinted to order',x,y,width,size=9,leading=17)-28
 y=para(c,'Cover artwork: Lake Suwa in Shinano Province,\nca. 1830–32, Katsushika Hokusai.\nThe Metropolitan Museum of Art.\nHenry L. Phillips Collection.\nPublic-domain reproduction · Open Access / CC0.',x,y,width,size=7.1,leading=11)-24
 para(c,'thebookswanderer.com',x,y,width,size=8,leading=12)
 # Leave the lower-right back cover free for the manufacturer's barcode.
 c.save()
 d=fitz.open(path);pix=d[0].get_pixmap(matrix=fitz.Matrix(300/72,300/72),alpha=False)
 assert (pix.width,pix.height)==(4065,2850)
 pix.save(BASE/'reading-society-notebook-artwork.png')
 render_extract(path,fitz.Rect(fx,ch-(fy+ph),fx+pw,ch-fy),BASE/'notebook-front.png')
 render_extract(path,fitz.Rect(turn,ch-(fy+ph),turn+pw,ch-fy),BASE/'notebook-back.png')
 return {'placeholder_pixels':[pix.width,pix.height],'hokusai_placed_dpi':dpi,'trim_panel_inches':[5.75,8],'turn_in_inches':.75,'spine_inches':.55}
if __name__=='__main__':
 report={'book':book_cover(),'notebook':notebook_cover()};(BASE/'design-preflight.json').write_text(json.dumps(report,indent=2));print(report)
