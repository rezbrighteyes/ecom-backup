# -*- coding: utf-8 -*-
"""The Odoo test harness replaces `requests.Session.send` for every test class
(odoo/tests/common.py, `_request_handler`), so these tests drive `wrap_send`
directly with a fake transport instead of going through `requests`.
"""
from unittest.mock import patch

import requests

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.reza_starshipit_rate_limit import starshipit_throttle as st

SHIPMENT_URL = "https://api.starshipit.com/api/orders/shipment"
BODY_429 = '{ "statusCode": 429, "message": "Rate limit is exceeded. Try again in 1 seconds." }'


def _response(status, text="", headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = text.encode()
    response.headers.update(headers or {})
    return response


def _request(url=SHIPMENT_URL, method="POST"):
    return requests.Request(method, url, json={"order_id": 1}).prepare()


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, session, request, **kwargs):
        self.calls.append((request, kwargs))
        return self.responses.pop(0)


@tagged("post_install", "-at_install")
class TestStarshipitThrottle(TransactionCase):

    def setUp(self):
        super().setUp()
        self.sleeps = []
        self.clock = [1000.0]
        patcher_sleep = patch.object(st, "_sleep", self._fake_sleep)
        patcher_clock = patch.object(st, "_monotonic", lambda: self.clock[0])
        patcher_slot = patch.object(st, "_next_slot", 0.0)
        for p in (patcher_sleep, patcher_clock, patcher_slot):
            p.start()
            self.addCleanup(p.stop)

    def _fake_sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock[0] += seconds

    def test_429_then_200_retries_same_request(self):
        fake = FakeTransport(_response(429, BODY_429), _response(200, "{}"))
        request = _request()
        response = st.wrap_send(fake)(requests.Session(), request, timeout=30)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(fake.calls), 2)
        self.assertIs(fake.calls[1][0], request, "the retry must resend the same request")
        self.assertEqual(fake.calls[1][1], {"timeout": 30}, "kwargs must pass through")
        self.assertIn(1.0 + st.WAIT_MARGIN, self.sleeps)

    def test_other_hosts_are_never_retried_or_paced(self):
        fake = FakeTransport(_response(429, BODY_429))
        response = st.wrap_send(fake)(requests.Session(), _request("https://api.example.com/x"))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(self.sleeps, [])

    def test_lookalike_host_is_not_starshipit(self):
        self.assertFalse(st.is_starshipit("https://api.starshipit.com.evil.test/api"))
        self.assertFalse(st.is_starshipit("https://evil.test/?u=api.starshipit.com"))
        self.assertTrue(st.is_starshipit("https://api.starshipit.com/api/orders"))

    def test_gives_up_after_max_retries_and_returns_the_429(self):
        fake = FakeTransport(*[_response(429, BODY_429) for _ in range(st.MAX_RETRIES + 1)])
        response = st.wrap_send(fake)(requests.Session(), _request())
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(fake.calls), st.MAX_RETRIES + 1)

    def test_success_and_errors_other_than_429_are_not_retried(self):
        for status in (200, 400, 500):
            fake = FakeTransport(_response(status, "{}"))
            response = st.wrap_send(fake)(requests.Session(), _request())
            self.assertEqual(response.status_code, status)
            self.assertEqual(len(fake.calls), 1, status)

    def test_wait_comes_from_retry_after_then_body_then_default(self):
        self.assertEqual(st.retry_wait(_response(429, BODY_429, {"Retry-After": "3"})),
                         3 + st.WAIT_MARGIN)
        self.assertEqual(st.retry_wait(_response(429, "Try again in 2 seconds.")),
                         2 + st.WAIT_MARGIN)
        self.assertEqual(st.retry_wait(_response(429, "nope")),
                         st.DEFAULT_WAIT + st.WAIT_MARGIN)
        self.assertEqual(st.retry_wait(_response(429, "Try again in 600 seconds")),
                         st.MAX_WAIT)

    def test_back_to_back_calls_are_spaced_min_interval_apart(self):
        fake = FakeTransport(*[_response(200, "{}") for _ in range(3)])
        send = st.wrap_send(fake)
        for _ in range(3):
            send(requests.Session(), _request())
        self.assertEqual(self.sleeps, [st.MIN_INTERVAL, st.MIN_INTERVAL])

    def test_install_is_idempotent(self):
        with patch.object(requests.Session, "send", requests.Session.send):
            st.install()
            once = requests.Session.send
            st.install()
            self.assertIs(requests.Session.send, once)
            self.assertTrue(once._reza_starshipit_wrapped)
