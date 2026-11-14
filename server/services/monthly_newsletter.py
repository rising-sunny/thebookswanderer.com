"""Bilingual monthly letter for opted-in subscribers, once per email and month."""
from __future__ import annotations
import fcntl
import re
from datetime import datetime, timedelta, timezone
from email.utils import make_msgid
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from database import SessionLocal
from models import EmailOptOut, NewsletterSubscriber, Product
from services import collaborators_store as store, email as mail
from services.invitation import SENDER
import i18n
from urls import PUBLIC_BASE

START_PERIOD = '2026-11'
MONTHS = {'en': ('January February March April May June July August September October November December').split(),
          'es': ('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre').split()}
TIPS = {
 'en': ['Return to a book you underlined years ago.', 'Swap one reading recommendation with a friend.', 'Make room for ten quiet pages.', 'Try a story set somewhere you have never visited.', 'Read a chapter outside.', 'Keep a sentence that made you pause.', 'Choose a short book for a long afternoon.', 'Revisit an author you used to love.', 'Start a small notebook of reading discoveries.', 'Save a passage with the page number.', 'Give a reader a book with a handwritten note.', 'Look back at a story that stayed with you.'],
 'es': ['Vuelve a un libro que subrayaste hace años.', 'Intercambia una recomendación con alguien cercano.', 'Haz espacio para diez páginas tranquilas.', 'Prueba una historia ambientada en un lugar que no conoces.', 'Lee un capítulo al aire libre.', 'Guarda una frase que te haya hecho detenerte.', 'Elige un libro corto para una tarde larga.', 'Vuelve a un autor que te gustaba.', 'Empieza un cuaderno de descubrimientos lectores.', 'Anota un fragmento junto a su número de página.', 'Regala un libro con una nota escrita a mano.', 'Recuerda una historia que se haya quedado contigo.']}
TEMPLATES = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parents[1]/'templates')), autoescape=select_autoescape(['html']))

# Hand-written issues. A period listed here replaces the generic copy and pins the products;
# any other month keeps the rotating shelf above. Prices come from the catalogue, never from here.
EDITIONS = {'2026-12': {
 'en': {
  'subject': 'Your 2027 reading year, still blank',
  'preheader': 'Three ten-minute rituals, one book to start on January 1st, and a free challenge.',
  'heading': 'A reading year, still unwritten',
  'intro': "December is the month of lists: gifts, groceries, regrets, resolutions. So here is one more, and it is the nicest of them all: the books you haven't read yet. Nothing crossed off, nothing abandoned, every page still ahead of you. Let's get it ready before the year turns.",
  'rituals_title': 'Three ten-minute rituals for a good start',
  'rituals': [
   ('Choose your first book.', "Not the best book on your shelf; the one you are actually looking forward to. Put it on top of the pile now, so January 1st already has a yes waiting."),
   ('Pick a number, not a verdict.', 'Fifty-two is one a week. Twenty-six is one every other week. Twelve is one a month, and perfectly respectable. Any number you finish beats the one you abandon in March.'),
   ('Give your list a home.', 'A list that lives in a drawer gets forgotten; one that sits next to your reading chair gets finished. Pin it up, tuck it into a notebook, or give it a book of its own.')],
  'feature_intro': 'If a book of its own sounds right, this is the one we made for it:',
  'feature_slug': 'reading-challenge-journal-2027',
  'feature_title': 'The 2027 Reading Challenge Journal',
  'feature_blurb': 'The challenge, bound. The 52 prompts as a checklist, a bookshelf where you colour one spine for every book you finish, four bingo cards, a page for every month and room to review all fifty-two books. A5 paperback, 56 full-colour pages. It is printed to order (a few working days, then shipping), so order a little ahead if you want it in your hands on January 1st.',
  'feature_cta': 'See the journal',
  'shelf': ['readers-2027-desk-calendar', 'reading-passport-printed', 'reading-log-bookmarks'],
  'closing': 'One small favour: tell us the first book of 2027. Just hit reply. It reaches a real person, and we read every one.'},
 'es': {
  'subject': 'Tu año de lectura 2027, todavía en blanco',
  'preheader': 'Tres rituales de diez minutos, un libro para empezar el 1 de enero y un reto gratis.',
  'heading': 'Un año de lectura todavía por escribir',
  'intro': 'Diciembre es el mes de las listas: regalos, compras, arrepentimientos, propósitos. Así que aquí va una más, y es la más bonita de todas: la de los libros que aún no has leído. Nada tachado, nada abandonado, todas las páginas por delante. Vamos a dejarla lista antes de que cambie el año.',
  'rituals_title': 'Tres rituales de diez minutos para empezar bien',
  'rituals': [
   ('Elige tu primer libro.', 'No el mejor de tu estantería, sino el que de verdad te apetece leer. Ponlo ahora encima de la pila y el 1 de enero ya tendrá un sí esperándote.'),
   ('Elige un número, no una sentencia.', 'Cincuenta y dos es un libro por semana. Veintiséis, uno cada quince días. Doce es uno al mes y es perfectamente digno. Cualquier cifra que termines vale más que la que abandonas en marzo.'),
   ('Dale un hogar a tu lista.', 'Una lista guardada en un cajón se olvida; una junto a tu sillón de lectura se termina. Cuélgala, métela en una libreta o dale un libro propio.')],
  'feature_intro': 'Si lo de un libro propio te suena bien, esto es lo que hicimos para eso:',
  'feature_slug': 'reading-challenge-journal-2027',
  'feature_title': 'El diario del reto de lectura 2027',
  'feature_blurb': 'El reto, encuadernado. Las 52 consignas como lista de comprobación, una estantería donde coloreas un lomo por cada libro que termines, cuatro cartones de bingo, una página para cada mes y espacio para reseñar los cincuenta y dos libros. Tapa blanda A5, 56 páginas a todo color (las páginas están en inglés). Se imprime bajo pedido (unos días hábiles y luego el envío), así que pídelo con algo de margen si lo quieres en tus manos el 1 de enero.',
  'feature_cta': 'Ver el diario',
  'shelf': ['readers-2027-desk-calendar', 'reading-passport-printed', 'reading-log-bookmarks'],
  'closing': 'Un pequeño favor: cuéntanos cuál será tu primer libro de 2027. Solo responde a este correo; lo lee una persona de verdad y los leemos todos.'}}}

