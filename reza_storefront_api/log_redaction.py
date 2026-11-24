# -*- coding: utf-8 -*-
"""Keep the storefront token out of Odoo 20's HTTP logs.

With DEBUG on 'odoo.http.server' and 'odoo.http.server.headers', Odoo 20's
native HTTP server logs every raw request header (odoo/http/server_log.py),
in the message text and as the LogRecord attribute `http_headers`. On an h11
protocol error it also logs the exception with exc_info, and h11's message
quotes the offending header line.

Two layers:
1. http_log() is wrapped (in server_log and in server, which imported it by
   name). Before Odoo builds any message or record, the header value is
   replaced, and an exception whose text names the header is logged as its
   type and a redacted message, without the traceback.
2. A logging.Filter on the same loggers redacts a complete header field in
   text, in `http_headers`, and in a formatted exception, for any record that
   still carries one.

Residual risk, stated plainly: this file is imported when the database
registry loads in a worker. A request that a cold worker logs before that is
not covered by either layer. Both layers only matter when DEBUG is enabled on
'odoo.http.server' (and 'odoo.http.server.headers' for parsed headers); Odoo
ships the headers logger at WARNING. Keep both loggers below DEBUG in
production. (Loading this addon server-wide to close the gap is NOT advised:
it would also register its auth='none' controller outside the database.)
18/20: Odoo 18's Werkzeug access log prints the request line only.
"""

import logging
import re
import sys

HEADER = b"x-storefront-token"
REDACTED = b"[redacted]"
LOGGER_NAMES = ("odoo.http.server", "odoo.http.server.headers")
# A header pair as pprint prints it: (b'x-storefront-token', b'<value>'), where
# a long value can be split into several adjacent literals. The whole value,
# every literal of it, is replaced.
_LITERAL = r"""b?(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")"""
_PAIR = re.compile(
    r"""(['"]x-storefront-token['"]\s*,\s*)""" + _LITERAL + r"(?:\s*" + _LITERAL + r")*",
    re.IGNORECASE)
# A complete header field "X-Storefront-Token: value", at the start of a line
# or of a quoted literal (as in h11's "illegal header line: bytearray(b'...')").
_FIELD = re.compile(r"""(?m)(?:^|(?<=['"]))[ \t]*x-storefront-token[ \t]*:[ \t]*""",
                    re.IGNORECASE)


def _field_end(text, start, quote):
    """End of a header value: a line break (real or escaped \\r / \\n) or,
    inside a quoted literal, the unescaped quote that closes it."""
    i = start
    while i < len(text):
        char = text[i]
        if char in "\r\n":
            return i
        if char == "\\" and quote:
            if text[i + 1:i + 2] in ("r", "n"):
                return i
            i += 2
            continue
        if quote and char == quote:
            return i
        i += 1
    return len(text)


def _redact_fields(text):
    out, pos = [], 0
    for match in _FIELD.finditer(text):
        if match.start() < pos:
            continue
        before = text[match.start() - 1] if match.start() else ""
        quote = before if before in "'\"" else ""
        end = _field_end(text, match.end(), quote)
        out.append(text[pos:match.end()])
        out.append("[redacted]")
        pos = end
    out.append(text[pos:])
    return "".join(out)


def redact_text(text):
    if not isinstance(text, str) or "storefront-token" not in text.lower():
        return text
    return _redact_fields(_PAIR.sub(r"\1b'[redacted]'", text))


def redact_headers(headers):
    """A copy of a header list with the token value replaced."""
    out = []
    changed = False
    for item in headers or ():
        try:
            name, value = item
        except (TypeError, ValueError):
            out.append(item)
            continue
        raw = name if isinstance(name, bytes) else str(name).encode("latin-1", "replace")
        if raw.lower() == HEADER:
            value = REDACTED if isinstance(value, bytes) else REDACTED.decode()
            changed = True
        out.append((name, value))
    return out if changed else headers


class RedactStorefrontToken(logging.Filter):

    def filter(self, record):
        for attr in ("msg", "colored_message"):
            value = getattr(record, attr, None)
            if isinstance(value, str):
                setattr(record, attr, redact_text(value))
        headers = getattr(record, "http_headers", None)
        if isinstance(headers, str):
            record.http_headers = redact_text(headers)
        elif headers:
            record.http_headers = redact_headers(headers)
        if record.exc_info and record.exc_info is not True:
            formatted = logging.Formatter().formatException(record.exc_info)
            if "storefront-token" in formatted.lower():
                record.exc_info = None
                record.exc_text = redact_text(formatted)
        if isinstance(record.exc_text, str):
            record.exc_text = redact_text(record.exc_text)
        if isinstance(record.args, tuple):
            record.args = tuple(redact_text(a) if isinstance(a, str) else a for a in record.args)
        return True


def _redact_request(req):
    if req is None or not getattr(req, "headers", None):
        return req
    headers = list(req.headers)
    clean = redact_headers(headers)
    if clean is headers:
        return req
    try:
        import h11
        return h11.Request(method=req.method, target=req.target,
                           http_version=req.http_version, headers=clean)
    except Exception:  # noqa: BLE001 - better no headers than the secret
        return None


def install():
    for name in LOGGER_NAMES:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactStorefrontToken) for f in logger.filters):
            logger.addFilter(RedactStorefrontToken())
    try:
        from odoo.http import server as http_server, server_log
    except ImportError:  # 18/20: no native HTTP server on Odoo 18
        return
    original = server_log.http_log
    if getattr(original, "_reza_storefront_redacting", False):
        return

    def http_log(level, msg, *args, req=None, res=None, **kwargs):
        exc_info = kwargs.get("exc_info")
        if exc_info:
            if exc_info is True:
                exc_info = sys.exc_info()
            elif isinstance(exc_info, BaseException):
                exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
            exc = exc_info[1] if isinstance(exc_info, tuple) else None
            if exc is not None and "storefront-token" in str(exc).lower():
                kwargs["exc_info"] = False
                msg = "%s[%s: %s] " % (msg, type(exc).__name__, redact_text(str(exc)))
        return original(level, msg, *args, req=_redact_request(req), res=res, **kwargs)

    http_log._reza_storefront_redacting = True
    http_log.__wrapped__ = original
    server_log.http_log = http_log
    if getattr(http_server, "http_log", None) is original:
        http_server.http_log = http_log


install()
