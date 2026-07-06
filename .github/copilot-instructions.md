# python-md24de — Copilot Instructions

## Project overview

Unofficial, typed Python client library for the messdienst24.de utility portal.
Parses heating/hot-water consumption HTML and exposes a clean, minimal public API.

## Language & runtime

- Python 3.12+; use 3.12-compatible syntax
- All files start with `from __future__ import annotations`

## Code style

- Formatter/linter: **ruff** (`line-length = 100`, target `py312`)
- Active ruff rules: `E, F, I, N, W, UP, ANN, S, B, C4, PIE, RET, SIM` — all annotations required (`ANN`)
- Type checker: **pyright strict** — every function must be fully annotated; no `Any` unless unavoidable
- Private module files are prefixed with `_` (e.g. `_client.py`, `_parser.py`)
- Public surface is re-exported from `__init__.py` only; internals stay in `_*.py` modules

## Models

- All data models are `@dataclass(frozen=True)` in `_models.py`
- Enums are plain `Enum` subclasses
- Field docstrings use the `"""…"""` style directly below each field

## Error handling

- All library exceptions inherit from `Md24deError` (defined in `_exceptions.py`)
- Raise `ParseError` for unexpected HTML structure
- Raise `LoginError` when authentication fails
- Raise `PdfNotAvailableError` when PDF rendering is requested but the `[pdf]` optional extra (`reportlab`) is not installed
- Never raise built-in exceptions directly to callers

## HTTP client

- HTTP is done exclusively via **httpx** (`httpx.Client`, synchronous)
- Auth helpers live in `_auth.py` (`login`, `logout`)
- The base URL constant is `_BASE_URL` in `_client.py`

## Parsing

- HTML parsing uses **BeautifulSoup4 + lxml**; JSON-like data uses **json5**
- All parsing logic lives in `_parser.py`

## PDF rendering & notices

- PDF rendering lives in `_pdf.py` and depends on **reportlab**, which is an *optional* `[pdf]` extra — never a hard runtime dependency
- Import `reportlab` (and anything from `_pdf.py`) **lazily**, never at module top level of eagerly-imported modules: `__init__.py` defers `render_consumption_report_pdf` via `__getattr__`, and `Md24deClient.get_pdf()` imports it inside the method
- Before the lazy `_pdf` import, call `check_reportlab_available()` from `_pdf_check.py` so a missing extra raises `PdfNotAvailableError` instead of a raw `ImportError`
- Static, session-independent legal notices live in `_notices.py` (no reportlab dependency); `get_uvi_disclosure_note()` returns the UVI disclosure text and `_pdf.py` uses it rather than duplicating the text
- The UVI disclosure note is a voluntary clarification, **not** a § 6a Abs. 2 HeizkostenV Pflichtangabe (the law mandates only the three data items: consumption, month/year comparison, average comparison)

## Logging

- Every `_*.py` module has `_log = logging.getLogger(__name__)` at module level
- `__init__.py` registers `logging.NullHandler()` on the root `messdienst24` logger
- Use `_log.debug(...)` for operational events (tenant, HTTP status, byte counts, parsed dates)
- **Never log credentials** (username, password) or any URL that contains them
- `_parser.py` defines `_TRACE = 5` for raw HTML/JS dumps before `ParseError` — use `_log.log(_TRACE, ...)`
- **Never call `logging.addLevelName()`** — that mutates global process state, which is inappropriate for a library; callers can register the name themselves if needed

## Testing

- Framework: **pytest** with `pytest-cov` and `pytest-mock`
- Tests live in `tests/`; HTML fixtures in `tests/fixtures/`
- Run tests: `pytest`
- Run type check: `pyright src/`
- Run linter: `ruff check src/ tests/`

## Build

- Build system: **hatchling**; install dev dependencies with `pip install -e ".[dev]"`