def _card(p,lang,period):
    item=i18n.product(p,lang); image=item.get('image_url') or '/assets/logo-email.png'
    if image.startswith('/'):image=PUBLIC_BASE+image
    return {'title':item['title'],'image':image,'url':PUBLIC_BASE+('/es' if lang=='es' else '')+'/products/'+item['slug']+'?utm_source=newsletter&utm_medium=email&utm_campaign=monthly_'+period}

def validate_period(period):
    if not re.fullmatch(r'20\d{2}-(?:0[1-9]|1[0-2])',period):
        raise ValueError('Invalid monthly period')
    return period

def draft(lang, period, unsubscribe_url='', products=None):
    validate_period(period)
    if lang not in ('es','en'): raise ValueError('Unsupported language')
    year,month=map(int,period.split('-')); es=lang=='es'; name=MONTHS[lang][month-1]
    heading='Una pausa entre páginas' if es else 'A pause between pages'
    intro='Una pequeña carta con una idea para tus lecturas, una selección de la tienda y un recurso gratuito para guardar.' if es else 'A small letter with one reading idea, a few finds from the shop, and a free resource to keep.'
    subject=(f'Tu carta de {name}' if es else f'Your {name} reading letter')+' · The Books Wanderer'
    if products is None:
        with SessionLocal() as db:
            products=[p.to_public() for p in db.query(Product).filter(Product.active.is_(True)).order_by(Product.id.desc()).all()]
    # Rotate the shelf between months, keeping the initial issue on new arrivals.
    offset=((year-2026)*12+month-11)*3
    items=[]
    if products:
        start=offset%len(products)
        for product in (products[start:]+products[:start])[:3]:
            item=i18n.product(product,lang)
            image=item.get('image_url') or '/assets/logo-email.png'
            if image.startswith('/'):image=PUBLIC_BASE+image
            items.append({'title':item['title'],'image':image,'url':PUBLIC_BASE+('/es' if es else '')+'/products/'+item['slug']+'?utm_source=newsletter&utm_medium=email&utm_campaign=monthly_'+period})
    ed=EDITIONS.get(period,{}).get(lang); extra={}; pre_text=[]; post_text=[]
    if ed:
        by_slug={p['slug']:p for p in products}
        subject=ed['subject']+' · The Books Wanderer'; heading=ed['heading']; intro=ed['intro']
        pinned=[_card(by_slug[s],lang,period) for s in ed['shelf'] if s in by_slug]
        if pinned: items=pinned
        extra={'preheader':ed['preheader'],'rituals_title':ed['rituals_title'],'rituals':ed['rituals'],'feature_intro':ed['feature_intro'],'closing':ed['closing']}
        pre_text=[ed['rituals_title']]+[f'{i}. {t} {b}' for i,(t,b) in enumerate(ed['rituals'],1)]
        feat=by_slug.get(ed['feature_slug'])
        if feat:
            extra['feature']=dict(_card(feat,lang,period),title=ed['feature_title'],blurb=ed['feature_blurb'],cta=ed['feature_cta'],price='${:.2f}'.format(feat['price_usd']))
            pre_text+=[ed['feature_intro'],extra['feature']['title']+' — '+extra['feature']['price']+'\n'+ed['feature_blurb']+'\n'+extra['feature']['url']]
        post_text=[ed['closing']]
    resource=PUBLIC_BASE+('/reto-de-lectura-2027/' if es else '/reading-challenge-2027/')+'?utm_source=newsletter&utm_medium=email&utm_campaign=monthly_'+period
    context={'lang':lang,'subject':subject,'heading':heading,'intro':intro,'month':f'{name} {year}','tip':TIPS[lang][month-1],'items':items,'resource':resource,'unsubscribe_url':unsubscribe_url,'base':PUBLIC_BASE,**extra}
    text='\n\n'.join([heading,context['month'],intro]+pre_text+[context['tip']]+[item['title']+'\n'+item['url'] for item in items]+[('Reto de Lectura 2027 gratuito: ' if es else 'Free 2027 Reading Challenge: ')+resource]+post_text+[('Darte de baja: ' if es else 'Unsubscribe: ')+unsubscribe_url])
    return {'subject':subject,'html':TEMPLATES.get_template('monthly_newsletter.html').render(**context),'text':text}

