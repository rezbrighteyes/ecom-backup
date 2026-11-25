# -*- coding: utf-8 -*-
"""Second lock: a Cloudflare Access JWT on every request, when configured.

The token alone (gate.check / catalogue.token_ok) can be replayed by anyone
who copies it, and the Odoo.sh host can be reached without going through
Cloudflare. When both parameters below are set, every request must ALSO carry
the JWT that Cloudflare Access adds to requests it let through:

* header  Cf-Access-Jwt-Assertion (RS256, signed by the team's Access keys)
* keys    https://<team domain>/cdn-cgi/access/certs (JWKS, "keys" list)
* claims  aud contains the AUD tag configured for the requested WEBSITE,
          iss == https://<team domain>, exp in the future, nbf / iat (when
          present) not in the future

Cloudflare docs: cloudflare-one/identity/authorization-cookie/validating-json/
and .../application-token/ (a service-token JWT carries no nbf).

Parameters (ir.config_parameter):
  reza_storefront_api.access_team_domain   e.g. yourteam.cloudflareaccess.com
  reza_storefront_api.access_aud           <website_id>:<AUD tag>, comma
                                           separated, e.g. "2:ab12...,4:cd34..."
Both set: the JWT is required, and only websites listed in access_aud are
served (each with its own AUD tags). Neither set: token only. Exactly one set,
a team domain that is not exactly <label>.cloudflareaccess.com, or ANY
access_aud entry without a numeric website id: closed. A bare AUD is refused
on purpose: it would let a JWT for one shop's Access application open every
shop in the database.

Plain module functions; nothing here is on a model, so nothing is reachable
over RPC. Uses only `cryptography` and `urllib3` / `certifi` (installed with
`requests`), all Odoo core dependencies (PyJWT is not installed on 18 or 20).

Odoo 20 version. The Odoo 18 copy differs only where marked "18/20".
"""

import base64
import binascii
import collections
import json
import logging
import math
import re
import threading
import time

import certifi
import urllib3
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_logger = logging.getLogger(__name__)

JWT_HEADER = "Cf-Access-Jwt-Assertion"
PARAM_TEAM = "reza_storefront_api.access_team_domain"
PARAM_AUD = "reza_storefront_api.access_aud"
LEEWAY = 30                 # seconds, for exp / nbf / iat
JWKS_TTL = 3600             # seconds a fetched key set is trusted
STALE_GRACE = 300           # a stale set still serves known kids WHILE a refresh runs
REFETCH_INTERVAL = 60       # per team: at most one fetch attempt a minute, failed or not
FETCH_CONNECT_TIMEOUT = 5
FETCH_READ_TIMEOUT = 2      # per socket read
FETCH_DEADLINE = 5          # hard bound for the caller: DNS, connect, headers, body
FETCH_CHUNK = 4096
MAX_JWKS_BYTES = 65536
MAX_JWT_LENGTH = 8192
MIN_RSA_BITS = 2048
MAX_RSA_BITS = 8192
MAX_TEAMS = 8               # teams cached per worker
MAX_LIVE_FETCHES = 4        # fetch threads alive at once per worker, abandoned ones included

_TEAM = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com", re.ASCII)
_SEGMENT = re.compile(r"[A-Za-z0-9_-]+", re.ASCII)
_AUD_ENTRY = re.compile(r"([0-9]{1,9}):([A-Za-z0-9._-]{1,256})", re.ASCII)
_NOT_CONFIGURED = "off"

_lock = threading.Lock()     # guards _teams and _live; never held during network I/O
_teams = collections.OrderedDict()
_live = {"threads": 0}       # fetch threads still running in this worker
_clock = time.monotonic      # replaced in tests
_wall = time.time            # replaced in tests
_http = None


class Refused(Exception):
    """A JWT check failed. args[0] is a short reason code, safe to log."""


class _TeamKeys:
    __slots__ = ("keys", "fetched", "attempt", "fetching", "thread_live")

    def __init__(self):
        self.keys = {}
        self.fetched = None
        self.attempt = None
        self.fetching = False       # a request is waiting on this team's fetch
        self.thread_live = False    # this team's fetch thread has not exited yet

    def busy(self):
        return self.fetching or self.thread_live


def reset_cache():
    with _lock:
        _teams.clear()
        _live["threads"] = 0


# ---------------------------------------------------------------- config

