from typing import Protocol

from shared.schemas import WebsiteFacts


class WebsiteProvider(Protocol):
    async def fetch_website_facts(self, url: str) -> WebsiteFacts: ...
