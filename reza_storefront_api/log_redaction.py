# -*- coding: utf-8 -*-
"""Keep the storefront credentials out of Odoo 20's HTTP logs.

Credentials: the X-Storefront-Token header, the Cloudflare Access headers
Cf-Access-Jwt-Assertion, cf-access-token and CF-Access-Client-Secret, and the
CF_Authorization cookie inside the Cookie header.

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

HEADERS = (b"x-storefront-token", b"cf-access-jwt-assertion", b"cf-access-token",
           b"cf-access-client-secret")
COOKIE = b"cookie"
REDACTED = b"[redacted]"
LOGGER_NAMES = ("odoo.http.server", "odoo.http.server.headers")
_NAMES = "|".join(re.escape(h.decode()) for h in HEADERS)
# Lower-case marks of a credential in any text: when none is present the text
# is left alone.
_MARKS = tuple(h.decode() for h in HEADERS) + ("cf_authorization",)
# A header pair as pprint prints it: (b'x-storefront-token', b'<value>'), where
# a long value can be split into several adjacent literals. The whole value,
# every literal of it, is replaced.
_LITERAL = r"""b?(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")"""
_PAIR = re.compile(
    r"""(['"](?:""" + _NAMES + r""")['"]\s*,\s*)""" + _LITERAL + r"(?:\s*" + _LITERAL + r")*",
    re.IGNORECASE)
# A complete header field "X-Storefront-Token: value", at the start of a line
# or of a quoted literal (as in h11's "illegal header line: bytearray(b'...')").
_FIELD = re.compile(r"""(?m)(?:^|(?<=['"]))[ \t]*(?:""" + _NAMES + r""")[ \t]*:[ \t]*""",
                    re.IGNORECASE)
# The Access cookie inside a Cookie header, in any form.
# A quoted cookie value ("...") is taken whole, quotes included.
_COOKIE = re.compile(r"""(CF_Authorization\s*=\s*)(?:"[^"]*"?|[^;\s'"\\]*)""", re.IGNORECASE)


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


def mentions_credential(text):
    lower = text.lower()
    return any(mark in lower for mark in _MARKS)


def redact_text(text):
    if not isinstance(text, str) or not mentions_credential(text):
        return text
    text = _COOKIE.sub(r"\1[redacted]", text)
    return _redact_fields(_PAIR.sub(r"\1b'[redacted]'", text))


def _safe_exception_text(exc_type):
    """A fixed reason for an exception whose text names a credential: its
    type only, never its (possibly malformed, unrecognised) text."""
    name = getattr(exc_type, "__name__", "Exception")
    return "%s: [text withheld: it names a credential header]" % name


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
        if raw.strip().lower() in HEADERS:
            value = REDACTED if isinstance(value, bytes) else REDACTED.decode()
            changed = True
        elif raw.strip().lower() == COOKIE:
            # The whole Cookie field is withheld when it carries the Access
            # cookie, whatever its syntax (quoted, odd spacing, repeated).
            text = value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else str(value)
            if "cf_authorization" in text.lower():
                value = REDACTED if isinstance(value, (bytes, bytearray)) else REDACTED.decode()
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
            if mentions_credential(formatted):
                exc_type = record.exc_info[0]
                record.exc_info = None
                record.exc_text = _safe_exception_text(exc_type)
        if isinstance(record.exc_text, str):
            record.exc_text = redact_text(record.exc_text)
        if isinstance(record.args, tuple):
            record.args = tuple(redact_text(a) if isinstance(a, str) else a for a in record.args)
        return True


def _is_protocol_error(exc):
    try:
        import h11
    except ImportError:  # pragma: no cover - h11 ships with Odoo 20
        return False
    return isinstance(exc, h11.ProtocolError)


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
            # A protocol error quotes raw request bytes, possibly a header in
            # a shape no pattern here knows: its text is never logged.
            if exc is not None and (_is_protocol_error(exc) or mentions_credential(str(exc))):
                kwargs["exc_info"] = False
                msg = "%s[%s] " % (msg, _safe_exception_text(type(exc)))
        return original(level, msg, *args, req=_redact_request(req), res=res, **kwargs)

    http_log._reza_storefront_redacting = True
    http_log.__wrapped__ = original
    server_log.http_log = http_log
    if getattr(http_server, "http_log", None) is original:
        http_server.http_log = http_log


install()
