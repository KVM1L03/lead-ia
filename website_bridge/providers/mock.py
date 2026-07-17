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
