"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def consumption_html() -> str:
    """Raw HTML from the portal's consumption endpoint (anonymized/synthetic sample data)."""
    return (FIXTURES_DIR / "consumption.html").read_text(encoding="utf-8")
