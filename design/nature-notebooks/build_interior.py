"""Typeset a 160-page English commonplace book; no generated illustrations."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import simpleSplit
import fitz
BASE=Path('work/nature-notebooks');BASE.mkdir(exist_ok=True)
ASSETS=Path('assets/products/commonplace-book');ASSETS.mkdir(parents=True,exist_ok=True)
for name,file in [('Serif','LiberationSerif-Regular.ttf'),('SerifItalic','LiberationSerif-Italic.ttf'),('SerifBold','LiberationSerif-Bold.ttf'),('Sans','LiberationSans-Regular.ttf'),('SansBold','LiberationSans-Bold.ttf')]:
 pdfmetrics.registerFont(TTFont(name,'/usr/share/fonts/truetype/liberation/'+file))
W,H=A5;INK=HexColor('#282828');GRAY=HexColor('#666666');RULE=HexColor('#B9B9B9')
def tracked(c,text,x,y,font='Sans',size=8,space=1.1,color=GRAY,center=False):
 width=pdfmetrics.stringWidth(text,font,size)+max(0,len(text)-1)*space
 t=c.beginText();t.setFont(font,size);t.setCharSpace(space);t.setTextOrigin(x-width/2 if center else x,y);t.textOut(text);t.setCharSpace(0);c.setFillColor(color);c.drawText(t)
def paragraph(c,text,x,y,width,font='Sans',size=10,leading=15,color=INK):
 c.setFont(font,size);c.setFillColor(color)
 for raw in text.split('\n'):
  for line in simpleSplit(raw,font,size,width) or ['']:
   c.drawString(x,y,line);y-=leading
 return y
class Book:
 def __init__(self):
  self.c=canvas.Canvas(str(BASE/'commonplace-book-interior.pdf'),pagesize=A5,pageCompression=1,initialFontName='Sans')
  self.c.setTitle('The Commonplace Book — Words, Ideas & Connections');self.c.setAuthor('The Books Wanderer');self.p=0
 def begin(self,kicker,title,sub='',folio=True):
  self.p+=1;self.left=53 if self.p%2 else 39;self.right=W-(39 if self.p%2 else 53);self.width=self.right-self.left
  c=self.c;tracked(c,'THE BOOKS WANDERER',self.left,H-31,size=6,space=1.4)
  c.setStrokeColor(RULE);c.setLineWidth(.4);c.line(self.left,H-41,self.right,H-41)
  tracked(c,kicker.upper(),self.left,H-63,size=7,space=1.2)
  c.setFillColor(INK);c.setFont('Serif',26);c.drawString(self.left,H-96,title);self.y=H-123
  if sub:self.y=paragraph(c,sub,self.left,self.y,self.width,size=9,leading=13,color=GRAY)-12
  if folio:
   c.setFillColor(GRAY);c.setFont('Sans',6.5);c.drawString(self.left,26,'THE COMMONPLACE BOOK');c.drawRightString(self.right,26,str(self.p))
  return self
 def end(self):self.c.showPage()
 def text(self,s,size=10,leading=15,gap=14):self.y=paragraph(self.c,s,self.left,self.y,self.width,size=size,leading=leading)-gap
 def label(self,s):tracked(self.c,s.upper(),self.left,self.y,size=7,space=.8);self.y-=18
 def lines(self,n=3,spacing=19):
  self.c.setStrokeColor(RULE);self.c.setLineWidth(.32)
  for _ in range(n):
   if self.y<48:raise ValueError(f'Writing space overflow: page {self.p}')
   self.c.line(self.left,self.y,self.right,self.y);self.y-=spacing
  self.y-=12
 def field(self,s,n=2):self.label(s);self.lines(n)
 def table(self,headers,widths,rows,height=24):
  c=self.c;y=self.y;c.setFillColor(HexColor('#F0F0F0'));c.rect(self.left,y-21,self.width,25,stroke=0,fill=1)
  x=self.left;c.setFont('SansBold',6.7);c.setFillColor(GRAY)
  for text,w in zip(headers,widths):c.drawString(x+5,y-12,text);x+=w
  y-=21;c.setStrokeColor(RULE);c.setLineWidth(.32)
  for i in range(rows):
   yy=y-height*(i+1)
   if yy<48:raise ValueError(f'Table overflow: page {self.p}')
   c.line(self.left,yy,self.right,yy)
   x=self.left
   for w in widths[:-1]:x+=w;c.line(x,yy,x,yy+height)
  self.y=y-height*rows-20
b=Book();c=b.c
b.begin('The Reading Society','The Commonplace',folio=False)
c.setFont('SerifItalic',40);c.setFillColor(INK);c.drawString(b.left,H-145,'Book')
b.y=H-195;b.text('Words, ideas & connections',13,leading=20)
b.y=H-275;b.text('A place to keep what catches your attention,\nand discover what belongs together.',size=11,leading=18)
tracked(c,'THE BOOKS WANDERER',W/2,82,size=8,space=1.8,center=True);b.end()
b.begin('This collection','Make it your own')
b.field('This book belongs to',2);b.field('Begun in / at',2)
b.text('There is no required order and no deadline. Collect the things you want to return to, leave room for your own response, and let an index grow with the collection.',size=10)
b.y=156;b.text('Text and page design © 2026 The Books Wanderer.\nFirst edition · English · 160 interior pages.\nCover: Great Cinereous Owl, 1837. Robert Havell after John James Audubon. National Gallery of Art, Washington; Gift of Mrs. Walter B. James, 1945.8.351. Artwork reproduction in the public domain.\nthebookswanderer.com',size=7.1,leading=10.5,gap=0);b.end()
b.begin('Start here','A commonplace practice')
for heading,body in [('COLLECT','Save a passage, observation, question or idea. Write enough of the source to find it again: author, title, page, place or date.'),('NOTICE','Explain what caught your attention. Your response can be as brief as a question, a disagreement, or a reminder to look more closely.'),('CONNECT','Link an entry to another page, topic or experience. The useful thread may appear weeks after you first wrote the words.'),('RETURN','Add a topic to the index and revisit the collection when you need a starting point. An entry is allowed to remain unfinished.')]:
 b.label(heading);b.text(body,size=9.5,leading=14,gap=15)
b.end()
b.begin('Your own method','Leave a useful trail')
b.text('A source line helps a future version of you find the original. Use the fields that fit what you are collecting; leave the others blank.')
for heading,body in [('FROM A BOOK','Author · title · edition or translation, if useful · page or chapter.'),('FROM A CONVERSATION','Name or context · date · what was said or what you understood.'),('FROM AN OBSERVATION','Place · date · what you noticed. Mark your own words as an observation.'),('FROM ANOTHER PAGE','Page number · shared topic · the question or contrast connecting them.')]:
 b.label(heading);b.text(body,size=9.3,leading=14,gap=13)
b.text('Use quotation marks for words copied exactly; distinguish a paraphrase from your own response. You do not need to collect long passages for an idea to be useful.',size=9.3,leading=14);b.end()
for i in range(4):
 b.begin('A living index',f'Topics & pages {i+1}','Add subjects in any order. Return to the same topic as new connections appear.')
 b.table(['TOPIC / WORD / QUESTION','PAGE REFERENCES'],[b.width*.63,b.width*.37],15,height=24);b.end()
b.begin('Before you begin','Follow your curiosity')
b.field('Subjects I keep returning to',4)
b.field('Questions I want to carry with me',4)
b.field('A book, place or conversation to begin with',3);b.end()
assert b.p==9
for i in range(1,61):
 b.begin(f'Collection {i:02d} · collect','Words worth keeping')
 assert b.p%2==0
 b.field('Topic / date',1);b.field('Source / author / title',2);b.field('Page, chapter or place',1)
 b.label('Passage / observation / idea');b.lines(10,spacing=19);b.end()
 b.begin(f'Collection {i:02d} · connect','Room for a response')
 b.field('What caught my attention?',4)
 b.field('What does this connect to?',4)
 b.field('A question / page to return to',4);b.end()
assert b.p==129
for i in range(16):
 b.begin('Loose leaves','Notes & discoveries','An extra thought, a longer passage, or a place to keep following the thread.')
 b.lines(20,spacing=19);b.end()
for i in range(12):
 b.begin('Room to explore','Maps & connections','Sketch a relationship, make a small list, or give an idea room to grow.')
 c.setFillColor(HexColor('#BDBDBD'));yy=b.y
 while yy>=53:
  xx=b.left
  while xx<=b.right:c.circle(xx,yy,.4,stroke=0,fill=1);xx+=14
  yy-=14
 b.end()
for i in range(3):
 b.begin('Return & continue','Threads to follow','A final place to gather the connections you want to explore next.')
 b.table(['TOPIC / QUESTION','PAGES / NEXT STEP'],[b.width*.46,b.width*.54],13,height=28);b.end()
assert b.p==160;b.c.save()
doc=fitz.open(BASE/'commonplace-book-interior.pdf');assert len(doc)==160
sample=fitz.open()
for p in (0,1,2,4,9,10,129,145):sample.insert_pdf(doc,from_page=p,to_page=p)
sample.save(ASSETS/'sample_en.pdf',garbage=4,deflate=True)
for label,p in [('title',0),('how',2),('index',4),('collect',9),('connect',10),('notes',129),('dots',145)]:
 doc[p].get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False).save(BASE/f'page-{label}.png')
contact=fitz.open();page=contact.new_page(width=840,height=1188)
for i,p in enumerate((0,1,2,3,4,8,9,10,129,145,157,159)):
 x=(i%3)*280;y=(i//3)*297;page.show_pdf_page(fitz.Rect(x+12,y+10,x+268,y+286),doc,p)
page.get_pixmap().save(BASE/'interior-contact.png')
print('160-page interior: 60 facing entry pairs; 4 index pages; 16 ruled and 12 dot-grid notes; 3 final thread maps. Eight-page actual sample exported.')
