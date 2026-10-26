import base64
import json
import time
from functools import cache

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from sermon.config import CloudflareAccess

TEAM_DOMAIN = "reformation.cloudflareaccess.com"
AUDIENCE = "32eafc7626e974616f467e2d9e1ba0a3f3c1c5e0b2e9c2b8c1fd6d8e0d2d4a7b"
ACCESS = CloudflareAccess(team_domain=TEAM_DOMAIN, audience=AUDIENCE)
KEY_ID = "9c5a1e0f"
EMAIL = "pastor@reformation.example"


@cache
def keypair(name="signing"):
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def private_pem(name="signing"):
    return keypair(name).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def public_pem(name="signing"):
    return keypair(name).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def public_jwk(name="signing", kid=KEY_ID):
    published = jwt.algorithms.RSAAlgorithm.to_jwk(keypair(name).public_key(), as_dict=True)
    return {**published, "kid": kid, "alg": "RS256", "use": "sig"}


def published_keys(*jwks):
    return {"keys": list(jwks), "public_cert": {}, "public_certs": []}


def claims(**overrides):
    now = int(time.time())
    return {
        "aud": [AUDIENCE],
        "email": EMAIL,
        "exp": now + 600,
        "iat": now,
        "nbf": now,
        "iss": f"https://{TEAM_DOMAIN}",
        "type": "app",
        "sub": "0c8f6d7e-1a2b-4c3d-8e9f-a0b1c2d3e4f5",
        **overrides,
    }


def without(payload, *names):
    return {name: value for name, value in payload.items() if name not in names}


def signed(payload=None, *, key="signing", kid=KEY_ID, algorithm="RS256"):
    return jwt.encode(
        claims() if payload is None else payload,
        private_pem(key),
        algorithm=algorithm,
        headers={"kid": kid},
    )


def segment(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()


def unsigned(payload=None, kid=KEY_ID):
    return f"{segment({'alg': 'none', 'typ': 'JWT', 'kid': kid})}.{segment(payload or claims())}."


def signed_with_the_public_key_as_a_shared_secret(payload=None, kid=KEY_ID):
    import hashlib
    import hmac

    head = f"{segment({'alg': 'HS256', 'typ': 'JWT', 'kid': kid})}.{segment(payload or claims())}"
    mac = hmac.new(public_pem(), head.encode(), hashlib.sha256).digest()
    return f"{head}.{base64.urlsafe_b64encode(mac).rstrip(b'=').decode()}"
