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
- Never raise built-in exceptions directly to callers

## HTTP client

- HTTP is done exclusively via **httpx** (`httpx.Client`, synchronous)
- Auth helpers live in `_auth.py` (`login`, `logout`)
- The base URL constant is `_BASE_URL` in `_client.py`

## Parsing

- HTML parsing uses **BeautifulSoup4 + lxml**; JSON-like data uses **json5**
- All parsing logic lives in `_parser.py`

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
