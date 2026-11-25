# -*- coding: utf-8 -*-
"""The second lock (access.py): a Cloudflare Access JWT, verified offline
against a fake JWKS. The HTTP boundary is in test_http.py."""

import json
import threading
import time
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from .. import access
from .jwt_tools import (
    AUD, TEAM, SigningKey, b64, claims, encode, hs256_with_public_key, jwks, service_claims,
)

NOW = 1_900_000_000
SITE = 7001                       # a website id; access.py never reads the website
REAL_FETCH = access._fetch_jwks   # setUp replaces it with a fake


class FakeResponse:
    """A urllib3 response: status and headers first, body read in chunks."""

    def __init__(self, test, status=200, headers=None, chunks=(), tick=0.0):
        self.test = test
        self.status = status
        self.headers = headers or {}
        self.chunks = list(chunks)
        self.tick = tick
        self.reads = 0
        self.asked = 0
        self.closed = False

    def read(self, amount, decode_content=True):
        assert decode_content is False, "the body must be read undecoded"
        self.reads += 1
        self.asked += amount
        self.test.mono[0] += self.tick
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        return chunk() if callable(chunk) else chunk

    def close(self):
        self.closed = True


@tagged("post_install", "-at_install")
class TestAccessJwt(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.params = cls.env["ir.config_parameter"].sudo()
        cls.key = SigningKey("sf-kid-1")
        cls.other_key = SigningKey("sf-kid-1")    # same kid, different key
        cls.second_key = SigningKey("sf-kid-2")

    def setUp(self):
        super().setUp()
        access.reset_cache()
        self.addCleanup(access.reset_cache)
        self.mono = [1000.0]
        for name, value in (("_wall", lambda: NOW), ("_clock", lambda: self.mono[0])):
            patcher = patch.object(access, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.served = jwks(self.key)
        self.fetches = []
        patcher = patch.object(access, "_fetch_jwks", self._fake_fetch)
        patcher.start()
        self.addCleanup(patcher.stop)
        self._configure(TEAM, "%d:%s" % (SITE, AUD))

    def _fake_fetch(self, team):
        self.fetches.append(team)
        served = self.served
        if callable(served):
            served = served()
        if isinstance(served, BaseException):
            raise served
        return served

    def _configure(self, team, aud):
        for key, value in ((access.PARAM_TEAM, team), (access.PARAM_AUD, aud)):
            if value is None:
                self.params.search([("key", "=", key)]).unlink()
            else:
                self.params.set_str(key, value)  # 18/20: set_param on 18

    def _ok(self, jwt_value, site=SITE):
        return access.access_ok(self.env, jwt_value, site)

    def _token(self, **overrides):
        return encode(self.key, claims(NOW, **overrides))

    def _reason(self, jwt_value, team=TEAM, auds=frozenset({AUD})):
        with self.assertRaises(access.Refused) as cm:
            access.verify(jwt_value, team, auds)
        return cm.exception.args[0]

    def _assert_refused(self, jwt_value, reason):
        """Refused by verify() for exactly this reason, and by access_ok()."""
        self.assertEqual(self._reason(jwt_value), reason)
        self.assertFalse(self._ok(jwt_value))

    # ------------------------------------------------------------ valid

    def test_valid_jwt_passes(self):
        self.assertTrue(self._ok(self._token()))
        self.assertTrue(self._ok(encode(self.key, service_claims(NOW))),
                        "a service-token JWT has no nbf and no email")
        self.assertTrue(self._ok(self._token(aud=AUD)), "aud as a string")
        self.assertTrue(self._ok(self._token(aud=["other", AUD])))
        self._configure(TEAM, "%d:first-aud, %d:%s" % (SITE, SITE, AUD))
        self.assertTrue(self._ok(self._token()), "one of several AUD tags")
        self.assertEqual(self.fetches, [TEAM], "the key set is fetched once and cached")

    # ------------------------------------------------------------ refused

    def test_missing_or_malformed_jwt(self):
        for value in (None, "", "abc", "a.b", "a.b.c.d", "x" * (access.MAX_JWT_LENGTH + 1)):
            self.assertFalse(self._ok(value), repr(value)[:40])
        self.assertEqual(self._reason(None), "missing")
        self.assertEqual(self._reason("a.b"), "malformed")

    def test_segments_must_be_strict_base64url(self):
        """base64 decoding drops stray characters by default: a token with
        junk inside a segment must not decode to the valid one."""
        head, body, sig = self._token().split(".")
        self.assertTrue(self._ok(".".join((head, body, sig))), "control")
        for bad in ((head, body, sig[:10] + "*" + sig[10:]),
                    (head, body + "=", sig), (head + " ", body, sig)):
            self._assert_refused(".".join(bad), "malformed")

    def test_segments_must_be_canonical_base64url(self):
        """A 256-byte signature leaves 2 unused bits in its last character:
        setting them spells the same bytes differently. Refused."""
        head, body, sig = self._token().split(".")
        self.assertEqual(len(sig) % 4, 2, "fixture: the last character has unused bits")
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        last = alphabet.index(sig[-1])
        variant = sig[:-1] + alphabet[last | 0b0001]
        self.assertNotEqual(variant, sig)
        self.assertEqual(access.base64.urlsafe_b64decode(variant + "=="),
                         access.base64.urlsafe_b64decode(sig + "=="), "fixture: same bytes")
        self._assert_refused(".".join((head, body, variant)), "malformed")

    def test_duplicate_json_names_and_constants_are_refused(self):
        good = json.dumps(claims(NOW))
        self.assertTrue(self._ok(encode(self.key, None, raw_payload=good)), "control")
        dup_aud = good[:-1] + ', "aud": ["another-app"]}'
        self._assert_refused(encode(self.key, None, raw_payload=dup_aud), "malformed")
        dup_alg = '{"alg": "none", "kid": "sf-kid-1", "alg": "RS256"}'
        self._assert_refused(encode(self.key, claims(NOW), raw_header=dup_alg), "malformed")
        # On a payload WITHOUT nbf, so the duplicate-name rule cannot be what
        # refuses it: only the constants rule makes this "malformed".
        no_nbf = json.dumps(claims(NOW, nbf=None))
        for constant in ("NaN", "Infinity", "-Infinity"):
            raw = no_nbf[:-1] + ', "nbf": %s}' % constant
            self._assert_refused(encode(self.key, None, raw_payload=raw), "malformed")

    def test_bad_signature(self):
        self._assert_refused(encode(self.other_key, claims(NOW)), "signature")
        head, _body, sig = self._token().split(".")
        _h, other_body, _s = self._token(email="attacker@example.com").split(".")
        self._assert_refused(".".join((head, other_body, sig)), "signature")

    def test_wrong_aud(self):
        for aud in (["another-app"], "another-app", [], None, [None], 5, AUD.upper(),
                    [AUD, 5]):
            self._assert_refused(self._token(aud=aud), "aud")

    def test_aud_is_bound_to_the_website(self):
        """Two shops with different Access applications: a JWT for one never
        opens the other, and an unlisted website is closed."""
        other_site, other_aud = SITE + 1, "sf-aud-other-shop"
        self._configure(TEAM, "%d:%s,%d:%s" % (SITE, AUD, other_site, other_aud))
        mine, theirs = self._token(), self._token(aud=[other_aud])
        self.assertTrue(self._ok(mine, SITE))
        self.assertTrue(self._ok(theirs, other_site))
        self.assertFalse(self._ok(theirs, SITE))
        self.assertFalse(self._ok(mine, other_site))
        self.assertFalse(self._ok(mine, SITE + 2), "a website not listed is closed")

    def test_wrong_type(self):
        for kind in ("org", None, "APP", ["app"]):
            self._assert_refused(self._token(type=kind), "type")

    def test_wrong_iss(self):
        for iss in ("https://otherteam.cloudflareaccess.com", "http://" + TEAM,
                    "https://%s/" % TEAM, TEAM, None, "https://" + TEAM.upper()):
            self._assert_refused(self._token(iss=iss), "iss")

    def test_expired(self):
        self.assertTrue(self._ok(self._token(exp=NOW - access.LEEWAY + 1)), "within the leeway")
        for exp in (NOW - access.LEEWAY, NOW - access.LEEWAY - 1, NOW - 86400, None, True,
                    "9999999999"):
            self._assert_refused(self._token(exp=exp), "expired")
        # 1e400 is valid JSON and parses to infinity: never "valid forever".
        raw = json.dumps(claims(NOW, exp=None))[:-1] + ', "exp": 1e400}'
        self._assert_refused(encode(self.key, None, raw_payload=raw), "expired")

    def test_nbf_in_the_future(self):
        self.assertTrue(self._ok(self._token(nbf=NOW + access.LEEWAY)), "within the leeway")
        for nbf in (NOW + access.LEEWAY + 1, NOW + 3600, "0", False):
            self._assert_refused(self._token(nbf=nbf), "nbf")

    def test_iat_in_the_future(self):
        self._assert_refused(self._token(iat=NOW + access.LEEWAY + 1), "iat")

    def test_alg_none(self):
        classic = encode(self.key, claims(NOW), alg="none", signer=lambda d: b"")
        self.assertIn(self._reason(classic), ("malformed", "alg"), "empty signature segment")
        self.assertFalse(self._ok(classic))
        self.assertEqual(self._reason(classic + "AA"), "alg", "junk signature")
        # Same header with a genuine RS256 signature: only the alg check can
        # refuse it, so this goes red if that check is removed.
        self._assert_refused(encode(self.key, claims(NOW), alg="none"), "alg")
        self._assert_refused(encode(self.key, claims(NOW), alg="RS512"), "alg")

    def test_alg_hs256_with_public_key_as_secret(self):
        self._assert_refused(encode(self.key, claims(NOW), alg="HS256",
                                    signer=hs256_with_public_key(self.key)), "alg")
        self._assert_refused(encode(self.key, claims(NOW), alg="HS256"), "alg")

    def test_crit_header_refused(self):
        self._assert_refused(encode(self.key, claims(NOW), header_extra={"crit": ["exp"]}),
                             "crit")

    # ------------------------------------------------------------ keys

    def test_unknown_kid_refetches_once_per_minute(self):
        self.assertTrue(self._ok(self._token()))
        self.assertEqual(len(self.fetches), 1)
        # Cloudflare rotated: kid 2 now signs, the cache only knows kid 1.
        self.served = jwks(self.key, self.second_key)
        self.mono[0] += access.REFETCH_INTERVAL
        self.assertTrue(self._ok(encode(self.second_key, claims(NOW))))
        self.assertEqual(len(self.fetches), 2, "an unknown kid triggers one refetch")
        # A kid nobody publishes: refused, and no new fetch inside the minute.
        stray = SigningKey("sf-kid-stray")
        self.mono[0] += 10
        self.assertEqual(self._reason(encode(stray, claims(NOW))), "kid_unknown")
        self.assertEqual(len(self.fetches), 2, "throttled")
        self.assertTrue(self._ok(self._token()), "known kids still pass")
        self.mono[0] += access.REFETCH_INTERVAL
        self.assertEqual(self._reason(encode(stray, claims(NOW))), "kid_unknown")
        self.assertEqual(len(self.fetches), 3, "allowed again after a minute")

    def test_flood_of_unknown_kids_never_touches_a_known_caller(self):
        self.assertTrue(self._ok(self._token()))
        stray = SigningKey("sf-kid-flood")
        good = self._token()
        for i in range(40):
            self.mono[0] += 7          # some inside, some after the throttle window
            self.served = {"keys": ["junk"]} if i % 3 else jwks(self.key)
            self.assertFalse(self._ok(encode(stray, claims(NOW))))
            fetches = len(self.fetches)
            self.assertTrue(self._ok(good), i)
            self.assertEqual(len(self.fetches), fetches, "a known kid never fetches")
        self.assertLessEqual(len(self.fetches), 1 + 40 * 7 // access.REFETCH_INTERVAL + 1)

    def test_known_kid_is_not_held_up_by_a_running_fetch(self):
        """The cache lock is not held during the network fetch: while another
        request waits on Cloudflare, a known kid is answered at once, from the
        fresh set and (within STALE_GRACE) from a stale one."""
        self.assertTrue(self._ok(self._token()))
        started, release = threading.Event(), threading.Event()

        def slow():
            started.set()
            release.wait(5)
            return jwks(self.key)

        def fetch_in_thread(kid_key):
            def run():
                try:
                    access.signing_key(TEAM, kid_key.kid)
                except access.Refused:
                    pass
            thread = threading.Thread(target=run)
            thread.start()
            self.assertTrue(started.wait(5), "fixture: the fetch started")
            return thread

        for stale in (False, True):
            started.clear()
            release.clear()
            self.served = slow
            self.mono[0] += access.REFETCH_INTERVAL + (access.JWKS_TTL if stale else 0)
            thread = fetch_in_thread(self.second_key if not stale else self.key)
            begin = time.monotonic()
            try:
                key = access.signing_key(TEAM, self.key.kid)
            finally:
                elapsed = time.monotonic() - begin
                release.set()
                thread.join(10)
            self.assertIsNotNone(key, stale)
            self.assertLess(elapsed, 1.0, "waited on another request's fetch (stale=%s)" % stale)
        # An unknown kid while a fetch runs is refused, not queued.
        started.clear()
        release.clear()
        self.mono[0] += access.REFETCH_INTERVAL
        thread = fetch_in_thread(self.second_key)
        try:
            with self.assertRaises(access.Refused) as cm:
                access.signing_key(TEAM, "sf-kid-unknown")
        finally:
            release.set()
            thread.join(10)
        self.assertEqual(cm.exception.args[0], "jwks_busy")

    def test_jwks_fetch_failure_refuses(self):
        self.served = OSError("network down")
        self.assertEqual(self._reason(self._token()), "jwks_unavailable")
        self.assertFalse(self._ok(self._token()))
        self.assertEqual(len(self.fetches), 1, "a failure is throttled too")
        self.served = {"keys": []}
        self.mono[0] += access.REFETCH_INTERVAL
        self.assertEqual(self._reason(self._token()), "jwks_empty")

    def test_empty_or_failed_fetch_never_replaces_a_fresh_set(self):
        self.assertTrue(self._ok(self._token()))
        for served in (OSError("down"), {"keys": ["junk"]}, {"keys": [{"kty": "EC"}]},
                       "not a dict"):
            self.served = served
            self.mono[0] += access.REFETCH_INTERVAL
            self.assertFalse(self._ok(encode(self.second_key, claims(NOW))), served)
            self.assertTrue(self._ok(self._token()), "kid 1 is still trusted after %r" % served)

    def test_issuer_empty_key_set_withdraws_every_key(self):
        """{"keys": []} from the issuer is authoritative: kid 1 stops working
        at once, though the old set was still fresh."""
        self.assertTrue(self._ok(self._token()))
        self.served = {"keys": []}
        self.mono[0] += access.REFETCH_INTERVAL
        self.assertFalse(self._ok(encode(self.second_key, claims(NOW))), "triggers the fetch")
        self.assertEqual(self._reason(self._token()), "kid_unknown",
                         "kid 1 is withdrawn, and the next fetch is throttled")

    def test_fetch_has_a_hard_deadline(self):
        """Socket timeouts bound each call, not their sum: the caller waits
        FETCH_DEADLINE at most, whatever the fetch does."""
        release = threading.Event()
        self.addCleanup(release.set)

        def hung():
            release.wait(10)
            return jwks(self.key)

        self.served = hung
        with patch.object(access, "FETCH_DEADLINE", 0.3):
            begin = time.monotonic()
            self.assertEqual(self._reason(self._token()), "jwks_unavailable")
            elapsed = time.monotonic() - begin
        self.assertLess(elapsed, 2.0, "the caller waited for the hung fetch")

    def _hang_fetch(self):
        """Serve a fetch that hangs until the returned event is set."""
        release = threading.Event()
        self.addCleanup(release.set)

        def hung():
            release.wait(10)
            return jwks(self.key)

        self.served = hung
        return release

    def _wait_thread_exit(self, team):
        for _ in range(100):
            with access._lock:
                entry = access._teams.get(team)
                if entry is None or not entry.thread_live:
                    return
            time.sleep(0.02)
        self.fail("fixture: the fetch thread did not exit")

    def test_abandoned_fetch_keeps_the_team_busy_until_it_exits(self):
        release = self._hang_fetch()
        with patch.object(access, "FETCH_DEADLINE", 0.2):
            self.assertEqual(self._reason(self._token()), "jwks_unavailable", "timed out")
            self.mono[0] += access.REFETCH_INTERVAL + 1     # cooldown over
            self.assertEqual(self._reason(self._token()), "jwks_busy",
                             "the abandoned thread still holds the team")
            self.assertEqual(len(self.fetches), 1, "no second fetch while it runs")
            release.set()
            self._wait_thread_exit(TEAM)
            self.served = jwks(self.key)
            self.assertTrue(self._ok(self._token()), "free again once the thread exited")
        self.assertEqual(len(self.fetches), 2)
        self.assertEqual(access._live["threads"], 0)

    def test_stale_key_is_refused_while_a_timed_out_fetch_lingers(self):
        """After the set expires, a fetch that times out is a failed fetch:
        the abandoned thread keeps the team busy, but the stale key is NOT
        served from the grace window meanwhile."""
        self.assertTrue(self._ok(self._token()))
        self.mono[0] += access.JWKS_TTL + 1                 # stale, inside STALE_GRACE
        release = self._hang_fetch()
        with patch.object(access, "FETCH_DEADLINE", 0.2):
            self.assertEqual(self._reason(self._token()), "jwks_unavailable", "timed out")
            with access._lock:
                self.assertTrue(access._teams[TEAM].thread_live, "fixture: thread lingers")
            self.assertEqual(self._reason(self._token()), "jwks_busy",
                             "stale key served after a timed-out fetch")
            release.set()
            self._wait_thread_exit(TEAM)
        # The abandoned thread's late answer is discarded, never installed.
        self.assertEqual(self._reason(self._token()), "jwks_unavailable")

    def test_live_fetch_threads_are_capped_per_worker(self):
        release = self._hang_fetch()
        other = "otherteam.cloudflareaccess.com"
        with patch.object(access, "FETCH_DEADLINE", 0.2), \
                patch.object(access, "MAX_LIVE_FETCHES", 1):
            self.assertEqual(self._reason(self._token()), "jwks_unavailable")
            with self.assertRaises(access.Refused) as cm:
                access.signing_key(other, self.key.kid)
            self.assertEqual(cm.exception.args[0], "jwks_busy")
            self.assertEqual(self.fetches, [TEAM], "the second team never fetched")
            release.set()
            self._wait_thread_exit(TEAM)
            self.served = jwks(self.key)
            access.signing_key(other, self.key.kid)
        self.assertEqual(self.fetches, [TEAM, other])

    def test_result_is_published_in_one_critical_section(self):
        """After the fetch returns, the caller takes the lock once: it clears
        `fetching` and installs the keys together."""
        real = threading.Lock()
        state = {"fetched": False, "after": 0}
        main = threading.current_thread()

        class CountingLock:
            def __enter__(self):
                real.acquire()
                if state["fetched"] and threading.current_thread() is main:
                    state["after"] += 1
                return self

            def __exit__(self, *exc):
                real.release()
                return False

        def fetch():
            state["fetched"] = True
            return jwks(self.key)

        self.served = fetch
        with patch.object(access, "_lock", CountingLock()):
            self.assertTrue(self._ok(self._token()))
        self.assertEqual(state["after"], 1)

    def test_a_fetching_team_is_never_evicted(self):
        with patch.object(access, "MAX_TEAMS", 2):
            self.assertTrue(self._ok(self._token()))
            with access._lock:
                access._teams[TEAM].fetching = True       # a fetch is running
                access._entry("t2.cloudflareaccess.com")
                access._entry("t3.cloudflareaccess.com")  # evicts t2, not TEAM
                self.assertIn(TEAM, access._teams)
                self.assertNotIn("t2.cloudflareaccess.com", access._teams)
                access._teams["t3.cloudflareaccess.com"].fetching = True
                with self.assertRaises(access.Refused) as cm:
                    access._entry("t4.cloudflareaccess.com")
                self.assertEqual(cm.exception.args[0], "jwks_busy")
                access._teams[TEAM].fetching = False

    def test_fetching_flag_is_cleared_when_the_fetch_dies(self):
        self.served = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            access.signing_key(TEAM, self.key.kid)
        self.assertFalse(access._teams[TEAM].fetching)

    def test_stale_keys_are_not_used_after_a_failed_refetch(self):
        self.assertTrue(self._ok(self._token()))
        self.mono[0] += access.JWKS_TTL + 1
        self.served = OSError("network down")
        self.assertEqual(self._reason(self._token()), "jwks_unavailable")
        self.mono[0] += 1
        self.assertEqual(self._reason(self._token()), "jwks_unavailable",
                         "throttled, and the stale set is not trusted meanwhile")
        self.served = jwks(self.key)
        self.mono[0] += access.REFETCH_INTERVAL
        self.assertTrue(self._ok(self._token()))

    def test_keys_and_throttle_are_kept_per_team(self):
        self.assertTrue(self._ok(self._token()))
        other = "otherteam.cloudflareaccess.com"
        self._configure(other, "%d:%s" % (SITE, AUD))
        self.served = OSError("other team unreachable")
        self.assertFalse(self._ok(self._token(iss="https://" + other)),
                         "team 1 keys are not reused")
        self.assertEqual(self.fetches, [TEAM, other])
        # Back to team 1 within the minute: its keys and cooldown survived.
        self._configure(TEAM, "%d:%s" % (SITE, AUD))
        self.assertTrue(self._ok(self._token()))
        self.assertEqual(self._reason(encode(self.second_key, claims(NOW))), "kid_unknown")
        self.assertEqual(self.fetches, [TEAM, other], "no refetch and no cross-team eviction")

    def test_weak_or_unusable_keys_are_ignored(self):
        """Each unusable entry, served ALONE (so the duplicate-kid rule cannot
        hide a missing check), leaves no key."""
        weak = SigningKey("sf-kid-1", bits=1024)
        jwk = self.key.jwk()
        huge_n = b64((2 ** 8200 + 1).to_bytes(1026, "big"))
        cases = [
            ("1024-bit modulus", weak.jwk()),
            ("8201-bit modulus", dict(jwk, n=huge_n)),
            ("use enc", dict(jwk, use="enc")),
            ("alg RS512", dict(jwk, alg="RS512")),
            ("key_ops sign only", dict(jwk, key_ops=["sign"])),
            ("key_ops null", dict(jwk, key_ops=None)),
            ("key_ops repeated", dict(jwk, key_ops=["verify", "verify"])),
            ("key_ops not strings", dict(jwk, key_ops=["verify", 5])),
            ("exponent over 32 bits", dict(jwk, e=b64((2 ** 40 + 1).to_bytes(6, "big")))),
            ("even exponent", dict(jwk, e=b64((65538).to_bytes(3, "big")))),
            ("EC key", {"kty": "EC", "kid": "sf-kid-1"}),
            ("not an object", "junk"),
        ]
        for what, entry in cases:
            self.mono[0] += access.REFETCH_INTERVAL
            self.served = {"keys": [entry]}
            self.assertEqual(self._reason(self._token()), "jwks_empty", what)
        self.mono[0] += access.REFETCH_INTERVAL
        self.served = {"keys": [dict(jwk, key_ops=["verify"])]}
        self.assertTrue(self._ok(self._token()), "control: key_ops with verify is usable")

    def test_one_bad_key_does_not_spoil_the_set(self):
        bad = dict(self.second_key.jwk(), e=b64((1).to_bytes(1, "big")))      # e = 1
        broken = dict(self.second_key.jwk(), kid="sf-kid-3", n="!!")
        self.served = {"keys": [bad, broken, self.key.jwk()]}
        self.assertTrue(self._ok(self._token()))
        real = access.rsa.RSAPublicNumbers
        calls = []

        def flaky(e, n):
            calls.append(e)
            if len(calls) == 1:
                raise ValueError("backend refused the first key")
            return real(e, n)

        access.reset_cache()
        self.served = {"keys": [dict(self.second_key.jwk()), self.key.jwk()]}
        with patch.object(access.rsa, "RSAPublicNumbers", flaky):
            self.assertTrue(self._ok(self._token()))
        self.assertEqual(len(calls), 2)

    def test_duplicate_kid_is_ambiguous_and_dropped(self):
        self.served = {"keys": [self.key.jwk(), dict(self.other_key.jwk())]}
        self.assertEqual(self._reason(self._token()), "jwks_empty")

    def test_fetch_reads_status_first_with_a_size_and_time_bound(self):
        opened = []

        def serve(res):
            def fake_open(url):
                opened.append(url)
                return res
            return patch.object(access, "_open", fake_open)

        body = json.dumps(jwks(self.key)).encode()
        ok = FakeResponse(self, chunks=[body[:100], body[100:]])
        with serve(ok):
            self.assertEqual(REAL_FETCH(TEAM), jwks(self.key))
        self.assertEqual(opened, ["https://%s/cdn-cgi/access/certs" % TEAM])
        self.assertTrue(ok.closed)
        cases = {
            "jwks_status": FakeResponse(self, status=302, chunks=[b"x" * 10 ** 6]),
            "jwks_encoding": FakeResponse(self, headers={"Content-Encoding": "gzip"},
                                          chunks=[b"x"]),
            "jwks_size": FakeResponse(self, chunks=[b" " * 4096] * 100),
            "jwks_slow_at_eof": FakeResponse(self, chunks=[], tick=access.FETCH_DEADLINE + 1),
            "jwks_slow": FakeResponse(self, chunks=[b" "] * 100, tick=1.0),
        }
        for reason, res in cases.items():
            with serve(res), self.assertRaises(access.Refused) as cm:
                REAL_FETCH(TEAM)
            self.assertEqual(cm.exception.args[0], reason.replace("_at_eof", ""))
            self.assertTrue(res.closed, reason)
        self.assertEqual(cases["jwks_status"].reads, 0, "a redirect body is never read")
        self.assertEqual(cases["jwks_encoding"].reads, 0)
        self.assertLessEqual(cases["jwks_size"].reads, access.MAX_JWKS_BYTES // 4096 + 1)
        self.assertLessEqual(cases["jwks_size"].asked, access.MAX_JWKS_BYTES + 1,
                             "never asks for more than one byte past the cap")
        self.assertLessEqual(cases["jwks_slow"].reads, access.FETCH_DEADLINE + 1)

    def test_fetch_request_shape(self):
        calls = []

        class Pool:
            def request(self, method, url, **kwargs):
                calls.append((method, url, kwargs))
                return FakeResponse(None, status=500)

        with patch.object(access, "_pool", lambda: Pool()):
            with self.assertRaises(access.Refused):
                REAL_FETCH(TEAM)
            for team in ("evil.com/.cloudflareaccess.com", "evil.com#.cloudflareaccess.com",
                         "u@sfteam.cloudflareaccess.com", "sfteam.cloudflareaccess.com:8443",
                         "a.b.cloudflareaccess.com", "cloudflareaccess.com"):
                with self.assertRaises(access.Refused):
                    REAL_FETCH(team)
        self.assertEqual(len(calls), 1, "no request to an invalid team host")
        method, url, kwargs = calls[0]
        self.assertEqual((method, url), ("GET", "https://%s/cdn-cgi/access/certs" % TEAM))
        self.assertIs(kwargs["redirect"], False)
        self.assertIs(kwargs["retries"], False)
        self.assertIs(kwargs["preload_content"], False)
        self.assertIs(kwargs["decode_content"], False)
        self.assertEqual(kwargs["headers"]["Accept-Encoding"], "identity")
        self.assertEqual(kwargs["timeout"].connect_timeout, access.FETCH_CONNECT_TIMEOUT)
        self.assertEqual(kwargs["timeout"].read_timeout, access.FETCH_READ_TIMEOUT)

    def test_pool_verifies_certificates(self):
        access._http = None
        self.addCleanup(setattr, access, "_http", None)
        pool = access._pool()
        self.assertEqual(pool.connection_pool_kw.get("cert_reqs"), "CERT_REQUIRED")
        self.assertTrue(pool.connection_pool_kw.get("ca_certs"))

    # ------------------------------------------------------------ settings

    def test_only_one_parameter_set_closes_the_endpoint(self):
        good = self._token()
        aud = "%d:%s" % (SITE, AUD)
        for team, value in ((TEAM, None), (None, aud), (TEAM, ""), ("", aud), (TEAM, " , ")):
            self._configure(team, value)
            self.assertIsNone(access.settings(self.env), (team, value))
            self.assertFalse(self._ok(good), (team, value))
        self.assertEqual(self.fetches, [], "a misconfigured lock fetches nothing")

    def test_aud_entries_must_name_a_website(self):
        good = self._token()
        for value in (AUD, "%d:%s,%s" % (SITE, AUD, AUD), "x:%s" % AUD, ":%s" % AUD,
                      "%d:" % SITE, "%d:%s:extra" % (SITE, AUD), "%d: %s" % (SITE, AUD)):
            self._configure(TEAM, value)
            self.assertIsNone(access.settings(self.env), value)
            self.assertFalse(self._ok(good), value)
        self._configure(TEAM, " %d:%s , %d:b " % (SITE, AUD, SITE + 1))
        self.assertEqual(access.settings(self.env),
                         (TEAM, {SITE: frozenset({AUD}), SITE + 1: frozenset({"b"})}))

    def test_invalid_team_domain_closes_the_endpoint(self):
        aud = "%d:%s" % (SITE, AUD)
        for team in ("evil.com/.cloudflareaccess.com", "https://" + TEAM, TEAM + "/",
                     TEAM + ":443", "u@" + TEAM, "a.b.cloudflareaccess.com",
                     "cloudflareaccess.com", "sfteam.cloudflareaccess.com.evil.com",
                     "sfteam.example.com"):
            self._configure(team, aud)
            self.assertIsNone(access.settings(self.env), team)
            self.assertFalse(self._ok(self._token()), team)
        self.assertEqual(self.fetches, [])
        self._configure("  SFTeam.CloudflareAccess.com ", aud)
        self.assertEqual(access.settings(self.env), (TEAM, {SITE: frozenset({AUD})}))

    def test_neither_parameter_set_is_token_only(self):
        self._configure(None, None)
        for value in (None, "", "garbage"):
            self.assertTrue(self._ok(value), repr(value))
        self._configure("", "  ")
        self.assertTrue(self._ok(None), "empty values count as unset")
        self.assertEqual(self.fetches, [])

    def test_refusal_is_logged_without_the_jwt(self):
        bad = self._token(aud=["another-app"])
        lines = []

        def record(msg, *args):
            lines.append(msg % args)

        with patch.object(access._logger, "info", record), \
                patch.object(access._logger, "warning", record):
            self.assertFalse(self._ok(bad))
        self.assertEqual(lines, ["storefront API refused: access JWT aud"])
