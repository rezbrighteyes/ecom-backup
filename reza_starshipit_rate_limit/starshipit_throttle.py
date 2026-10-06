# -*- coding: utf-8 -*-
"""Pace and retry outbound calls to the Starshipit API.

See the manifest description for why this lives at the `requests` layer.
"""
import logging
import re
import threading
import time
from urllib.parse import urlsplit

import requests

_logger = logging.getLogger(__name__)

STARSHIPIT_HOSTS = {"api.starshipit.com"}

# Minimum gap between two Starshipit calls from one worker process. Starshipit
# was seen refusing the third call inside one second, so two per second.
MIN_INTERVAL = 0.5
# Retries after the first refused attempt.
MAX_RETRIES = 5
# Fallback wait when the response names none, and the ceiling on any one wait.
DEFAULT_WAIT = 1.0
MAX_WAIT = 10.0
# Added to the named wait, so the retry lands after the window, not on its edge.
WAIT_MARGIN = 0.25

_TRY_AGAIN_RE = re.compile(r"try again in\s+(\d+(?:\.\d+)?)\s*second", re.IGNORECASE)

_lock = threading.Lock()
_next_slot = 0.0

# Indirection so tests can stub the clock without sleeping.
_sleep = time.sleep
_monotonic = time.monotonic


def is_starshipit(url):
    try:
        host = urlsplit(url or "").hostname
    except ValueError:
        return False
    return host in STARSHIPIT_HOSTS


def retry_wait(response):
    """Seconds to wait before retrying a 429, from the response itself."""
    wait = None
    header = response.headers.get("Retry-After")
    if header:
        try:
            wait = float(header)
        except ValueError:
            wait = None
    if wait is None:
        match = _TRY_AGAIN_RE.search(response.text or "")
        if match:
            wait = float(match.group(1))
    if wait is None or wait < 0:
        wait = DEFAULT_WAIT
    return min(wait + WAIT_MARGIN, MAX_WAIT)


def throttle():
    """Hold the caller until its slot comes up, MIN_INTERVAL after the last one."""
    global _next_slot
    with _lock:
        now = _monotonic()
        slot = max(now, _next_slot)
        _next_slot = slot + MIN_INTERVAL
    delay = slot - now
    if delay > 0:
        _sleep(delay)


def wrap_send(send):
    """Return a `Session.send` replacement that paces and retries Starshipit calls."""

    def starshipit_send(session, request, **kwargs):
        if not is_starshipit(request.url):
            return send(session, request, **kwargs)
        attempt = 0
        while True:
            throttle()
            response = send(session, request, **kwargs)
            if response.status_code != 429 or attempt >= MAX_RETRIES:
                if response.status_code == 429:
                    _logger.warning(
                        "Starshipit still rate limited after %s retries: %s %s",
                        attempt, request.method, request.url)
                return response
            attempt += 1
            wait = retry_wait(response)
            _logger.info(
                "Starshipit 429 on %s %s, retry %s/%s in %.2fs",
                request.method, request.url, attempt, MAX_RETRIES, wait)
            response.close()
            _sleep(wait)

    starshipit_send._reza_starshipit_wrapped = send
    return starshipit_send


def install():
    current = requests.Session.send
    if getattr(current, "_reza_starshipit_wrapped", None):
        return
    requests.Session.send = wrap_send(current)
    _logger.info("Starshipit rate-limit retry installed on requests.Session.send")
