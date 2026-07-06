"""Helper to check for optional PDF dependencies."""

from __future__ import annotations

import sys


def check_reportlab_available() -> None:
    """Raise PdfNotAvailableError if reportlab is not installed.

    Call this at the start of any function that needs reportlab.
    """
    if not _is_reportlab_available():
        from md24de._exceptions import PdfNotAvailableError

        raise PdfNotAvailableError(
            "PDF rendering requires the 'pdf' extra. "
            "Install it with: pip install python-md24de[pdf]"
        )


def _is_reportlab_available() -> bool:
    """Check if reportlab is available without importing it."""
    return "reportlab" in sys.modules or _can_import("reportlab")


def _can_import(module_name: str) -> bool:
    """Check if a module can be imported without actually importing it."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False