def settings(env):
    """(team_domain, {website_id: frozenset(aud)}) when the lock is on,
    _NOT_CONFIGURED when it is off, None when it is misconfigured (closed)."""
    params = env["ir.config_parameter"].sudo()
    team = (params.get_str(PARAM_TEAM) or "").strip().lower()  # 18/20: get_param on 18
    aud = (params.get_str(PARAM_AUD) or "").strip()  # 18/20: get_param on 18
    if not team and not aud:
        return _NOT_CONFIGURED
    if not team or not aud or not _TEAM.fullmatch(team):
        return None
    per_site = {}
    for entry in aud.split(","):
        entry = entry.strip()
        if not entry:
            continue
        match = _AUD_ENTRY.fullmatch(entry)
        if not match:
            return None
        per_site.setdefault(int(match.group(1)), set()).add(match.group(2))
    if not per_site:
        return None
    return team, {site: frozenset(auds) for site, auds in per_site.items()}


def access_ok(env, jwt_value, website_id):
    """True when the request for website_id may pass this lock. Never raises."""
    try:
        conf = settings(env)
        if conf == _NOT_CONFIGURED:
            return True
        if conf is None:
            raise Refused("misconfigured")
        auds = conf[1].get(website_id)
        if not auds:
            raise Refused("website_not_listed")
        verify(jwt_value, conf[0], auds)
        return True
    except Refused as exc:
        _logger.info("storefront API refused: access JWT %s", exc.args[0])
    except Exception as exc:  # noqa: BLE001 - never accept on an unexpected error
        _logger.warning("storefront API refused: access JWT check error %s", type(exc).__name__)
    return False


# ---------------------------------------------------------------- JWT

def _b64(segment):
    """Strict base64url: the alphabet only, no padding, and canonical (the
    unused bits of the last character must be zero), so one value has one
    spelling."""
    if not _SEGMENT.fullmatch(segment):
        raise Refused("malformed")
    try:
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (binascii.Error, ValueError):
        raise Refused("malformed") from None
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != segment:
        raise Refused("malformed")
    return raw


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise Refused("malformed")
        out[key] = value
    return out


def _no_constants(name):
    raise Refused("malformed")


def _json_object(raw):
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates,
                           parse_constant=_no_constants)
    except (UnicodeDecodeError, ValueError):
        raise Refused("malformed") from None
    if not isinstance(value, dict):
        raise Refused("malformed")
    return value


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def verify(jwt_value, team, auds):
    """Raise Refused unless jwt_value is a valid Access JWT for team/auds."""
    if not jwt_value or not isinstance(jwt_value, str):
        raise Refused("missing")
    if len(jwt_value) > MAX_JWT_LENGTH:
        raise Refused("malformed")
    parts = jwt_value.split(".")
    if len(parts) != 3:
        raise Refused("malformed")
    header_raw, claims_raw, signature = (_b64(part) for part in parts)
    header = _json_object(header_raw)
    if header.get("alg") != "RS256":
        raise Refused("alg")
    if "crit" in header:
        raise Refused("crit")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise Refused("kid")
    claims = _json_object(claims_raw)
    key = signing_key(team, kid)
    try:
        key.verify(signature, (parts[0] + "." + parts[1]).encode("ascii"),
                   padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise Refused("signature") from None
    if claims.get("iss") != "https://" + team:
        raise Refused("iss")
    aud = claims.get("aud")
    aud = [aud] if isinstance(aud, str) else aud
    if (not isinstance(aud, list) or not aud or not all(isinstance(a, str) for a in aud)
            or not any(a in auds for a in aud)):
        raise Refused("aud")
    # Cloudflare documents "app" for application tokens (user and service
    # token alike) and "org" for the global session token.
    if claims.get("type") != "app":
        raise Refused("type")
    now = _wall()
    exp = claims.get("exp")
    if not _number(exp) or now >= exp + LEEWAY:
        raise Refused("expired")
    if "nbf" in claims and (not _number(claims["nbf"]) or now < claims["nbf"] - LEEWAY):
        raise Refused("nbf")
    if "iat" in claims and (not _number(claims["iat"]) or now < claims["iat"] - LEEWAY):
        raise Refused("iat")
    return claims


# ---------------------------------------------------------------- keys

def _pool():
    global _http
    if _http is None:
        _http = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=certifi.where(),
                                    retries=False)
    return _http


