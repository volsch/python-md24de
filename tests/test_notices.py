"""Tests for the session-independent legal-notice helper."""

from __future__ import annotations

from md24de import get_uvi_disclosure_note
from md24de._notices import UVI_DISCLOSURE_NOTE


class TestGetUviDisclosureNote:
    def test_returns_the_disclosure_text(self) -> None:
        assert get_uvi_disclosure_note() == UVI_DISCLOSURE_NOTE

    def test_mentions_the_uvi_and_its_non_binding_character(self) -> None:
        note = get_uvi_disclosure_note()
        assert "Diese Informationen dienen lediglich Ihrer Orientierung." in note
        assert "ersetzt keine Abrechnung" in note
        assert "UVI" in note

    def test_is_stable_across_calls(self) -> None:
        """The note is static/session-independent — every call returns the same text."""
        assert get_uvi_disclosure_note() == get_uvi_disclosure_note()
