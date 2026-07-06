# python-md24de

[![Latest release](https://img.shields.io/github/v/release/volsch/python-md24de?label=latest)](https://github.com/volsch/python-md24de/releases/latest)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=volsch_python-md24de&metric=alert_status)](https://sonarcloud.io/summary/overall?id=volsch_python-md24de)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=volsch_python-md24de&metric=coverage)](https://sonarcloud.io/summary/overall?id=volsch_python-md24de)

Unofficial Python client library for the [messdienst24.de](https://messdienst24.de) utility-consumption portal.
Provides typed, programmatic access to heating and hot-water consumption data and PDF document generation.

> **Disclaimer** — This project is not affiliated with, endorsed by, or in any way officially
> connected with messdienst24.de or its operators. It was built by observing the portal's
> web interface for personal and educational use. Use at your own risk.

---

## Features

- Log in and log out of the portal securely
- Retrieve the currently available consumption month
- Parse structured heating and hot-water consumption data (current usage, household averages,
  month-over-month and year-over-year comparisons, historical readings)
- Render a monthly UVI PDF document — the current portal no longer offers a PDF download, so
  this library generates one locally from the parsed report
- Serialize/deserialize a parsed report to/from compact JSON, and render your own simplified
  UVI PDF from it — both work offline, with no portal access required
- Fully typed — passes **pyright strict** with zero errors
- Minimal dependencies: `httpx`, `beautifulsoup4`, `lxml`, `json5` (PDF rendering is an optional extra)
- Python 3.12+

## Installation

This library is not published on PyPI. Install directly from a GitHub release.

**Check the latest version** in the badge above, then install it (replace `vX.Y.Z` accordingly):

```bash
pip install "git+https://github.com/volsch/python-md24de.git@vX.Y.Z"
```

To include PDF rendering support (requires `reportlab`):

```bash
pip install "git+https://github.com/volsch/python-md24de.git@vX.Y.Z#egg=python-md24de[pdf]"
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add "git+https://github.com/volsch/python-md24de.git@vX.Y.Z"
```

To include PDF rendering support:

```bash
uv add "git+https://github.com/volsch/python-md24de.git@vX.Y.Z[pdf]"
```

Alternatively, download the pre-built wheel directly from the
[Releases page](https://github.com/volsch/python-md24de/releases/latest) and install it:

```bash
pip install python_md24de-X.Y.Z-py3-none-any.whl
```

## Quick start

```python
from pathlib import Path
from md24de import Md24deClient, Comparison

with Md24deClient(tenant="xy", username="your_user", password="your_pass") as client:
    # Which month is currently available?
    month = client.get_last_available_month()
    print(f"Data available for: {month.month:02d}/{month.year}")

    # Full consumption report (lazy-parsed, cached after first call)
    report = client.get_consumption_report()
    print(f"Heating:   {report.heating.current_kwh} kWh eq")
    print(f"Hot water: {report.hot_water.current_kwh} kWh eq")

    if report.heating.vs_average is Comparison.LESS:
        print("You used less heating energy than comparable households.")

    # Render the monthly PDF locally (the portal itself provides no PDF download)
    pdf_bytes = client.get_pdf()
    Path("consumption.pdf").write_bytes(pdf_bytes)
```

The `tenant` is the short identifier in your portal URL — e.g. `xy` if your portal login page
is `https://messdienst24.de/?md=xy`.

> **Note — Data availability** — The portal always serves the previous month's data, never
> the current month. For example, in June you will receive either April's or May's data,
> depending on when the portal publishes it. If no data has been published yet at all, the
> relevant page section may not be present and constructing `Md24deClient` itself will raise
> a `ParseError`. Use `get_last_available_month()` to check which month the portal is
> currently serving.

## API reference

### `Md24deClient`

```python
Md24deClient(
    *,
    tenant: str,
    username: str,
    password: str,
    options: ClientOptions | None = None,
)

ClientOptions(
    timeout: float = 30.0,
    http_trace_callback: HttpTraceCallback | None = None,
)
```

Logs in on construction. Use as a context manager (`with`) to ensure the session is always
closed, or call `.close()` manually.

> **Warning — Session lifetime** — The portal may terminate the session after a fixed period
> regardless of recent activity (server-side absolute timeout).  Any method call after the
> session has expired will raise `Md24deError` or return an unexpected response.  For
> long-running processes, create a new `Md24deClient` instance for each retrieval.

**Raises** `LoginError` if authentication fails.

#### Methods

| Method | Returns | Description |
|---|---|---|
| `get_last_available_month()` | `AvailableMonth` | The month/year currently provided by the portal |
| `get_consumption_report()` | `ConsumptionReport` | Full consumption data; lazy-parsed and cached |
| `get_pdf()` | `bytes` | Raw PDF bytes for the available month, rendered locally (no portal download); requires the `[pdf]` extra |
| `close()` | `None` | Log out and close the HTTP connection |

### HTTP request/response tracing

Pass `http_trace_callback` via `ClientOptions` to observe every HTTP request/response pair made
by the client (e.g. for audit logging or troubleshooting). The callback is called exactly once per request,
whether it succeeded or failed, and is **never called for the login/logout requests** — so
credentials are never exposed through it. It only ever receives plain, library-owned data
(`HttpRequestTrace` / `HttpResponseTrace`), never an `httpx` object. Since `get_pdf()` renders
the PDF locally (no HTTP request), the only traced request is the one made internally to fetch
the consumption page.

```python
from md24de import Md24deClient, ClientOptions, HttpRequestTrace, HttpResponseTrace

def my_trace_callback(request: HttpRequestTrace, response: HttpResponseTrace | None) -> None:
    print(request.method, request.url, "->", response.status_code if response else "no response")

with Md24deClient(
    tenant="xy",
    username="your_user",
    ******
    options=ClientOptions(http_trace_callback=my_trace_callback),
) as client:
    ...
```

| Type | Description |
|---|---|
| `HttpTraceCallback` | `Callable[[HttpRequestTrace, HttpResponseTrace \| None], None]` |
| `HttpRequestTrace` | `method`, `url` (incl. query string), `headers` (multi-valued, unmasked), `body` (`str \| None`, only if textual) |
| `HttpResponseTrace` | `status_code`, `headers` (multi-valued, unmasked), `body` (`str \| None`, only if textual), `tls_version` (`str \| None`, e.g. `"TLSv1.3"`) |

A ready-to-use default implementation, `FileHttpTraceLogger`, appends a timestamped,
numbered, human-readable trace of every request/response to a file. `Cookie`/`Set-Cookie`
header values are always masked in this rendered text:

```python
from md24de import Md24deClient, ClientOptions, FileHttpTraceLogger

with Md24deClient(
    tenant="xy",
    username="your_user",
    ******
    options=ClientOptions(http_trace_callback=FileHttpTraceLogger("md24de-http-trace.log")),
) as client:
    ...
```

Produces entries like:

```
=== 1 === 2026-07-05T20:20:22.797846+00:00 ===
> GET https://messdienst24.de/uvi
> Host: messdienst24.de
> Cookie: ***
>

< 200 [TLSv1.3]
< Content-Type: text/html; charset=UTF-8
< Set-Cookie: ***
<
<html>...</html>
```

Use `format_http_trace(request, response, sequence=...)` directly if you want the same
formatted text routed to a different sink (e.g. a logger or a cloud log stream, which is
preferable to writing to a temp file in ephemeral environments like AWS Lambda).

### Models

#### `AvailableMonth`

| Field | Type | Description |
|---|---|---|
| `year` | `int` | Four-digit year |
| `month` | `int` | Month number (1–12) |

#### `ConsumptionReport`

The report does not carry a top-level `year` or `month` field.  The covered period is
available per-reading in `MeterReport.history` (`history[0]` is the last available month at
the time the report was fetched).  Use `get_last_available_month()` to get the month without
parsing the full report — note that it reflects the state at login time.

| Field | Type | Description |
|---|---|---|
| `object_info` | `ObjectInfo` | Address and object number |
| `heating` | `MeterReport` | Heating consumption data |
| `hot_water` | `MeterReport` | Hot-water consumption data |

#### `ObjectInfo`

| Field | Type | Description |
|---|---|---|
| `object_number` | `str` | Property identifier assigned by the service provider |
| `address` | `str` | Street address of the metered property |

#### `MeterReport`

| Field | Type | Description |
|---|---|---|
| `current_kwh` | `float \| None` | Your consumption this month in kWh eq (`None` if the portal did not supply a value — distinct from an actual 0 kWh reading) |
| `average_kwh` | `float \| None` | Average of comparable households in kWh eq (`None` if the portal did not supply a value) |
| `vs_average` | `Comparison \| None` | Compared to comparable households (`None` if unavailable) |
| `vs_previous_month` | `Comparison \| None` | Compared to last month (`None` if unavailable) |
| `vs_previous_year` | `Comparison \| None` | Compared to same month last year (`None` if unavailable) |
| `history` | `tuple[MeterReading, ...]` | Historical bar-chart readings, newest first |

#### `MeterReading`

| Field | Type | Description |
|---|---|---|
| `year` | `int` | Four-digit year |
| `month` | `int` | Month number (1–12) |
| `your_kwh` | `float \| None` | Your consumption for that month in kWh eq (`None` if the portal did not supply a value) |
| `average_kwh` | `float \| None` | Average of comparable households for that month in kWh eq (`None` if the portal did not supply a value) |

#### `Comparison`

```python
class Comparison(Enum):
    LESS  = "less"
    MORE  = "more"
    EQUAL = "equal"
```

### Session-independent helpers

These functions operate on an already-parsed `ConsumptionReport` and require no portal
access — useful for archiving data or re-generating output from stored reports.

| Function | Returns | Description |
|---|---|---|
| `dump_consumption_report(report)` | `str` | Compact JSON serialization; fields with `None` are omitted |
| `load_consumption_report(data)` | `ConsumptionReport` | Parses JSON produced by `dump_consumption_report()` |
| `render_consumption_report_pdf(report)` | `bytes` | Renders a simplified UVI PDF (no address/object number); requires the `[pdf]` extra |
| `get_uvi_disclosure_note()` | `str` | Returns the informational UVI disclosure note embedded in the PDF; no `[pdf]` extra required |

```python
from md24de import (
    dump_consumption_report,
    load_consumption_report,
    render_consumption_report_pdf,
    get_uvi_disclosure_note,
)

json_text = dump_consumption_report(report)
same_report = load_consumption_report(json_text)
uvi_pdf_bytes = render_consumption_report_pdf(report)
note_text = get_uvi_disclosure_note()
```

`render_consumption_report_pdf()` produces a one-page PDF containing only the period
(`UVI <Month> <Year>`), the values required by § 6a Absatz 2 HeizkostenV (your consumption, the
comparable-household average, and the vs.-average/vs.-previous-month/vs.-previous-year
comparisons), and an informational disclosure notice. It deliberately omits the address and
object number present in the portal's own PDF (see `get_pdf()`). It covers only the monthly
disclosure items of Absatz 2 — annual-billing items required by Absatz 3 (e.g. contact info,
dispute-resolution info, the weather-adjusted year-over-year graphic) are out of scope, since
they belong to a different document (the annual `Abrechnung`, not the monthly UVI).

`GERMAN_MONTH_NAMES` is a public constant mapping month numbers (1-12) to their German
names (e.g. `{5: "Mai"}`), for callers that need to render a German month name (e.g. in
custom reports or emails) without duplicating the mapping.

`get_uvi_disclosure_note()` returns the same static, informational disclosure text embedded by
`render_consumption_report_pdf()` — it is session-independent and does not require the
`[pdf]` extra, so it can be used on its own (e.g. to show the note in a UI or another
document) without rendering a full PDF. `render_consumption_report_pdf()` calls this
function internally rather than duplicating the text. The note is a voluntary clarification of
the UVI's non-binding character; it is not one of the § 6a Absatz 2 HeizkostenV Pflichtangaben
(which mandate only the three data items above).

### Exceptions

| Exception | Raised when |
|---|---|
| `Md24deError` | Base class for all library errors |
| `LoginError` | Authentication fails |
| `ParseError` | Page HTML cannot be parsed as expected — may indicate the portal's structure has changed |
| `PdfNotAvailableError` | `render_consumption_report_pdf()` is called but the `[pdf]` extra is not installed |

## Development

```bash
git clone https://github.com/volsch/python-md24de.git
cd python-md24de
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest
```

Type-check:

```bash
pyright src/
```

Lint and format:

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Logging

The library uses Python's standard `logging` module under the `md24de` logger hierarchy
and registers a `NullHandler` so no output appears unless the calling application configures
logging explicitly.

To enable debug output during development:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Debug messages include tenant identifiers, HTTP status codes, response sizes, and parsed
month/year values. **Credentials (username, password) are never written to any log message.**

For even more verbose output — including raw HTML/JS snippets (capped at 256 KB) that are
emitted right before a `ParseError` — enable level `5`:

```python
import logging
logging.addLevelName(5, "TRACE")          # optional: give it a readable name
logging.basicConfig(level=5)
```

> The library does **not** call `logging.addLevelName()` itself — that would be a global
> side effect inappropriate for a library. If you omit the call above, level 5 messages
> appear as `"Level 5"` in your log output.

## Legal

### Legal context for the data

The monthly consumption report accessed through this library is the *unterjährige
Verbrauchsinformation* (UVI) — a legally mandated document under §6a of the German
Heating Cost Ordinance (*Heizkostenverordnung*, HeizkostenV). Under §6b HeizkostenV,
consumption data may only be collected and used for billing purposes and to fulfil the
legal information obligations. This library retrieves your own data from the portal
provided for exactly that purpose.

### Unofficial project

This library is **not** an official product of messdienst24.de. It was built by observing the
portal's web interface for personal and educational use. The library does not circumvent any
technical protection measures and only uses credentials that the account holder provides
themselves.

### Credentials and privacy

Your username and password are sent directly to the messdienst24.de servers over HTTPS. This
library does not store or log them. However, any direct or indirect dependency of this library
— such as HTTP client internals, logging back-ends, or network proxies configured in your
environment — is outside this library's control and may handle the data differently.

Consumption data fetched from the portal is not persisted by this library — it is held in
memory only for the lifetime of the `Md24deClient` object.

### No warranty

The portal's HTML structure can change at any time without notice, which may break this library.
A `ParseError` is often a sign that the portal's page layout has changed. The software is
provided "as is" — see the [LICENSE](LICENSE) for full terms.

### Terms of service

Before using this library, ensure your use complies with the messdienst24.de terms of service.
Automated access may be restricted by those terms.

## License

[MIT](LICENSE) © 2026 Volker Schmidt
