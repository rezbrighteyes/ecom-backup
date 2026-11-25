# -*- coding: utf-8 -*-
"""Signed test JWTs and a fake JWKS, for the Cloudflare Access lock tests."""

import base64
import hashlib
import hmac
import json
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

TEAM = "sfteam.cloudflareaccess.com"
AUD = "sf-aud-32eafc7626e974616deaf0dc3ce63d7b"


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _uint(number):
    return b64(number.to_bytes((number.bit_length() + 7) // 8, "big"))


class SigningKey:

    def __init__(self, kid, bits=2048):
        self.kid = kid
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=bits)

    def jwk(self):
        numbers = self.private.public_key().public_numbers()
        return {"kid": self.kid, "kty": "RSA", "alg": "RS256", "use": "sig",
                "e": _uint(numbers.e), "n": _uint(numbers.n)}

    def public_pem(self):
        return self.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

    def sign(self, data):
        return self.private.sign(data, padding.PKCS1v15(), hashes.SHA256())


def jwks(*keys):
    return {"keys": [k.jwk() for k in keys]}


def claims(now=None, **overrides):
    """A user-login payload as Cloudflare documents it. A key set to None is
    left out."""
    now = int(time.time() if now is None else now)
    body = {"aud": [AUD], "email": "owner@example.com", "exp": now + 600, "iat": now,
            "nbf": now, "iss": "https://" + TEAM, "type": "app", "sub": "sf-user"}
    body.update(overrides)
    return {k: v for k, v in body.items() if v is not None}


def service_claims(now=None):
    """A service-token payload as Cloudflare documents it: no nbf, no email."""
    now = int(time.time() if now is None else now)
    return {"type": "app", "aud": [AUD], "exp": now + 600, "iss": "https://" + TEAM,
            "common_name": "sf0123456789.access", "iat": now, "sub": ""}


def encode(key, payload, alg="RS256", kid=None, signer=None, header_extra=None,
           raw_header=None, raw_payload=None):
    """A compact JWS. signer(data) -> signature bytes; defaults to key's RS256.
    raw_header / raw_payload: JSON text used as is (duplicate keys, 1e400)."""
    header = {"alg": alg, "typ": "JWT", "kid": key.kid if kid is None else kid}
    header.update(header_extra or {})
    head = b64((raw_header or json.dumps(header)).encode())
    body = b64((raw_payload or json.dumps(payload)).encode())
    data = ("%s.%s" % (head, body)).encode("ascii")
    signature = (signer or key.sign)(data)
    return "%s.%s.%s" % (head, body, b64(signature))


def hs256_with_public_key(key):
    """The classic key-confusion forgery: HMAC keyed with the public key PEM."""
    return lambda data: hmac.new(key.public_pem(), data, hashlib.sha256).digest()
