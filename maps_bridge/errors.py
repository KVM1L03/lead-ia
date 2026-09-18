"""Domain errors for the maps_bridge service."""


class RateLimitError(Exception):
    """Raised when a Maps provider returns HTTP 429."""


class SiteFetchError(Exception):
    """Raised when fetch_site refuses or fails to retrieve a URL.

    Covers SSRF guard rejections (private/loopback/link-local address, bad
    scheme), unsupported content types, oversized responses, and timeouts.
    """