def _open(url):
    """The response with its body NOT read: no redirect is followed (and so
    no redirect body is read), no retry, no content decoding."""
    return _pool().request(
        "GET", url,
        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        timeout=urllib3.Timeout(connect=FETCH_CONNECT_TIMEOUT, read=FETCH_READ_TIMEOUT),
        redirect=False, retries=False, preload_content=False, decode_content=False)


def _fetch_jwks(team):
    """The team's JWKS as a dict. HTTPS to the validated team host only, the
    status read before the body, at most MAX_JWKS_BYTES of undecoded body, and
    the whole body within FETCH_DEADLINE seconds."""
    if not _TEAM.fullmatch(team or ""):
        raise Refused("misconfigured")
    deadline = _clock() + FETCH_DEADLINE
    res = _open("https://%s/cdn-cgi/access/certs" % team)
    try:
        if res.status != 200:
            raise Refused("jwks_status")
        encoding = (res.headers.get("Content-Encoding") or "identity").strip().lower()
        if encoding != "identity":
            raise Refused("jwks_encoding")
        body = bytearray()
        while True:
            if _clock() > deadline:
                raise Refused("jwks_slow")
            # Never ask for more than one byte past the cap.
            want = min(FETCH_CHUNK, MAX_JWKS_BYTES + 1 - len(body))
            chunk = res.read(want, decode_content=False)
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > MAX_JWKS_BYTES:
                raise Refused("jwks_size")
        if _clock() > deadline:
            raise Refused("jwks_slow")
    finally:
        res.close()
    return json.loads(bytes(body).decode("utf-8"))


def _fetch_bounded(team, entry):
    """_fetch_jwks in a daemon thread, waited on for FETCH_DEADLINE seconds at
    most. Socket timeouts bound each blocking call but not their sum (DNS is
    not bounded by them at all); this is the caller's hard bound. A fetch
    still running at the deadline is abandoned and its result discarded, but
    its slot is NOT released until the thread really exits: the team stays
    busy (no second fetch for it) and the thread counts against
    MAX_LIVE_FETCHES for the whole worker. The caller reserved both under the
    lock (signing_key)."""
    box = {}

    def release():
        with _lock:
            entry.thread_live = False
            _live["threads"] = max(0, _live["threads"] - 1)

    def run():
        try:
            box["value"] = _fetch_jwks(team)
        except BaseException as exc:  # noqa: BLE001 - handed to the caller
            box["error"] = exc
        finally:
            release()

    thread = threading.Thread(target=run, name="storefront-jwks-fetch", daemon=True)
    try:
        thread.start()
    except BaseException:
        release()
        raise
    thread.join(FETCH_DEADLINE)
    if thread.is_alive():
        raise Refused("jwks_slow")
    if "error" in box:
        raise box["error"]
    return box["value"]


def _int(value):
    return int.from_bytes(_b64(value), "big") if isinstance(value, str) else None


def _key(jwk):
    """One RSA verification key from a JWK, or None when it is unusable."""
    if not isinstance(jwk, dict) or jwk.get("kty") != "RSA":
        return None
    if jwk.get("alg", "RS256") != "RS256" or jwk.get("use", "sig") != "sig":
        return None
    if "key_ops" in jwk:
        ops = jwk["key_ops"]
        if (not isinstance(ops, list) or not all(isinstance(op, str) for op in ops)
                or len(set(ops)) != len(ops) or "verify" not in ops):
            return None
    n, e = _int(jwk.get("n")), _int(jwk.get("e"))
    if not n or not e:
        return None
    if not MIN_RSA_BITS <= n.bit_length() <= MAX_RSA_BITS:
        return None
    if e < 3 or e % 2 == 0 or e.bit_length() > 32:
        return None
    return rsa.RSAPublicNumbers(e, n).public_key()


def _parse_keys(jwks):
    """kid -> key for every usable entry. One bad entry is skipped on its own;
    a kid published twice is ambiguous and is dropped."""
    keys, seen = {}, collections.Counter()
    listed = jwks.get("keys") if isinstance(jwks, dict) else None
    for jwk in listed if isinstance(listed, list) else ():
        kid = jwk.get("kid") if isinstance(jwk, dict) else None
        if not isinstance(kid, str) or not kid:
            continue
        seen[kid] += 1
        try:
            key = _key(jwk)
        except Exception:  # noqa: BLE001 - one bad entry never spoils the set
            key = None
        if key is not None:
            keys[kid] = key
    return {kid: key for kid, key in keys.items() if seen[kid] == 1}


