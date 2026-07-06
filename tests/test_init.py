"""Tests for the md24de package's public surface and lazy attribute access."""

from __future__ import annotations

import pytest

import md24de


class TestModuleGetattr:
    def test_render_consumption_report_pdf_is_lazily_accessible(self) -> None:
        assert callable(md24de.render_consumption_report_pdf)

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        with pytest.raises(AttributeError, match="has no attribute 'does_not_exist'"):
            md24de.does_not_exist  # type: ignore[attr-defined]  # noqa: B018
