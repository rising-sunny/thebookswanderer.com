"""The approved bilingual shop invitation, shared by preview and campaign."""
from pathlib import Path
from email.utils import formataddr

from jinja2 import Environment, FileSystemLoader, select_autoescape

from urls import PUBLIC_BASE

templates = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parents[1] / "templates")), autoescape=select_autoescape(["html"]))
SENDER = "hello@thebookswanderer.com"
SENDER_HEADER = formataddr(("The Books Wanderer", SENDER))


def draft(lang: str, unsubscribe_url: str = "", *, test: bool = False) -> dict:
    if lang not in ("es", "en"):
        raise ValueError("Unsupported invitation language")
    if lang == "es":
        subject = "Te invitamos a The Books Wanderer"
        paragraphs = [
            "Hola:",
            "Queremos invitarte a conocer The Books Wanderer, nuestra tienda de accesorios y recursos para quienes disfrutan de la lectura.",
            "Si te suscribes, recibirás gratis nuestro reto de lectura 2027: un imprimible con 52 propuestas y una página para registrar tus lecturas.",
            "También te compartiremos novedades de la tienda y recomendaciones lectoras.",
            "¡Nos encantará que nos visites!",
        ]
        heading, eyebrow, cta = "Un regalo para tus lecturas", "The Books Wanderer te invita", "Recibir mi reto gratuito"
        secondary_cta, closing = "Visitar la tienda", "Un saludo,"
        optout = "Si prefieres que no volvamos a escribirte, basta con responder «no contactar»."
        unsubscribe_label = "No recibir más invitaciones"
    else:
        subject = "You're invited to The Books Wanderer"
        paragraphs = [
            "Hi there,",
            "We'd love to welcome you to The Books Wanderer, our shop of reading accessories and resources for book lovers.",
            "Subscribe to receive our free 2027 Reading Challenge: a printable with 52 prompts and a page to log your reading year.",
            "We'll also share shop updates and reading recommendations.",
            "We'd love to see you there!",
        ]
        heading, eyebrow, cta = "A gift for your reading life", "An invitation from The Books Wanderer", "Get my free reading challenge"
        secondary_cta, closing = "Visit the shop", "Warmly,"
        optout = "If you'd prefer not to hear from us again, just reply 'do not contact'."
        unsubscribe_label = "Stop receiving invitations"
    tracking = "?utm_source=outreach_test&utm_medium=email&utm_campaign=store_invitation_test&tbw_test=1" if test else "?utm_source=outreach&utm_medium=email&utm_campaign=store_invitation"
    shop_url = PUBLIC_BASE + ("/es/" if lang == "es" else "/") + tracking
    cta_url = shop_url + "#newsletter"
    context = {"lang": lang, "subject": subject, "paragraphs": paragraphs,
               "heading": heading, "eyebrow": eyebrow, "cta": cta, "closing": closing,
               "optout": optout, "base": PUBLIC_BASE, "cta_url": cta_url,
               "shop_url": shop_url, "secondary_cta": secondary_cta,
               "unsubscribe_url": unsubscribe_url, "unsubscribe_label": unsubscribe_label}
    text = "\n\n".join(paragraphs + [cta + ":\n" + cta_url, secondary_cta + ":\n" + shop_url, closing + "\nThe Books Wanderer", optout])
    if unsubscribe_url:
        text += "\n\n" + unsubscribe_label + ":\n" + unsubscribe_url
    return {**context, "text": text, "html": templates.get_template("collaborator_email.html").render(context)}