def _entry(team):
    """The team's cache entry. Least recently used teams are evicted beyond
    MAX_TEAMS, but never one whose fetch is running: if every other entry is
    fetching, the new team is refused instead."""
    entry = _teams.get(team)
    if entry is None:
        if len(_teams) >= MAX_TEAMS:
            idle = next((name for name, other in _teams.items() if not other.busy()), None)
            if idle is None:
                raise Refused("jwks_busy")
            del _teams[idle]
        entry = _teams[team] = _TeamKeys()
    _teams.move_to_end(team)
    return entry


def signing_key(team, kid):
    """The team's public key for kid, never waiting on another request's fetch.

    A kid in the team's fresh set (younger than JWKS_TTL) is answered at once.
    Otherwise this request fetches the set, unless the team was fetched less
    than REFETCH_INTERVAL ago (refused) or another request is fetching it
    right now (a known kid is then served from the stale set for up to
    STALE_GRACE; an unknown one is refused). The lock is never held during
    the fetch. An issuer answer of {"keys": []} withdraws every key at once;
    a failed or unusable fetch never replaces a set; a stale set is never
    used after a failed fetch.

    Residual risk, stated plainly:
    * Refresh is on demand: the first request that needs an expired set
      waits for the fetch (at most FETCH_DEADLINE).
    * A kid that Cloudflare publishes less than REFETCH_INTERVAL after this
      worker's last fetch is refused until the interval passes (each worker
      has its own cache and interval). Cloudflare keeps the previous key valid
      for 7 days after a rotation, so routine rotation is not affected.
    * Revocation: a removed key stays trusted until the set expires
      (JWKS_TTL, plus STALE_GRACE while a refresh runs) unless a fetch sees
      the withdrawal first. Do not rely on this for emergency revocation:
      restart the workers, or delete access_aud ALONE (one Access parameter
      without the other closes the endpoint at once; deleting both would
      fall back to token only)."""
    with _lock:
        entry = _entry(team)
        now = _clock()
        age = None if entry.fetched is None else now - entry.fetched
        if age is not None and age < JWKS_TTL and kid in entry.keys:
            return entry.keys[kid]
        if entry.busy():
            # Stale keys are served only while another REQUEST is waiting on
            # a live fetch (entry.fetching), never because an abandoned,
            # timed-out thread is still alive: a timed-out fetch is a failed
            # fetch, and a stale set is never used after a failed fetch.
            if (entry.fetching and age is not None and age < JWKS_TTL + STALE_GRACE
                    and kid in entry.keys):
                return entry.keys[kid]
            raise Refused("jwks_busy")
        if entry.attempt is not None and now - entry.attempt < REFETCH_INTERVAL:
            raise Refused("kid_unknown" if age is not None and age < JWKS_TTL
                          else "jwks_unavailable")
        if _live["threads"] >= MAX_LIVE_FETCHES:
            raise Refused("jwks_busy")
        entry.fetching = True
        entry.thread_live = True
        _live["threads"] += 1
        entry.attempt = now
    keys, reason, withdrawn = {}, None, False
    try:
        jwks = _fetch_bounded(team, entry)
        keys = _parse_keys(jwks)
        # {"keys": []} from the issuer itself is a withdrawal of every key,
        # not a broken answer: honour it at once.
        withdrawn = isinstance(jwks, dict) and jwks.get("keys") == []
        if not keys:
            reason = "jwks_empty"
    except Exception as exc:  # noqa: BLE001 - any failure refuses
        reason = exc.args[0] if isinstance(exc, Refused) else type(exc).__name__
        _logger.warning("storefront API: Access key fetch failed (%s)", reason)
        reason = "jwks_unavailable"
    except BaseException:
        with _lock:
            entry.fetching = False
        raise
    # The result is published and `fetching` cleared in ONE critical section,
    # so no newer refresh can run between the two.
    with _lock:
        entry.fetching = False
        if _teams.get(team) is not entry:
            raise Refused("jwks_busy")
        if withdrawn:
            entry.keys = {}
            entry.fetched = _clock()
            raise Refused("jwks_empty")
        if keys:
            entry.keys = keys
            entry.fetched = _clock()
            if kid in keys:
                return keys[kid]
            raise Refused("kid_unknown")
        fresh = entry.fetched is not None and _clock() - entry.fetched < JWKS_TTL
        if fresh and kid in entry.keys:
            return entry.keys[kid]
        raise Refused(reason)
