"""Bounded, robots-aware research of explicitly selected public websites.

No search scraping, email guessing, login, mailing, or newsletter integration.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import getproxies, proxy_bypass
from urllib.robotparser import RobotFileParser

import httpcore
import httpx
from email_validator import EmailNotValidError, validate_email

AGENT = "TBWCollaboratorResearch"
USER_AGENT = f"{AGENT}/1.0 (+https://thebookswanderer.com/contact.html)"
MAX_BYTES = 750_000
CONTACT_WORDS = ("contact", "contacto", "collaborat", "colabor", "partnership", "advertis", "publicidad", "sponsor", "media-kit", "media kit", "work-with", "trabaja-con", "press", "prensa", "editorial")
EXCLUDED_WORDS = ("privacy", "privacidad", "legal", "terms", "terminos", "support", "soporte", "help", "ayuda", "careers", "empleo", "jobs")
EMAIL_RE = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}", re.I)


class ResearchError(ValueError):
    pass


def is_public(ip: str) -> bool:
    address = ipaddress.ip_address(ip)
    return address.is_global and not address.is_multicast and not address.is_reserved


def normalize_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
            raise ResearchError("Usa una URL pública http/https sin credenciales.")
        if parsed.port not in (None, 80 if parsed.scheme == "http" else 443):
            raise ResearchError("Solo se permiten los puertos web estándar.")
        if ":" in host or any(ord(c) < 33 for c in value) or "\\" in value:
            raise ResearchError("URL no admitida.")
        try:
            ip = ipaddress.ip_address(host)
            if not is_public(str(ip)):
                raise ResearchError("No se permiten redes privadas o locales.")
        except ValueError as exc:
            if isinstance(exc, ResearchError):
                raise
        if host == "localhost" or "." not in host or host.endswith((".local", ".internal", ".localhost")):
            raise ResearchError("No se permiten destinos internos.")
        # Tracking strings and fragments are irrelevant for research pages.
        return urlunsplit((parsed.scheme, host, parsed.path or "/", "", ""))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, ResearchError):
            raise
        raise ResearchError("URL no válida.") from exc


def site_host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def public_addresses(host: str, port: int) -> list[str]:
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(item[4][0] for item in answers))
    if not addresses or any(not is_public(ip) for ip in addresses):
        raise ResearchError("Destino privado o DNS no admitido.")
    return addresses


class PublicBackend(httpcore.SyncBackend):
    """Pin direct sockets to checked numeric IPs; TLS still uses the host name.

    Configured environment proxies are retained. Their own DNS/egress policy
    controls proxy transport; the URL's public destination is checked separately.
    """
    def __init__(self, proxy_host: str | None = None):
        self.proxy_host = proxy_host

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host == self.proxy_host:
            return super().connect_tcp(host, port, timeout, local_address, socket_options)
        addresses = public_addresses(host, port)
        return super().connect_tcp(addresses[0], port, timeout, local_address, socket_options)


class Fetcher:
    def __init__(self, site_url: str, max_seconds: float = 75):
        self.site = site_host(site_url)
        self.deadline = time.monotonic() + max_seconds
        self.last_request = 0.0
        self.delay = 1.5
        self.clients: dict[str, httpx.Client] = {}
        self.robots: dict[str, RobotFileParser] = {}

    def close(self):
        for client in self.clients.values():
            client.close()

    def _budget(self):
        if time.monotonic() >= self.deadline:
            raise ResearchError("Tiempo máximo de revisión alcanzado.")

    def _client(self, url: str) -> httpx.Client:
        parsed = urlsplit(url)
        proxies = getproxies()
        proxy = "" if proxy_bypass(parsed.hostname or "") else proxies.get(parsed.scheme, proxies.get("all", ""))
        if proxy not in self.clients:
            transport = httpx.HTTPTransport(proxy=proxy or None, trust_env=True, retries=0)
            # httpx 0.28 uses an httpcore pool; replacing its backend keeps SNI,
            # CA verification and environment proxies while pinning direct DNS.
            transport._pool._network_backend = PublicBackend(urlsplit(proxy).hostname if proxy else None)
            self.clients[proxy] = httpx.Client(transport=transport, follow_redirects=False, headers={"User-Agent": USER_AGENT}, timeout=10)
        return self.clients[proxy]

    def _get(self, url: str, *, robots: bool = False) -> tuple[int, str, str]:
        for _ in range(4):
            self._budget()
            url = normalize_url(url)
            if site_host(url) != self.site:
                raise ResearchError("Redirección fuera del sitio seleccionado.")
            parsed = urlsplit(url)
            public_addresses(parsed.hostname, 443 if parsed.scheme == "https" else 80)
            pause = self.delay - (time.monotonic() - self.last_request)
            if pause > 0:
                if time.monotonic() + pause >= self.deadline:
                    self._budget_expired()
                time.sleep(pause)
            self._budget()
            self.last_request = time.monotonic()
            with self._client(url).stream("GET", url, timeout=min(10, max(0.1, self.deadline - time.monotonic()))) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    next_url = normalize_url(urljoin(url, response.headers.get("location", "")))
                    # Check robots on redirected content too, before fetching it.
                    if not robots and not self.allowed(next_url):
                        raise ResearchError("Página bloqueada por robots.txt.")
                    url = next_url
                    continue
                if response.status_code != 200:
                    return response.status_code, url, ""
                kind = response.headers.get("content-type", "").lower()
                if robots:
                    if kind and not any(t in kind for t in ("text/plain", "text/html")):
                        raise ResearchError("robots.txt no es texto.")
                elif not any(t in kind for t in ("text/html", "application/xhtml+xml")):
                    return response.status_code, url, ""
                if not robots and "noindex" in response.headers.get("x-robots-tag", "").lower():
                    return response.status_code, url, ""
                chunks, size = [], 0
                for chunk in response.iter_bytes(chunk_size=16_384):
                    self._budget()
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ResearchError("Página demasiado grande para esta revisión.")
                    chunks.append(chunk)
                return response.status_code, url, b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
        raise ResearchError("Demasiadas redirecciones.")

    def _budget_expired(self):
        raise ResearchError("Tiempo máximo de revisión alcanzado.")

    def allowed(self, url: str) -> bool:
        url = normalize_url(url)
        if site_host(url) != self.site:
            return False
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            code, _, text = self._get(origin + "/robots.txt", robots=True)
            robot = RobotFileParser()
            if code in (404, 410):
                robot.parse([])
            elif code == 200 and not text.lstrip().lower().startswith(("<!doctype html", "<html")):
                robot.parse(text.splitlines())
            else:
                raise ResearchError(f"No se pudo verificar robots.txt (HTTP {code}).")
            self.robots[origin] = robot
        robot = self.robots[origin]
        delay = robot.crawl_delay(AGENT) or robot.crawl_delay("*") or 0
        rate = robot.request_rate(AGENT) or robot.request_rate("*")
        if rate and rate.requests:
            delay = max(delay, rate.seconds / rate.requests)
        self.delay = max(self.delay, delay)
        return robot.can_fetch(AGENT, url)

    def page(self, url: str) -> tuple[str, str]:
        if not self.allowed(url):
            raise ResearchError("Página bloqueada por robots.txt.")
        code, final_url, body = self._get(url)
        if code != 200:
            raise ResearchError(f"Página no disponible (HTTP {code}).")
        return final_url, body


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.parts: list[str] = []
        self.hidden = 0
        self.anchor: tuple[str, list[str]] | None = None
        self.noindex = False
        self.nofollow = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "template"):
            self.hidden += 1
        if tag == "meta" and attrs.get("name", "").lower() in ("robots", AGENT.lower()):
            directives = attrs.get("content", "").lower()
            self.noindex |= "noindex" in directives or "none" in directives
            self.nofollow |= "nofollow" in directives or "none" in directives
        if tag == "a" and not self.hidden and "nofollow" not in attrs.get("rel", "").lower():
            self.anchor = (attrs.get("href", ""), [])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "a" and self.anchor:
            self.links.append((self.anchor[0], " ".join(self.anchor[1])))
            self.anchor = None

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.anchor:
                self.anchor[1].append(data)


def parse_page(html: str) -> PageParser:
    parser = PageParser()
    parser.feed(html)
    return parser


def extract_contacts(html: str, url: str) -> list[dict]:
    parser = parse_page(html)
    if parser.noindex:
        return []
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    path = unquote(urlsplit(url).path).lower()
    if any(w in path for w in EXCLUDED_WORDS):
        return []
    page_is_contact = any(w in path for w in CONTACT_WORDS)
    # Mailto addresses are explicit publication; plain text must appear on a
    # contact page or next to language indicating a professional purpose.
    occurrences = [(m.group(), text[max(0, m.start()-130):m.end()+130]) for m in EMAIL_RE.finditer(text)]
    for href, label in parser.links:
        if href.lower().startswith("mailto:"):
            address = unquote(href[7:].split("?", 1)[0])
            for m in EMAIL_RE.finditer(address):
                # Find the surrounding visible text, rather than infer purpose
                # from an address that happens to be embedded in a footer.
                index = text.lower().find(label.lower()) if label.strip() else -1
                context = text[max(0, index-130):index+len(label)+130] if index >= 0 else label
                if not context.strip():
                    context = f"Enlace mailto publicado en esta página: {m.group()}"
                occurrences.append((m.group(), context))
    found = {}
    for raw, evidence in occurrences:
        try:
            email = validate_email(raw, check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            continue
        local, domain = email.split("@", 1)
        if domain in ("example.com", "example.org", "example.net") or domain == "thebookswanderer.com":
            continue
        if any(w in local for w in ("noreply", "no-reply", "privacy", "privacidad", "abuse", "legal", "support", "soporte", "billing", "jobs", "career", "dpo", "newsletter", "unsubscribe")):
            continue
        # The local part itself (e.g. contact@...) is not proof of purpose.
        context = EMAIL_RE.sub("", evidence).lower()
        explicit = any(w in context for w in CONTACT_WORDS)
        role = any(local == w or local.startswith(w + ".") for w in ("contact", "contacto", "hello", "hola", "info", "editorial", "press", "prensa", "partnerships", "advertising", "colaboraciones"))
        if not explicit and not (page_is_contact and role):
            continue
        purpose = "Colaboraciones / publicidad" if any(w in context for w in ("colabor", "collabor", "partnership", "advertis", "publicidad", "sponsor")) else "Contacto profesional; revisar pertinencia"
        # An empty icon/mailto label must not replace a useful visible excerpt.
        if email not in found or len(evidence) > len(found[email]["evidence"]):
            found[email] = {"email": email, "source_url": url, "evidence": evidence[:300], "purpose": purpose}
    return list(found.values())[:12]


def collect_site(source: dict) -> tuple[list[dict], str]:
    url = normalize_url(source["url"])
    fetcher = Fetcher(url)
    contacts, warnings = {}, []
    try:
        root_url, root_html = fetcher.page(url)
        root = parse_page(root_html)
        if root.noindex:
            return [], "El sitio indica noindex; no se recopilaron contactos."
        # A source may itself be an explicitly selected contact page.
        for item in extract_contacts(root_html, root_url):
            contacts[item["email"]] = item
        links = []
        if not root.nofollow:
            for href, label in root.links:
                if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                try:
                    linked = normalize_url(urljoin(root_url, href))
                except ResearchError:
                    continue
                path = unquote(urlsplit(linked).path).lower()
                hint = path + " " + label.lower()
                if site_host(linked) == site_host(url) and any(w in hint for w in CONTACT_WORDS) and not any(w in path for w in EXCLUDED_WORDS) and linked not in links and linked != root_url:
                    links.append(linked)
        for linked in links[:4]:
            try:
                final_url, html = fetcher.page(linked)
                for item in extract_contacts(html, final_url):
                    contacts[item["email"]] = item
            except (ResearchError, httpx.HTTPError, OSError):
                warnings.append("Una página no estuvo disponible o no permitió la revisión.")
        summary = f"{len(contacts)} contacto(s) publicado(s) encontrado(s)."
        if not contacts:
            summary += " Puede usar formulario o no publicar correo profesional."
        if warnings:
            summary += f" {len(warnings)} página(s) omitida(s)."
        return list(contacts.values())[:12], summary
    finally:
        fetcher.close()
