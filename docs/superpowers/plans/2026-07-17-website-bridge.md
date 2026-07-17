# website_bridge MCP server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new zero-trust MCP microservice `website_bridge` that returns deterministic, LLM-free facts about a website's HTML.

**Architecture:** Mirrors `maps_bridge/`. A pure `extract_facts(html, url)` function is shared by two pluggable providers (`mock`, `http`); `httpx` is confined to the http provider. A persistent streamable-http FastMCP server holds a per-domain in-memory cache across calls. No `ai_worker` wiring in this plan.

**Tech Stack:** Python 3.12, FastMCP 3.4, BeautifulSoup4, httpx (async), Pydantic v2 strict, stdlib `urllib.robotparser`.

**Spec:** `docs/superpowers/specs/2026-07-17-website-bridge-design.md`

## Global Constraints

- Pydantic v2 strict everywhere: `model_config = ConfigDict(strict=True, extra="forbid")`. Zero `Any`, zero `as unknown`. (invariant #4)
- `WebsiteFacts` schema lives in `shared/schemas.py`. (invariant #6)
- `httpx` may only be imported in `website_bridge/providers/http.py`. No other `website_bridge` module — and nothing in `ai_worker/` — imports it. (invariant #5)
- No LLM, no JS rendering anywhere in this service.
- Blocking/sync calls inside a coroutine MUST go through `await asyncio.to_thread(...)` (applies to `robotparser.read()`). See `context/code-standards.md` § Async / Concurrency.
- All tests run with no network and no LLM (CI parity).
- Match existing `maps_bridge` idioms: `pydantic_settings.BaseSettings`, `@lru_cache` provider factory, `Protocol` provider interface.
- `visible_text_excerpt` max length 3000 chars.
- User-Agent: `LeadForgeBot/1.0 (+https://github.com/KVM1L03/lead-ia)`.

---

### Task 1: `WebsiteFacts` schema in `shared/`

**Files:**
- Modify: `shared/schemas.py`
- Test: `shared/tests/test_schemas.py`

**Interfaces:**
- Produces: `WebsiteFacts` Pydantic model with fields `has_ssl: bool`, `has_viewport_meta: bool`, `generator_meta: str | None`, `page_size_kb: float`, `has_contact_form: bool`, `booking_keywords_found: list[str]`, `has_phone_in_markup: bool`, `social_links: list[str]`, `has_schema_org: bool`, `copyright_year: int | None`, `visible_text_excerpt: str` (max 3000).

- [ ] **Step 1: Write the failing test**

Add to `shared/tests/test_schemas.py`:

```python
def test_website_facts_roundtrips_and_enforces_excerpt_limit() -> None:
    from pydantic import ValidationError

    from shared.schemas import WebsiteFacts

    facts = WebsiteFacts(
        has_ssl=True,
        has_viewport_meta=True,
        generator_meta=None,
        page_size_kb=12.5,
        has_contact_form=True,
        booking_keywords_found=["booksy"],
        has_phone_in_markup=True,
        social_links=["https://facebook.com/x"],
        has_schema_org=True,
        copyright_year=2026,
        visible_text_excerpt="hello",
    )
    assert facts.model_dump()["copyright_year"] == 2026
    assert WebsiteFacts.model_validate_json(facts.model_dump_json()).has_ssl is True

    with pytest.raises(ValidationError):
        WebsiteFacts(
            has_ssl=True,
            has_viewport_meta=False,
            generator_meta=None,
            page_size_kb=1.0,
            has_contact_form=False,
            booking_keywords_found=[],
            has_phone_in_markup=False,
            social_links=[],
            has_schema_org=False,
            copyright_year=None,
            visible_text_excerpt="x" * 3001,
        )
```

Ensure `import pytest` is present at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest shared/tests/test_schemas.py::test_website_facts_roundtrips_and_enforces_excerpt_limit -v`
Expected: FAIL — `ImportError: cannot import name 'WebsiteFacts'`

- [ ] **Step 3: Add the model**

Append to `shared/schemas.py` (the `Annotated`, `ConfigDict`, `StringConstraints`, `BaseModel` imports already exist at the top of the file):

```python
class WebsiteFacts(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    has_ssl: bool
    has_viewport_meta: bool
    generator_meta: str | None = None
    page_size_kb: float
    has_contact_form: bool
    booking_keywords_found: list[str]
    has_phone_in_markup: bool
    social_links: list[str]
    has_schema_org: bool
    copyright_year: int | None = None
    visible_text_excerpt: Annotated[str, StringConstraints(max_length=3000)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest shared/tests/test_schemas.py::test_website_facts_roundtrips_and_enforces_excerpt_limit -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shared/schemas.py shared/tests/test_schemas.py
git commit -m "feat(shared): add WebsiteFacts schema for website_bridge"
```

---

### Task 2: Package scaffold — config, errors, provider Protocol

**Files:**
- Create: `website_bridge/__init__.py` (empty)
- Create: `website_bridge/config.py`
- Create: `website_bridge/errors.py`
- Create: `website_bridge/providers/__init__.py`
- Create: `website_bridge/tests/__init__.py` (empty)
- Test: `website_bridge/tests/test_config.py`

**Interfaces:**
- Produces:
  - `website_bridge.config.settings` with attrs `WEBSITE_PROVIDER: str`, `WEBSITE_BRIDGE_PORT: int`, `WEBSITE_FETCH_TIMEOUT: float`, `WEBSITE_MAX_BYTES: int`, `WEBSITE_MAX_REDIRECTS: int`, `WEBSITE_CACHE_TTL: int`, `WEBSITE_USER_AGENT: str`.
  - `website_bridge.errors.RobotsDisallowedError(url: str)` (has `.url`), `website_bridge.errors.WebsiteFetchError`.
  - `website_bridge.providers.WebsiteProvider` Protocol with `async def fetch_website_facts(self, url: str) -> WebsiteFacts`.

- [ ] **Step 1: Write the failing test**

Create `website_bridge/tests/test_config.py`:

```python
def test_defaults_are_mock_and_typed() -> None:
    from website_bridge.config import settings

    assert settings.WEBSITE_PROVIDER == "mock"
    assert settings.WEBSITE_BRIDGE_PORT == 8100
    assert settings.WEBSITE_MAX_BYTES == 2_000_000
    assert settings.WEBSITE_MAX_REDIRECTS == 3
    assert "LeadForgeBot" in settings.WEBSITE_USER_AGENT


def test_errors_carry_url() -> None:
    from website_bridge.errors import RobotsDisallowedError, WebsiteFetchError

    err = RobotsDisallowedError("https://x.example/a")
    assert err.url == "https://x.example/a"
    assert issubclass(WebsiteFetchError, Exception)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest website_bridge/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'website_bridge'`

- [ ] **Step 3: Create the scaffold files**

`website_bridge/__init__.py`: empty file.
`website_bridge/tests/__init__.py`: empty file.

`website_bridge/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(strict=True)

    WEBSITE_PROVIDER: str = "mock"
    WEBSITE_BRIDGE_PORT: int = 8100
    WEBSITE_FETCH_TIMEOUT: float = 10.0
    WEBSITE_MAX_BYTES: int = 2_000_000
    WEBSITE_MAX_REDIRECTS: int = 3
    WEBSITE_CACHE_TTL: int = 86400
    WEBSITE_USER_AGENT: str = "LeadForgeBot/1.0 (+https://github.com/KVM1L03/lead-ia)"


settings = Settings()
```

`website_bridge/errors.py`:

```python
"""Domain errors for the website_bridge service."""


class RobotsDisallowedError(Exception):
    """Raised when robots.txt disallows fetching the target URL."""

    def __init__(self, url: str) -> None:
        super().__init__(f"robots.txt disallows fetching: {url}")
        self.url = url


class WebsiteFetchError(Exception):
    """Raised when the target site cannot be fetched (timeout, size cap, HTTP error)."""
```

`website_bridge/providers/__init__.py`:

```python
from typing import Protocol

from shared.schemas import WebsiteFacts


class WebsiteProvider(Protocol):
    async def fetch_website_facts(self, url: str) -> WebsiteFacts: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest website_bridge/tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add website_bridge/__init__.py website_bridge/config.py website_bridge/errors.py website_bridge/providers/__init__.py website_bridge/tests/__init__.py website_bridge/tests/test_config.py
git commit -m "feat(website_bridge): scaffold config, errors, provider protocol"
```

---

### Task 3: Fixtures + `extract_facts` (the core)

**Files:**
- Create: `website_bridge/fixtures/dentist_with_booking.html`
- Create: `website_bridge/fixtures/dentist_no_booking.html`
- Create: `website_bridge/fixtures/outdated_2012.html`
- Create: `website_bridge/extract.py`
- Test: `website_bridge/tests/test_extract.py`

**Interfaces:**
- Consumes: `shared.schemas.WebsiteFacts`.
- Produces: `website_bridge.extract.extract_facts(html: bytes, final_url: str) -> WebsiteFacts`.

**Fixture field expectations** (the test asserts these exactly):

| Fixture | url passed | ssl | viewport | generator | contact_form | booking | phone | social | schema_org | year |
|---|---|---|---|---|---|---|---|---|---|---|
| dentist_with_booking | `https://dentysta-booking.example` | T | T | None | T | `["umów","rezerwacja","calendly","booksy"]` | T | 2 | T | 2026 |
| dentist_no_booking | `https://dentysta-classic.example` | T | T | None | T | `[]` | T | 1 | F | 2025 |
| outdated_2012 | `http://dentysta-2012.example` | F | F | `"WordPress 3.2"` | T (via link) | `[]` | F | 0 | F | 2012 |

- [ ] **Step 1: Create the three fixtures**

`website_bridge/fixtures/dentist_with_booking.html`:

```html
<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Uśmiech Dental — nowoczesny gabinet</title>
  <script type="application/ld+json">
  {"@context":"https://schema.org","@type":"Dentist","name":"Uśmiech Dental"}
  </script>
</head>
<body>
  <h1>Uśmiech Dental</h1>
  <p>Umów wizytę online — rezerwacja w kilka sekund.</p>
  <a href="https://booksy.com/pl-pl/usmiech-dental">Rezerwacja przez Booksy</a>
  <a href="https://calendly.com/usmiech-dental/wizyta">Zarezerwuj w kalendarzu</a>
  <a href="tel:+48221234500">+48 22 123 45 00</a>
  <a href="https://facebook.com/usmiechdental">Facebook</a>
  <a href="https://instagram.com/usmiechdental">Instagram</a>
  <form action="/kontakt" method="post">
    <input type="email" name="email" placeholder="Twój e-mail">
    <textarea name="wiadomosc"></textarea>
    <button type="submit">Wyślij</button>
  </form>
  <footer>© 2026 Uśmiech Dental sp. z o.o.</footer>
</body>
</html>
```

`website_bridge/fixtures/dentist_no_booking.html`:

```html
<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gabinet Stomatologiczny Kowalski</title>
</head>
<body>
  <h1>Gabinet Stomatologiczny Kowalski</h1>
  <p>Zapraszamy do naszego gabinetu w centrum miasta.</p>
  <a href="tel:+48228887766">+48 22 888 77 66</a>
  <a href="https://facebook.com/gabinetkowalski">Znajdź nas na Facebooku</a>
  <form action="/wyslij" method="post">
    <input type="text" name="imie" placeholder="Imię">
    <input type="email" name="email" placeholder="E-mail">
    <button type="submit">Wyślij zapytanie</button>
  </form>
  <footer>© 2025 Gabinet Kowalski</footer>
</body>
</html>
```

`website_bridge/fixtures/outdated_2012.html`:

```html
<!doctype html>
<html>
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <meta name="generator" content="WordPress 3.2">
  <title>Dentysta - Stara Strona</title>
</head>
<body>
  <h1>Witamy na naszej stronie</h1>
  <p>Nasza praktyka dentystyczna zaprasza Panstwa do wspolpracy.</p>
  <a href="/kontakt.html">Kontakt</a>
  <p>Zadzwon do nas w godzinach otwarcia.</p>
  <p>Copyright 2012 - Wszelkie prawa zastrzezone.</p>
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

Create `website_bridge/tests/test_extract.py`:

```python
from pathlib import Path

import pytest

from website_bridge.extract import extract_facts

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


def test_booking_fixture_full_field_extraction() -> None:
    facts = extract_facts(_load("dentist_with_booking.html"), "https://dentysta-booking.example")
    assert facts.has_ssl is True
    assert facts.has_viewport_meta is True
    assert facts.generator_meta is None
    assert facts.page_size_kb > 0
    assert facts.has_contact_form is True
    assert facts.booking_keywords_found == ["umów", "rezerwacja", "calendly", "booksy"]
    assert facts.has_phone_in_markup is True
    assert len(facts.social_links) == 2
    assert all("facebook" in s or "instagram" in s for s in facts.social_links)
    assert facts.has_schema_org is True
    assert facts.copyright_year == 2026
    assert 0 < len(facts.visible_text_excerpt) <= 3000
    assert "Umów" in facts.visible_text_excerpt


def test_no_booking_fixture() -> None:
    facts = extract_facts(_load("dentist_no_booking.html"), "https://dentysta-classic.example")
    assert facts.has_ssl is True
    assert facts.has_viewport_meta is True
    assert facts.generator_meta is None
    assert facts.has_contact_form is True
    assert facts.booking_keywords_found == []
    assert facts.has_phone_in_markup is True
    assert len(facts.social_links) == 1
    assert facts.has_schema_org is False
    assert facts.copyright_year == 2025


def test_outdated_fixture() -> None:
    facts = extract_facts(_load("outdated_2012.html"), "http://dentysta-2012.example")
    assert facts.has_ssl is False
    assert facts.has_viewport_meta is False
    assert facts.generator_meta == "WordPress 3.2"
    assert facts.has_contact_form is True
    assert facts.booking_keywords_found == []
    assert facts.has_phone_in_markup is False
    assert facts.social_links == []
    assert facts.has_schema_org is False
    assert facts.copyright_year == 2012


def test_excerpt_is_truncated_to_3000() -> None:
    html = b"<html><body>" + (b"word " * 2000) + b"</body></html>"
    facts = extract_facts(html, "https://x.example")
    assert len(facts.visible_text_excerpt) <= 3000
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest website_bridge/tests/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'website_bridge.extract'` (also `bs4` may be missing — Task 8 adds it; if `bs4` import fails here, run `uv add beautifulsoup4` first per Task 8 Step 1, then continue).

- [ ] **Step 4: Implement `extract.py`**

`website_bridge/extract.py`:

```python
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
    for href, text in zip(hrefs, link_texts):
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
    return soup.find(attrs={"itemtype": re.compile(r"schema\.org", re.IGNORECASE)}) is not None


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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest website_bridge/tests/test_extract.py -v`
Expected: PASS (4 passed). If `bs4` import fails, complete Task 8 Step 1 (`uv add beautifulsoup4`) first.

- [ ] **Step 6: Commit**

```bash
git add website_bridge/fixtures website_bridge/extract.py website_bridge/tests/test_extract.py
git commit -m "feat(website_bridge): deterministic extract_facts + HTML fixtures"
```

---

### Task 4: Mock provider

**Files:**
- Create: `website_bridge/providers/mock.py`
- Test: `website_bridge/tests/test_mock_provider.py`

**Interfaces:**
- Consumes: `website_bridge.extract.extract_facts`, `shared.schemas.WebsiteFacts`.
- Produces: `website_bridge.providers.mock.MockWebsiteProvider` implementing `async def fetch_website_facts(self, url: str) -> WebsiteFacts`. Sentinel URLs: `https://dentysta-booking.example`, `https://dentysta-classic.example`, `http://dentysta-2012.example`. Unknown URL → falls back to `dentist_no_booking.html`.

- [ ] **Step 1: Write the failing test**

Create `website_bridge/tests/test_mock_provider.py`:

```python
from website_bridge.providers.mock import MockWebsiteProvider


async def test_booking_sentinel_returns_booking_facts() -> None:
    provider = MockWebsiteProvider()
    facts = await provider.fetch_website_facts("https://dentysta-booking.example")
    assert "booksy" in facts.booking_keywords_found
    assert facts.copyright_year == 2026


async def test_outdated_sentinel_has_no_ssl() -> None:
    provider = MockWebsiteProvider()
    facts = await provider.fetch_website_facts("http://dentysta-2012.example")
    assert facts.has_ssl is False
    assert facts.generator_meta == "WordPress 3.2"


async def test_unknown_url_falls_back_deterministically() -> None:
    provider = MockWebsiteProvider()
    facts = await provider.fetch_website_facts("https://something-unknown.example")
    assert facts.booking_keywords_found == []
    assert facts.has_ssl is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest website_bridge/tests/test_mock_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'website_bridge.providers.mock'`

- [ ] **Step 3: Implement `providers/mock.py`**

```python
"""Mock WebsiteProvider — serves fixture HTML through the real extract_facts."""

from __future__ import annotations

from pathlib import Path

from shared.schemas import WebsiteFacts
from website_bridge.extract import extract_facts

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"

_URL_TO_FIXTURE = {
    "https://dentysta-booking.example": "dentist_with_booking.html",
    "https://dentysta-classic.example": "dentist_no_booking.html",
    "http://dentysta-2012.example": "outdated_2012.html",
}
_DEFAULT_FIXTURE = "dentist_no_booking.html"


class MockWebsiteProvider:
    async def fetch_website_facts(self, url: str) -> WebsiteFacts:
        fixture = _URL_TO_FIXTURE.get(url, _DEFAULT_FIXTURE)
        html = (_FIXTURE_DIR / fixture).read_bytes()
        return extract_facts(html, url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest website_bridge/tests/test_mock_provider.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add website_bridge/providers/mock.py website_bridge/tests/test_mock_provider.py
git commit -m "feat(website_bridge): mock provider serving fixtures via extract_facts"
```

---

### Task 5: In-memory per-domain cache

**Files:**
- Create: `website_bridge/cache.py`
- Test: `website_bridge/tests/test_cache.py`

**Interfaces:**
- Consumes: `website_bridge.providers.WebsiteProvider`, `shared.schemas.WebsiteFacts`.
- Produces:
  - `website_bridge.cache.InMemoryCache(ttl: int = 86400)` with `get(domain: str) -> WebsiteFacts | None` and `set(domain: str, facts: WebsiteFacts) -> None`.
  - `website_bridge.cache.CachingWebsiteProvider(inner, cache)` implementing `async def fetch_website_facts(self, url: str) -> WebsiteFacts`; caches keyed by normalized domain (`netloc`, lowercased, leading `www.` stripped).

- [ ] **Step 1: Write the failing test**

Create `website_bridge/tests/test_cache.py`:

```python
from shared.schemas import WebsiteFacts
from website_bridge.cache import CachingWebsiteProvider, InMemoryCache


def _facts(year: int) -> WebsiteFacts:
    return WebsiteFacts(
        has_ssl=True,
        has_viewport_meta=True,
        generator_meta=None,
        page_size_kb=1.0,
        has_contact_form=False,
        booking_keywords_found=[],
        has_phone_in_markup=False,
        social_links=[],
        has_schema_org=False,
        copyright_year=year,
        visible_text_excerpt="",
    )


class _CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch_website_facts(self, url: str) -> WebsiteFacts:
        self.calls += 1
        return _facts(2000 + self.calls)


async def test_same_domain_hits_cache() -> None:
    inner = _CountingProvider()
    provider = CachingWebsiteProvider(inner, InMemoryCache())
    a = await provider.fetch_website_facts("https://clinic.example/home")
    b = await provider.fetch_website_facts("https://www.clinic.example/contact")
    assert inner.calls == 1
    assert a.copyright_year == b.copyright_year


async def test_different_domains_miss() -> None:
    inner = _CountingProvider()
    provider = CachingWebsiteProvider(inner, InMemoryCache())
    await provider.fetch_website_facts("https://a.example/")
    await provider.fetch_website_facts("https://b.example/")
    assert inner.calls == 2


def test_ttl_expiry_evicts(monkeypatch: object) -> None:
    import website_bridge.cache as cache_mod

    cache = InMemoryCache(ttl=10)
    times = iter([100.0, 130.0])
    monkeypatch.setattr(cache_mod.time, "time", lambda: next(times))  # type: ignore[attr-defined]
    cache.set("clinic.example", _facts(2020))
    assert cache.get("clinic.example") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest website_bridge/tests/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'website_bridge.cache'`

- [ ] **Step 3: Implement `cache.py`**

```python
"""In-memory per-domain cache and transparent caching wrapper for WebsiteProvider."""

from __future__ import annotations

import time
from urllib.parse import urlparse

from shared.schemas import WebsiteFacts
from website_bridge.providers import WebsiteProvider


def _domain_key(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


class InMemoryCache:
    def __init__(self, ttl: int = 86400) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, WebsiteFacts]] = {}

    def get(self, domain: str) -> WebsiteFacts | None:
        entry = self._store.get(domain)
        if entry is None:
            return None
        created_at, facts = entry
        if time.time() - created_at > self._ttl:
            del self._store[domain]
            return None
        return facts

    def set(self, domain: str, facts: WebsiteFacts) -> None:
        self._store[domain] = (time.time(), facts)


class CachingWebsiteProvider:
    """Transparent per-domain caching layer around any WebsiteProvider."""

    def __init__(self, inner: WebsiteProvider, cache: InMemoryCache) -> None:
        self._inner = inner
        self._cache = cache

    async def fetch_website_facts(self, url: str) -> WebsiteFacts:
        key = _domain_key(url)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        facts = await self._inner.fetch_website_facts(url)
        self._cache.set(key, facts)
        return facts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest website_bridge/tests/test_cache.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add website_bridge/cache.py website_bridge/tests/test_cache.py
git commit -m "feat(website_bridge): in-memory per-domain cache wrapper"
```

---

### Task 6: HTTP provider (httpx + robots.txt)

**Files:**
- Create: `website_bridge/providers/http.py`
- Test: `website_bridge/tests/test_http_provider.py`

**Interfaces:**
- Consumes: `website_bridge.extract.extract_facts`, `website_bridge.errors.{RobotsDisallowedError, WebsiteFetchError}`, `shared.schemas.WebsiteFacts`.
- Produces:
  - `website_bridge.providers.http.robots_allows(url: str, user_agent: str) -> bool` (module-level; monkeypatchable in tests).
  - `website_bridge.providers.http.HttpWebsiteProvider(user_agent: str, timeout: float = 10.0, max_bytes: int = 2_000_000, max_redirects: int = 3, transport: httpx.BaseTransport | None = None)` implementing `async def fetch_website_facts(self, url: str) -> WebsiteFacts`.

**Note:** `httpx` is imported ONLY in this file (invariant #5). `robotparser.read()` is blocking, so it runs via `asyncio.to_thread`.

- [ ] **Step 1: Write the failing test**

Create `website_bridge/tests/test_http_provider.py`:

```python
import httpx
import pytest

import website_bridge.providers.http as http_mod
from website_bridge.errors import RobotsDisallowedError, WebsiteFetchError
from website_bridge.providers.http import HttpWebsiteProvider

_HTML = (
    b"<html><head><meta name='viewport' content='width=device-width'></head>"
    b"<body><a href='https://facebook.com/x'>fb</a>"
    b"<footer>Copyright 2024</footer></body></html>"
)


def _allow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_mod, "robots_allows", lambda url, ua: True)


async def test_happy_fetch_extracts_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow(monkeypatch)
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_HTML))
    provider = HttpWebsiteProvider(user_agent="TestBot/1.0", transport=transport)
    facts = await provider.fetch_website_facts("https://clinic.example/")
    assert facts.has_ssl is True
    assert facts.has_viewport_meta is True
    assert facts.copyright_year == 2024
    assert len(facts.social_links) == 1


async def test_robots_disallow_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_mod, "robots_allows", lambda url, ua: False)
    provider = HttpWebsiteProvider(user_agent="TestBot/1.0")
    with pytest.raises(RobotsDisallowedError):
        await provider.fetch_website_facts("https://clinic.example/")


async def test_oversize_body_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow(monkeypatch)
    big = b"x" * 5000
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=big))
    provider = HttpWebsiteProvider(user_agent="TestBot/1.0", max_bytes=1000, transport=transport)
    with pytest.raises(WebsiteFetchError):
        await provider.fetch_website_facts("https://clinic.example/")


async def test_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow(monkeypatch)
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    provider = HttpWebsiteProvider(user_agent="TestBot/1.0", transport=transport)
    with pytest.raises(WebsiteFetchError):
        await provider.fetch_website_facts("https://clinic.example/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest website_bridge/tests/test_http_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'website_bridge.providers.http'`

- [ ] **Step 3: Implement `providers/http.py`**

```python
"""HTTP WebsiteProvider — the ONLY module in website_bridge that imports httpx."""

from __future__ import annotations

import asyncio
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from shared.schemas import WebsiteFacts
from website_bridge.errors import RobotsDisallowedError, WebsiteFetchError
from website_bridge.extract import extract_facts


def robots_allows(url: str, user_agent: str) -> bool:
    """Check robots.txt for *url*. Unreachable robots.txt is treated as allowed (RFC)."""
    parsed = urlparse(url)
    parser = robotparser.RobotFileParser()
    parser.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
    try:
        parser.read()
    except Exception:
        return True
    return parser.can_fetch(user_agent, url)


class HttpWebsiteProvider:
    def __init__(
        self,
        user_agent: str,
        timeout: float = 10.0,
        max_bytes: int = 2_000_000,
        max_redirects: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._ua = user_agent
        self._timeout = timeout
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._transport = transport

    async def fetch_website_facts(self, url: str) -> WebsiteFacts:
        if not await asyncio.to_thread(robots_allows, url, self._ua):
            raise RobotsDisallowedError(url)

        client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            max_redirects=self._max_redirects,
            headers={"User-Agent": self._ua},
            transport=self._transport,
        )
        try:
            async with client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            raise WebsiteFetchError(
                                f"Response exceeded {self._max_bytes} bytes: {url}"
                            )
                    final_url = str(response.url)
        except httpx.HTTPError as exc:
            raise WebsiteFetchError(f"Failed to fetch {url}: {exc}") from exc

        return extract_facts(bytes(body), final_url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest website_bridge/tests/test_http_provider.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add website_bridge/providers/http.py website_bridge/tests/test_http_provider.py
git commit -m "feat(website_bridge): http provider with robots gate and size cap"
```

---

### Task 7: Provider factory + FastMCP server

**Files:**
- Create: `website_bridge/provider_factory.py`
- Create: `website_bridge/server.py`
- Test: `website_bridge/tests/test_server.py`

**Interfaces:**
- Consumes: everything above; `website_bridge.config.settings`.
- Produces:
  - `website_bridge.provider_factory.get_provider(provider_name: str | None = None) -> WebsiteProvider` (`@lru_cache`), wrapping the selected provider in `CachingWebsiteProvider`. Unknown provider → `NotImplementedError`.
  - `website_bridge.server.mcp` (FastMCP instance) and `website_bridge.server.fetch_website_facts` tool.

- [ ] **Step 1: Write the failing test**

Create `website_bridge/tests/test_server.py`:

```python
import pytest

from website_bridge.provider_factory import get_provider
from website_bridge.server import fetch_website_facts, mcp


def test_server_imports() -> None:
    assert mcp is not None


async def test_tool_registered() -> None:
    tools = await mcp.list_tools()
    assert "fetch_website_facts" in {t.name for t in tools}


async def test_fetch_returns_facts_under_mock() -> None:
    facts = await fetch_website_facts(url="https://dentysta-booking.example")
    assert "booksy" in facts.booking_keywords_found


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    get_provider.cache_clear()
    monkeypatch.setattr("website_bridge.config.settings.WEBSITE_PROVIDER", "nope_xyz")
    try:
        with pytest.raises(NotImplementedError, match="Unknown provider"):
            get_provider()
    finally:
        get_provider.cache_clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest website_bridge/tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'website_bridge.provider_factory'`

- [ ] **Step 3: Implement `provider_factory.py`**

```python
"""Provider singleton for website_bridge — importable without starting the server."""

from __future__ import annotations

from functools import lru_cache

from website_bridge.cache import CachingWebsiteProvider, InMemoryCache
from website_bridge.config import settings
from website_bridge.providers import WebsiteProvider


@lru_cache(maxsize=4)
def get_provider(provider_name: str | None = None) -> WebsiteProvider:
    """Return a WebsiteProvider (mock or http), wrapped in a per-domain cache."""
    active = provider_name or settings.WEBSITE_PROVIDER
    inner: WebsiteProvider
    if active == "mock":
        from website_bridge.providers.mock import MockWebsiteProvider

        inner = MockWebsiteProvider()
    elif active == "http":
        from website_bridge.providers.http import HttpWebsiteProvider

        inner = HttpWebsiteProvider(
            user_agent=settings.WEBSITE_USER_AGENT,
            timeout=settings.WEBSITE_FETCH_TIMEOUT,
            max_bytes=settings.WEBSITE_MAX_BYTES,
            max_redirects=settings.WEBSITE_MAX_REDIRECTS,
        )
    else:
        raise NotImplementedError(f"Unknown provider: {active!r}")

    return CachingWebsiteProvider(inner, InMemoryCache(ttl=settings.WEBSITE_CACHE_TTL))
```

- [ ] **Step 4: Implement `server.py`**

```python
"""website_bridge MCP server — exposes the fetch_website_facts tool.

Runs as a persistent streamable-http server so the in-memory per-domain cache
survives across tool calls (not a stdio spawn per invocation).
"""

from fastmcp import FastMCP

from shared.schemas import WebsiteFacts
from website_bridge.config import settings
from website_bridge.provider_factory import get_provider

mcp = FastMCP("website-bridge")


@mcp.tool()
async def fetch_website_facts(url: str) -> WebsiteFacts:
    provider = get_provider()
    return await provider.fetch_website_facts(url)


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=settings.WEBSITE_BRIDGE_PORT,
        show_banner=False,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest website_bridge/tests/test_server.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add website_bridge/provider_factory.py website_bridge/server.py website_bridge/tests/test_server.py
git commit -m "feat(website_bridge): provider factory + persistent http MCP server"
```

---

### Task 8: Dependency, env, Docker, and lint wiring

**Files:**
- Modify: `pyproject.toml` (add `beautifulsoup4>=4.12`)
- Modify: `.env.example`
- Create: `website_bridge/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `Makefile:28` (mypy target)
- Modify: `.github/workflows/ci.yml:42` (mypy target)

**Interfaces:** none (packaging/config only).

- [ ] **Step 1: Add the BeautifulSoup4 dependency**

Run: `uv add beautifulsoup4`
Expected: `pyproject.toml` gains `beautifulsoup4>=4.12` (or newer) under `dependencies`, and `uv.lock` updates. (If Task 3 already required this, this step is a no-op confirming it's present.)

- [ ] **Step 2: Add env vars to `.env.example`**

Add near the `MAPS_PROVIDER` block:

```bash
# website_bridge: deterministic website-fact extraction (mock | http)
WEBSITE_PROVIDER=mock
WEBSITE_BRIDGE_PORT=8100
```

- [ ] **Step 3: Create `website_bridge/Dockerfile`**

```dockerfile
# Local dev only. Persistent streamable-http MCP server for website facts.
#
# ── Stage 1: build venv ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --compile-bytecode

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN useradd --system --no-create-home --shell /bin/false appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY website_bridge/ ./website_bridge/
COPY shared/ ./shared/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8100

USER appuser

CMD ["python", "-m", "website_bridge.server"]
```

- [ ] **Step 4: Add the compose service**

In `docker-compose.yml`, after the `maps-bridge` service block (ends at line ~282, before the top-level `volumes:` key), add:

```yaml
  website-bridge:
    build:
      context: .
      dockerfile: website_bridge/Dockerfile
    ports:
      - "8100:8100"
    networks:
      - lead-forge
```

- [ ] **Step 5: Extend mypy targets**

In `Makefile` line 28, change:

```make
	uv run mypy api_gateway ai_worker maps_bridge shared
```
to:
```make
	uv run mypy api_gateway ai_worker maps_bridge website_bridge shared
```

In `.github/workflows/ci.yml` line 42, change:

```yaml
        run: uv run mypy api_gateway ai_worker maps_bridge shared
```
to:
```yaml
        run: uv run mypy api_gateway ai_worker maps_bridge website_bridge shared
```

- [ ] **Step 6: Run full lint + test**

Run: `make lint && make test`
Expected: ruff clean, mypy clean (including `website_bridge`), all pytest + vitest green.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .env.example website_bridge/Dockerfile docker-compose.yml Makefile .github/workflows/ci.yml
git commit -m "chore(website_bridge): deps, env, Dockerfile, compose, mypy wiring"
```

---

### Task 9: Final verification + PR

- [ ] **Step 1: Full suite green**

Run: `make lint && make test`
Expected: all green.

- [ ] **Step 2: Smoke the persistent server boots**

Run: `WEBSITE_PROVIDER=mock uv run python -m website_bridge.server &` then, after ~2s, `curl -s http://localhost:8100/ -o /dev/null -w "%{http_code}\n"`; then kill the background process.
Expected: the server starts and binds port 8100 (any HTTP response code confirms the listener is up). Note the exact MCP handshake path is not asserted here — this only confirms the persistent listener boots.

- [ ] **Step 3: Push and open PR**

```bash
git push -u origin feat/website-bridge
gh pr create --base main --title "feat: website_bridge MCP server (deterministic website facts)" --fill
```

Report the PR URL. Do NOT merge — wait for CI (`python`, `frontend`) + human approval. Fill the PR template: one-sentence summary, invariants checked (esp. #4 strict typing, #5 zero-trust httpx boundary, #6 schema in shared/), and the manual smoke from Step 2.

- [ ] **Step 4: Update the progress tracker**

Add a one-line entry to `context/progress-tracker.md` pointing at this plan and its status (per `CLAUDE.md` §2.4). Commit and push:

```bash
git add context/progress-tracker.md
git commit -m "docs(progress): record website_bridge bridge implementation"
git push
```

---

## Self-Review

**Spec coverage:**
- WebsiteFacts model (all 11 fields) → Task 1 ✓
- fetch_website_facts tool → Task 7 ✓
- httpx timeout 10s / 2MB cap / 3 redirects → Task 6 ✓
- Unique bot User-Agent → Task 2 (config) + Task 6 (sent) ✓
- robots.txt respect + RobotsDisallowedError → Task 6 ✓
- No JS, BS4 extraction → Task 3 ✓
- booking_keywords / has_contact_form / social_links rules → Task 3 ✓
- mock + http providers → Tasks 4, 6 ✓
- 3 HTML fixtures (booking / no-booking / 2012) → Task 3 ✓
- in-memory per-domain cache → Task 5 ✓
- persistent MCP session (http transport) → Task 7 ✓
- unit tests for all WebsiteFacts fields → Task 3 (`test_extract.py`) ✓
- zero-trust httpx confinement → Task 6 note + Global Constraints ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `extract_facts(html: bytes, final_url: str) -> WebsiteFacts`, `fetch_website_facts(url: str) -> WebsiteFacts`, `get_provider(provider_name=None)`, `robots_allows(url, user_agent)`, `_domain_key` normalization used consistently across Tasks 3–7. ✓
