"""Domain errors for the website_bridge service."""


class RobotsDisallowedError(Exception):
    """Raised when robots.txt disallows fetching the target URL."""

    def __init__(self, url: str) -> None:
        super().__init__(f"robots.txt disallows fetching: {url}")
        self.url = url


class WebsiteFetchError(Exception):
    """Raised when the target site cannot be fetched (timeout, size cap, HTTP error)."""
