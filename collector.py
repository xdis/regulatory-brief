"""Bounded collection from a fixed public-source allowlist. No third-party packages."""
import re
from html.parser import HTMLParser
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse

SOURCES = [
    {'id': 'packaging', 'name': 'Packaging and packaging waste', 'topic': 'Packaging', 'owner': 'Packaging & Compliance', 'url': 'https://environment.ec.europa.eu/topics/waste-and-recycling/packaging-waste/packaging-packaging-waste-regulation_en'},
    {'id': 'ecodesign', 'name': 'Sustainable product design', 'topic': 'Product sustainability', 'owner': 'Product & Sustainability', 'url': 'https://commission.europa.eu/news-and-media/news/new-law-make-products-eu-market-more-sustainable-2024-07-19_en'},
    {'id': 'packaging-news', 'name': 'Packaging implementation update', 'topic': 'Packaging', 'owner': 'Packaging & Compliance', 'url': 'https://environment.ec.europa.eu/news/new-eu-rules-packaging-enter-application-2026-08-11_en'},
]
HOSTS = {urlparse(s['url']).hostname for s in SOURCES}

class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).scheme != 'https' or urlparse(newurl).hostname not in HOSTS:
            raise ValueError('Redirect outside the approved source domains.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.main = []; self.stack = []; self.title = []
    def handle_starttag(self, tag, attrs):
        if tag not in ('meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'):
            self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]
    def handle_data(self, data):
        if any(t in self.stack for t in ('script', 'style', 'nav', 'footer', 'header', 'noscript', 'svg')): return
        data = ' '.join(data.split())
        if not data: return
        if 'title' in self.stack: self.title.append(data)
        self.parts.append(data)
        if 'main' in self.stack or 'article' in self.stack: self.main.append(data)

def collect(source):
    req = Request(source['url'], headers={'User-Agent': 'RegulatoryBrief-PoC/0.1 (manual public-page review)', 'Accept': 'text/html'})
    with build_opener(PublicRedirect).open(req, timeout=20) as response:
        if 'text/html' not in response.headers.get('Content-Type', ''): raise ValueError('Expected an HTML source.')
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000: raise ValueError('Source exceeds the 2 MB collection limit.')
        page = Page(); page.feed(raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace'))
    body = '\n'.join(page.main or page.parts)
    if len(body) < 250: raise ValueError('Too little readable content. Source may require a browser or block collection.')
    if re.search(r'access denied|verify you are human|checking your browser', body[:600], re.I):
        raise ValueError('Source blocked automated collection.')
    return (' '.join(page.title) or source['name'])[:250], body[:150_000]
