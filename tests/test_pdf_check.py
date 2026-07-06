"""Tests for the optional-PDF-dependency availability check."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from md24de import PdfNotAvailableError
from md24de._pdf_check import (  # pyright: ignore[reportPrivateUsage]
    _can_import,  # pyright: ignore[reportPrivateUsage]
    _is_reportlab_available,  # pyright: ignore[reportPrivateUsage]
    check_reportlab_available,
)


class TestCanImport:
    def test_returns_true_for_importable_module(self) -> None:
        assert _can_import("sys") is True

    def test_returns_false_for_missing_module(self) -> None:
        assert _can_import("no_such_module_xyz123") is False


class TestIsReportlabAvailable:
    def test_true_when_already_imported(self) -> None:
        with patch.dict(sys.modules, {"reportlab": sys.modules[__name__]}):
            assert _is_reportlab_available() is True

    def test_false_when_not_importable(self) -> None:
        with (
            patch.dict(sys.modules, {}, clear=False),
            patch("md24de._pdf_check._can_import", return_value=False),
        ):
            sys.modules.pop("reportlab", None)
            assert _is_reportlab_available() is False


class TestCheckReportlabAvailable:
    def test_does_not_raise_when_available(self) -> None:
        with patch("md24de._pdf_check._is_reportlab_available", return_value=True):
            check_reportlab_available()

    def test_raises_pdf_not_available_error_when_missing(self) -> None:
        with (
            patch("md24de._pdf_check._is_reportlab_available", return_value=False),
            pytest.raises(PdfNotAvailableError, match=r"pip install python-md24de\[pdf\]"),
        ):
            check_reportlab_available()