def unsubscribe_link(email):
    from main import unsubscribe_token
    return PUBLIC_BASE+'/api/unsubscribe?'+urlencode({'email':email,'t':unsubscribe_token(email)})

def excluded_addresses():
    with store.connect() as db:
        excluded={row[0].lower() for row in db.execute('SELECT email FROM outreach_suppressions')}
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='outreach_samples'").fetchone():
            excluded.update(row[0].lower() for row in db.execute('SELECT email FROM outreach_samples'))
    return excluded

def eligible(now):
    cutoff=now.replace(tzinfo=None)-timedelta(days=7)
    excluded=excluded_addresses()
    with SessionLocal() as db:
        excluded.update(row[0].lower() for row in db.query(EmailOptOut.email))
        return [{'email':s.email.strip().lower(),'lang':s.lang if s.lang in ('es','en') else 'en'}
                for s in db.query(NewsletterSubscriber).filter(NewsletterSubscriber.active.is_(True),NewsletterSubscriber.welcome_step>=3).order_by(NewsletterSubscriber.id)
                if s.email.strip().lower() not in excluded and s.welcome_at and s.welcome_at<=cutoff
                and not (s.source or '').lower().startswith(('test','sample'))]

def run(*, send=False, now=None):
    now=now or datetime.now(timezone.utc);period=now.strftime('%Y-%m')
    if period<START_PERIOD or now.day>3:
        return {'period':period,'status':'not_due','first_issue':START_PERIOD}
    store.init_store()
    with (store.data_dir()/'monthly.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'period':period,'status':'already_running'}
        recipients=eligible(now)
        with store.connect() as db:
            existing={row[0] for row in db.execute('SELECT email FROM monthly_deliveries WHERE period=?',(period,))}
        pending=[r for r in recipients if r['email'] not in existing]
        if not send:return {'period':period,'status':'dry_run','new_eligible':len(pending),'already_recorded':len(existing)}
        if not mail.configured():raise ValueError('Monthly SMTP is not configured')
        # Every row is claimed before touching SMTP; ambiguous attempts never retry.
        with store.connect() as db:
            db.execute("UPDATE monthly_deliveries SET status='uncertain',detail='Interrupted send; no automatic retry' WHERE status='sending'")
        for recipient in pending:
            content=draft(recipient['lang'],period,unsubscribe_link(recipient['email']))
            with store.connect() as db:
                db.execute('INSERT OR IGNORE INTO monthly_deliveries(period,email,lang,created_at,subject,html,text,message_id) VALUES(?,?,?,?,?,?,?,?)',(period,recipient['email'],recipient['lang'],store.now(),content['subject'],content['html'],content['text'],make_msgid(domain='thebookswanderer.com')))
        allowed={r['email'] for r in eligible(now)}
        with store.connect() as db:
            queue=[dict(r) for r in db.execute("SELECT * FROM monthly_deliveries WHERE period=? AND status='queued' ORDER BY id LIMIT 60",(period,))]
        for row in queue:
            with store.connect() as db:
                if row['email'] not in allowed:
                    db.execute("UPDATE monthly_deliveries SET status='suppressed',detail='Unsubscribed, test address or not eligible' WHERE id=? AND status='queued'",(row['id'],));continue
                claimed=db.execute("UPDATE monthly_deliveries SET status='sending',attempted_at=? WHERE id=? AND status='queued'",(store.now(),row['id'])).rowcount
            if not claimed:continue
            # Recheck unsubscribe after the durable claim and immediately before send.
            if row['email'] not in {r['email'] for r in eligible(now)}:
                with store.connect() as db:db.execute("UPDATE monthly_deliveries SET status='suppressed' WHERE id=?",(row['id'],))
                continue
            link=unsubscribe_link(row['email'])
            try:
                accepted=mail._send_sync(to=[row['email']],subject=row['subject'],text=row['text'],html=row['html'],message_id=row['message_id'],from_address=SENDER,reply_to=SENDER,headers={'List-Unsubscribe':f'<{link}>','X-TBW-Campaign':'monthly_'+period})
            except Exception:accepted=False
            with store.connect() as db:
                db.execute('UPDATE monthly_deliveries SET status=?,sent_at=?,detail=? WHERE id=?',('sent' if accepted else 'uncertain',store.now() if accepted else None,'Accepted by SMTP' if accepted else 'No SMTP confirmation; no automatic retry',row['id']))
        with store.connect() as db:
            counts={r['status']:r['n'] for r in db.execute('SELECT status,count(*) AS n FROM monthly_deliveries WHERE period=? GROUP BY status',(period,))}
        return {'period':period,'status':'completed','counts':counts}
