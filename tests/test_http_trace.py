"""Tests for the HTTP request/response tracing support."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx

from md24de._http_trace import (
    FileHttpTraceLogger,
    build_request_trace,
    build_response_trace,
    format_http_trace,
)
from md24de._models import HttpRequestTrace, HttpResponseTrace


class TestBuildRequestTrace:
    def test_basic_fields(self) -> None:
        request = httpx.Request(
            "GET",
            "https://example.com/path",
            params={"a": "1", "b": "2"},
            headers={"X-Test": "value"},
        )
        trace = build_request_trace(request)
        assert trace.method == "GET"
        assert trace.url == "https://example.com/path?a=1&b=2"
        assert ("x-test", "value") in trace.headers
        assert trace.body is None

    def test_cookie_header_not_masked_in_trace_object(self) -> None:
        """Masking happens only in format_http_trace, not in the trace object itself."""
        request = httpx.Request(
            "GET", "https://example.com/", headers={"Cookie": "SESID=secret"}
        )
        trace = build_request_trace(request)
        assert ("cookie", "SESID=secret") in trace.headers

    def test_textual_body_decoded(self) -> None:
        request = httpx.Request(
            "POST",
            "https://example.com/",
            data={"action": "objverbmiet"},
        )
        trace = build_request_trace(request)
        assert trace.body == "action=objverbmiet"

    def test_binary_body_omitted(self) -> None:
        request = httpx.Request(
            "POST",
            "https://example.com/",
            content=b"\x00\x01binary",
            headers={"Content-Type": "application/octet-stream"},
        )
        trace = build_request_trace(request)
        assert trace.body is None

    def test_multi_valued_headers_preserved(self) -> None:
        request = httpx.Request(
            "GET",
            "https://example.com/",
            headers=[("X-Multi", "1"), ("X-Multi", "2")],
        )
        trace = build_request_trace(request)
        values = [v for n, v in trace.headers if n == "x-multi"]
        assert values == ["1", "2"]

    def test_undecodable_textual_body_omitted(self) -> None:
        """Invalid UTF-8 bytes with a textual content-type must not raise."""
        request = httpx.Request(
            "POST",
            "https://example.com/",
            content=b"\xff\xfe not valid utf-8",
            headers={"Content-Type": "text/plain"},
        )
        trace = build_request_trace(request)
        assert trace.body is None


class TestBuildResponseTrace:
    def test_basic_fields(self) -> None:
        response = httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            request=httpx.Request("GET", "https://example.com/"),
        )
        trace = build_response_trace(response, b"<html>hi</html>")
        assert trace.status_code == 200
        assert trace.body == "<html>hi</html>"

    def test_set_cookie_not_masked_in_trace_object(self) -> None:
        response = httpx.Response(
            200,
            headers=[("Set-Cookie", "SESID=secret; Path=/")],
            request=httpx.Request("GET", "https://example.com/"),
        )
        trace = build_response_trace(response, b"")
        assert ("set-cookie", "SESID=secret; Path=/") in trace.headers

    def test_binary_body_omitted(self) -> None:
        response = httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            request=httpx.Request("GET", "https://example.com/"),
        )
        trace = build_response_trace(response, b"%PDF-1.4 fake")
        assert trace.body is None

    def test_no_body_read_yields_none(self) -> None:
        response = httpx.Response(200, request=httpx.Request("GET", "https://example.com/"))
        trace = build_response_trace(response, None)
        assert trace.body is None

    def test_multi_valued_set_cookie_preserved(self) -> None:
        response = httpx.Response(
            200,
            headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")],
            request=httpx.Request("GET", "https://example.com/"),
        )
        trace = build_response_trace(response, b"")
        values = [v for n, v in trace.headers if n == "set-cookie"]
        assert values == ["a=1", "b=2"]

    def test_tls_version_absent_for_plain_transport(self) -> None:
        response = httpx.Response(200, request=httpx.Request("GET", "https://example.com/"))
        trace = build_response_trace(response, b"")
        assert trace.tls_version is None

    def test_tls_version_absent_when_ssl_object_missing(self) -> None:
        """network_stream present but get_extra_info('ssl_object') returns None."""
        network_stream = MagicMock()
        network_stream.get_extra_info.return_value = None
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com/"),
            extensions={"network_stream": network_stream},
        )
        trace = build_response_trace(response, b"")
        assert trace.tls_version is None

    def test_tls_version_extracted_from_ssl_object(self) -> None:
        ssl_object = MagicMock()
        ssl_object.version.return_value = "TLSv1.3"
        network_stream = MagicMock()
        network_stream.get_extra_info.return_value = ssl_object
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com/"),
            extensions={"network_stream": network_stream},
        )
        trace = build_response_trace(response, b"")
        assert trace.tls_version == "TLSv1.3"


class TestFormatHttpTrace:
    def test_masks_cookie_and_set_cookie(self) -> None:
        req = HttpRequestTrace(
            method="GET",
            url="https://example.com/",
            headers=(("cookie", "SESID=secret"),),
            body=None,
        )
        resp = HttpResponseTrace(
            status_code=200,
            headers=(("set-cookie", "SESID=secret; Path=/"),),
            body=None,
            tls_version="TLSv1.3",
        )
        text = format_http_trace(req, resp)
        assert "SESID=secret" not in text
        assert "***" in text

    def test_includes_timestamp_method_url_status(self) -> None:
        req = HttpRequestTrace(method="GET", url="https://example.com/x", headers=(), body=None)
        resp = HttpResponseTrace(status_code=204, headers=(), body=None, tls_version=None)
        text = format_http_trace(req, resp)
        assert "GET https://example.com/x" in text
        assert "204" in text

    def test_no_response_noted(self) -> None:
        req = HttpRequestTrace(method="GET", url="https://example.com/", headers=(), body=None)
        text = format_http_trace(req, None)
        assert "no response" in text

    def test_tls_version_included(self) -> None:
        req = HttpRequestTrace(method="GET", url="https://example.com/", headers=(), body=None)
        resp = HttpResponseTrace(status_code=200, headers=(), body=None, tls_version="TLSv1.3")
        text = format_http_trace(req, resp)
        assert "TLSv1.3" in text

    def test_includes_request_body(self) -> None:
        req = HttpRequestTrace(
            method="POST", url="https://example.com/", headers=(), body="action=login"
        )
        resp = HttpResponseTrace(status_code=200, headers=(), body=None, tls_version=None)
        text = format_http_trace(req, resp)
        assert "action=login" in text

    def test_includes_response_body(self) -> None:
        req = HttpRequestTrace(method="GET", url="https://example.com/", headers=(), body=None)
        resp = HttpResponseTrace(
            status_code=200, headers=(), body="<html>hi</html>", tls_version=None
        )
        text = format_http_trace(req, resp)
        assert "<html>hi</html>" in text


class TestFileHttpTraceLogger:
    def test_appends_trace_to_file(self, tmp_path: Path) -> None:
        path = tmp_path / "trace.log"
        logger = FileHttpTraceLogger(path)
        req = HttpRequestTrace(
            method="GET",
            url="https://example.com/",
            headers=(("cookie", "SESID=secret"),),
            body=None,
        )
        resp = HttpResponseTrace(status_code=200, headers=(), body=None, tls_version=None)
        logger(req, resp)
        logger(req, resp)
        content = path.read_text(encoding="utf-8")
        assert content.count("GET https://example.com/") == 2
        assert "SESID=secret" not in content

    def test_write_failure_is_logged_not_raised(self, tmp_path: Path) -> None:
        """An OSError while writing must be swallowed (logged), never propagated."""
        path = tmp_path / "unwritable" / "trace.log"  # parent dir doesn't exist -> OSError
        logger = FileHttpTraceLogger(path)
        req = HttpRequestTrace(method="GET", url="https://example.com/", headers=(), body=None)
        resp = HttpResponseTrace(status_code=200, headers=(), body=None, tls_version=None)
        logger(req, resp)  # must not raise
