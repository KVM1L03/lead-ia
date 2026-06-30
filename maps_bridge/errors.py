"""Domain errors for the maps_bridge service."""


class RateLimitError(Exception):
    """Raised when SerpAPI returns HTTP 429."""
