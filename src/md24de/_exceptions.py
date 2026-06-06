"""Custom exceptions for the md24de client library."""

from __future__ import annotations


class Md24deError(Exception):
    """Base exception for all errors raised by this library."""


class LoginError(Md24deError):
    """Raised when authentication fails.

    This can be caused by invalid credentials, a network error during login,
    or an unexpected response from the portal.
    """


class ParseError(Md24deError):
    """Raised when the portal response cannot be parsed.

    This typically indicates that the portal's HTML structure has changed
    and the library needs to be updated.
    """
