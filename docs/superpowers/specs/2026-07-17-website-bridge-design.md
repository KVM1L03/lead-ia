# website_bridge MCP server — Design

**Date:** 2026-07-17
**Status:** Approved (design)
**Branch:** `feat/website-bridge`

## Problem

The pipeline qualifies leads on Google Places metadata alone. It has no
signal about the prospect's *website* — whether it looks modern, offers
online booking, exposes a contact path, etc. We want a deterministic,
LLM-free source of website facts that the qualifier can later consume.

This spec covers **only** the bridge itself. Wiring the facts into the
`ai_worker` LangGraph/qualifier is an explicit follow-up feature, out of
scope here (keeps this PR under the 400-LOC backend LLM-review ceiling).

## Goals

- A new microservice `website_bridge/` that fetches a URL and returns a
  strict `WebsiteFacts` model.
- 100% deterministic extraction via BeautifulSoup4 — **no JS rendering, no
  LLM**.
- Zero-trust: the only process besides `maps_bridge` allowed to make
  outbound HTTP calls (invariant #5). `httpx` confined to
  `website_bridge/providers/http.py`.
- Pluggable providers (`mock`, `http`) mirroring the `maps_bridge` pattern.
- Persistent server-side in-memory cache, keyed per domain.
- Full unit-test coverage of extraction against HTML fixtures.

## Non-goals

- No `ai_worker` / LangGraph / qualifier changes.
- No JS execution / headless browser.
- No persistence beyond the in-process cache (no SQLite, unlike maps_bridge).
- No auth (consistent with the rest of this local-first demo).

## Architecture

New microservice mirroring `maps_bridge/`'s layout. Runs as a **persistent
streamable-http MCP server** — `mcp.run(transport="http", host="0.0.0.0",
port=8100)` — so the in-memory cache genuinely persists across tool calls
and clients connect to one long-lived process (not stdio spawn per call).
Added as a `docker-compose` service.

```
shared/schemas.py            + WebsiteFacts        (invariant #6: schema in shared/)
website_bridge/
  __init__.py
  config.py                  Settings: WEBSITE_PROVIDER, port, timeout, max bytes, redirects, TTL, UA
  errors.py                  RobotsDisallowedError, WebsiteFetchError
  extract.py                 extract_facts(html: bytes, final_url: str) -> WebsiteFacts   (pure, shared)
  cache.py                   InMemoryCache (per-domain) + CachingWebsiteProvider wrapper
  provider_factory.py        get_provider() with @lru_cache; mock | http
  providers/__init__.py      WebsiteProvider Protocol
  providers/mock.py          serves fixture HTML through extract_facts
  providers/http.py          httpx fetch + robots.txt gate -> extract_facts
  server.py                  FastMCP("website-bridge"); fetch_website_facts tool
  Dockerfile
  fixtures/dentist_with_booking.html
  fixtures/dentist_no_booking.html
  fixtures/outdated_2012.html
  tests/{__init__,test_extract,test_mock_provider,test_cache,test_http_provider,test_server}.py
```

### Key decision: shared extraction function

Providers differ **only in how they obtain the HTML bytes**. Both call
`extract.extract_facts(html_bytes, final_url)`:

- `mock` reads a fixture file's bytes → same parser as production.
- `http` fetches bytes over the network → same parser.

Consequences: unit tests exercise the real extraction logic against
fixtures; `httpx` stays confined to `providers/http.py`; the mock is a
faithful stand-in, not a divergent reimplementation.

## Data model (`shared/schemas.py`)

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

## `fetch_website_facts(url: str) -> WebsiteFacts` — http provider flow

1. Resolve the domain; fetch/parse `robots.txt` via stdlib
   `urllib.robotparser`. If `can_fetch(UA, url)` is False →
   **raise `RobotsDisallowedError`** (no partial/fabricated facts).
2. `httpx.AsyncClient(timeout=10, follow_redirects=True, max_redirects=3)`;
   stream the body and abort past **2 MB** → `WebsiteFetchError`.
3. User-Agent: `LeadForgeBot/1.0 (+https://github.com/KVM1L03/lead-ia)`.
4. Pass raw bytes + final (post-redirect) URL to `extract_facts`.

Network/timeout/HTTP-status failures raise `WebsiteFetchError`. The mock
provider never touches robots or the network.

## Extraction rules (`extract_facts`, BS4, no JS)

| Field | Rule |
|---|---|
| `has_ssl` | final URL scheme == `https` |
| `has_viewport_meta` | `<meta name="viewport">` present |
| `generator_meta` | `<meta name="generator">` content, else `None` |
| `page_size_kb` | `len(raw_bytes) / 1024`, rounded to 2 dp |
| `has_contact_form` | a `<form>` containing a text/email input, **or** a link whose href/text contains `kontakt`/`contact` (case-insensitive) |
| `booking_keywords_found` | dedup, order-stable list of matched keywords from `{booking, umów, rezerwacja, zarezerwuj, calendly, booksy, appointment, e-rejestracja}` found in link hrefs/text or visible text (case-insensitive) |
| `has_phone_in_markup` | a `tel:` link **or** a phone-shaped regex match in the markup |
| `social_links` | absolute hrefs pointing to facebook / instagram / linkedin / youtube / twitter / x / tiktok (deduped) |
| `has_schema_org` | `<script type="application/ld+json">` **or** any `itemtype` attribute containing `schema.org` |
| `copyright_year` | 4-digit year (`19xx`/`20xx`) near `©`/`&copy;`/`copyright`; take the latest match, else `None` |
| `visible_text_excerpt` | `get_text(" ")` after removing `<script>`/`<style>`, whitespace-collapsed, truncated to 3000 chars |

Keyword/social matching is case-insensitive. Polish keywords are matched on
a casefolded copy so `Umów` matches `umów`.

## Cache

`InMemoryCache` keyed by **normalized domain** (`urlparse(url).netloc`,
lowercased, `www.` stripped) with a TTL (default 24h). `CachingWebsiteProvider`
wraps the active provider transparently, exactly like `CachingMapsProvider`
in `maps_bridge`.

**Documented tradeoff:** keying per domain (as the task requires) means two
different paths on the same domain share one cache entry — acceptable for
this demo, and the explicit requirement. Cache lives in the persistent
server process, so it survives across tool calls.

## Providers

```python
class WebsiteProvider(Protocol):
    async def fetch_website_facts(self, url: str) -> WebsiteFacts: ...
```

- `MockWebsiteProvider` — maps a small set of sentinel URLs to fixture
  files, reads the bytes, and runs them through `extract_facts`. Unknown
  URLs fall back to a deterministic default fixture (documented).
- `HttpWebsiteProvider` — the flow above.

`provider_factory.get_provider()` uses `@lru_cache`, selecting on
`settings.WEBSITE_PROVIDER` (`mock` default), and wraps the result in
`CachingWebsiteProvider`. Unknown provider → `NotImplementedError`, matching
maps_bridge.

## Fixtures (3 scenarios)

- **dentist_with_booking.html** — dentysta z bookingiem online: viewport
  meta, schema.org JSON-LD, a contact `<form>`, Booksy + Calendly links,
  social links, a `tel:` phone, `© 2026`.
- **dentist_no_booking.html** — dentysta bez bookingu: viewport, contact
  `<form>`, phone, social links; **no** booking keywords; recent copyright.
- **outdated_2012.html** — przestarzała strona z 2012: no viewport,
  `<meta name="generator" content="WordPress 3.2">`, `© 2012`, no
  schema.org, no booking keywords, minimal markup.

## Testing

- `test_extract.py` — parametrized over the 3 fixtures, asserting **every**
  `WebsiteFacts` field per scenario (task requirement #4).
- `test_mock_provider.py` — sentinel URLs → expected facts; unknown-URL
  fallback.
- `test_cache.py` — a second call for the same domain does **not** re-invoke
  the inner provider; different domains do.
- `test_http_provider.py` — `httpx.MockTransport` for a happy fetch; body
  over 2 MB → `WebsiteFetchError`; robots disallow → `RobotsDisallowedError`.
  No real network.
- `test_server.py` — `fetch_website_facts` is registered on the FastMCP
  instance and returns facts under the mock provider.

All backend tests run with no network and no LLM (consistent with CI).

## Dependencies & wiring

- Add `beautifulsoup4>=4.12` to `pyproject.toml` (`httpx` already present;
  robots via stdlib `urllib.robotparser`).
- `.env.example`: `WEBSITE_PROVIDER=mock`, `WEBSITE_BRIDGE_PORT=8100`.
- `website_bridge/Dockerfile` (mirrors maps_bridge) + a `website_bridge`
  service in `docker-compose`.
- Extend the `mypy` target list (Makefile / CI) to include `website_bridge`.

## Risks / open questions

- Phone-regex false positives on numeric-heavy pages — kept conservative
  (require `tel:` or a clearly phone-shaped pattern) and covered by fixtures.
- `robotparser` fetching robots.txt is itself a network call in the http
  provider; failures to fetch robots.txt are treated as "allowed" (standard
  RFC behavior), and this path is only exercised in the http provider, never
  in tests against the network.
