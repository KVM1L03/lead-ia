"""Test isolation for maps_bridge: ensure MockMapsProvider regardless of os.environ.

litellm calls load_dotenv() at import time, which can set MAPS_PROVIDER=serpapi
from the user's .env before maps_bridge.config.Settings() is instantiated.
Patching settings.MAPS_PROVIDER here ensures every test in this directory gets
a clean MockMapsProvider.
"""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _mock_provider_isolation(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    from maps_bridge.config import settings

    monkeypatch.setattr(settings, "MAPS_PROVIDER", "mock")
    yield
