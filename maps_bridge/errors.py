"""Domain errors for the maps_bridge service."""


class RateLimitError(Exception):
    """Raised when a Maps provider returns HTTP 429."""
