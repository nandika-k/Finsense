"""Auth0 JWT verification helpers for FastAPI endpoints."""

import os
from auth0_server_python.auth_server.server_client import ServerClient
from dotenv import load_dotenv

load_dotenv()

# Simple in-memory storage for development
from functools import lru_cache
from typing import Any, Dict

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


security = HTTPBearer(auto_error=False)


def is_auth_enabled() -> bool:
    """Return True when Auth0 configuration is present."""
    return bool(os.getenv("AUTH0_DOMAIN") and os.getenv("AUTH0_AUDIENCE"))


class Auth0TokenVerifier:
    """Validate Auth0 access tokens against tenant JWKS."""

    def __init__(self, domain: str, audience: str, algorithms: list[str] | None = None) -> None:
        if not domain or not audience:
            raise ValueError("Auth0 domain and audience are required")

        self.domain = domain
        self.audience = audience
        self.algorithms = algorithms or ["RS256"]
        self.issuer = f"https://{self.domain}/"
        self.jwks_client = jwt.PyJWKClient(f"{self.issuer}.well-known/jwks.json")

    def verify(self, token: str) -> Dict[str, Any]:
        """Decode and validate a JWT access token."""
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
            )
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc


@lru_cache(maxsize=1)
def get_verifier() -> Auth0TokenVerifier:
    """Return cached verifier initialized from environment variables."""
    domain = os.getenv("AUTH0_DOMAIN", "").strip()
    audience = os.getenv("AUTH0_AUDIENCE", "").strip()
    return Auth0TokenVerifier(domain=domain, audience=audience)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> Dict[str, Any]:
    """FastAPI dependency that authenticates and returns token claims."""
    if not is_auth_enabled():
        return {"sub": "local-dev-user", "auth_disabled": True}

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization bearer token is required")

    verifier = get_verifier()
    return verifier.verify(credentials.credentials)
