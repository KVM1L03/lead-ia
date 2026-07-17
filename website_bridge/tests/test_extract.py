from pathlib import Path

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
    assert facts.booking_keywords_found == [
        "umów",
        "rezerwacja",
        "zarezerwuj",
        "calendly",
        "booksy",
    ]
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
