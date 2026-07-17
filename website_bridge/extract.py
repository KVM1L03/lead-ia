"""Deterministic website-fact extraction. No JS, no LLM — pure BeautifulSoup4."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from shared.schemas import WebsiteFacts

_BOOKING_KEYWORDS = [
    "booking",
    "umów",
    "rezerwacja",
    "zarezerwuj",
    "calendly",
    "booksy",
    "appointment",
    "e-rejestracja",
]
_SOCIAL_DOMAINS = (
    "facebook.",
    "instagram.",
    "linkedin.",
    "youtube.",
    "tiktok.",
    "twitter.",
    "x.com",
)
_CONTACT_TOKENS = ("kontakt", "contact")
_MAX_EXCERPT = 3000

_PHONE_RE = re.compile(r"(?:\+?\d[\s\-().]?){7,}\d")
_YEAR_RE = re.compile(r"(?:©|copyright)\D{0,15}((?:19|20)\d{2})", re.IGNORECASE)


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": re.compile(rf"^{name}$", re.IGNORECASE)})
    if isinstance(tag, Tag):
        content = tag.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def _detect_contact(soup: BeautifulSoup, hrefs: list[str], link_texts: list[str]) -> bool:
    for form in soup.find_all("form"):
        for inp in form.find_all("input"):
            if str(inp.get("type") or "text").lower() in ("text", "email"):
                return True
        if form.find("textarea") is not None:
            return True
    for href, text in zip(hrefs, link_texts, strict=True):
        blob = f"{href} {text}".lower()
        if any(tok in blob for tok in _CONTACT_TOKENS):
            return True
    return False


def _social_links(hrefs: list[str]) -> list[str]:
    found: list[str] = []
    for href in hrefs:
        host = urlparse(href).netloc.lower()
        if host and any(d in host for d in _SOCIAL_DOMAINS) and href not in found:
            found.append(href)
    return found


def _has_schema_org(soup: BeautifulSoup) -> bool:
    if soup.find("script", attrs={"type": re.compile(r"application/ld\+json", re.IGNORECASE)}):
        return True
    return (
        soup.find(True, attrs={"itemtype": re.compile(r"schema\.org", re.IGNORECASE)}) is not None
    )


def extract_facts(html: bytes, final_url: str) -> WebsiteFacts:
    soup = BeautifulSoup(html, "html.parser")

    anchors = [a for a in soup.find_all("a", href=True) if isinstance(a, Tag)]
    hrefs = [str(a.get("href", "")) for a in anchors]
    link_texts = [a.get_text(" ") for a in anchors]

    has_viewport = _meta_content(soup, "viewport") is not None
    generator_meta = _meta_content(soup, "generator")
    has_contact_form = _detect_contact(soup, hrefs, link_texts)
    has_phone_link = soup.find("a", href=re.compile(r"^tel:", re.IGNORECASE)) is not None
    has_schema = _has_schema_org(soup)
    social = _social_links(hrefs)

    # Strip non-visible tags before reading text.
    for tag in soup(["script", "style"]):
        tag.decompose()
    visible_text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    lower_blob = " ".join([visible_text.casefold()] + [h.casefold() for h in hrefs])

    booking = [kw for kw in _BOOKING_KEYWORDS if kw.casefold() in lower_blob]

    has_phone = has_phone_link or _PHONE_RE.search(visible_text) is not None

    years = [int(y) for y in _YEAR_RE.findall(visible_text)]
    copyright_year = max(years) if years else None

    return WebsiteFacts(
        has_ssl=urlparse(final_url).scheme == "https",
        has_viewport_meta=has_viewport,
        generator_meta=generator_meta,
        page_size_kb=round(len(html) / 1024, 2),
        has_contact_form=has_contact_form,
        booking_keywords_found=booking,
        has_phone_in_markup=has_phone,
        social_links=social,
        has_schema_org=has_schema,
        copyright_year=copyright_year,
        visible_text_excerpt=visible_text[:_MAX_EXCERPT],
    )
