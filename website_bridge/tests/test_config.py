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
