"""Auth0 authentication helpers for the Flask app."""

import os
from functools import wraps
from flask import session, redirect, url_for
from auth0_server_python.auth_server.server_client import ServerClient
from dotenv import load_dotenv

load_dotenv()

# Simple in-memory storage for development
# For production, use Redis, PostgreSQL, or other persistent storage
class MemoryStateStore:
    """In-memory state store for session data (development only)"""
    def __init__(self):
        self._data = {}
    
    async def get(self, key, options=None):
        return self._data.get(key)
    
    async def set(self, key, value, options=None):
        self._data[key] = value
    
    async def delete(self, key, options=None):
        self._data.pop(key, None)
    
    async def delete_by_logout_token(self, claims, options=None):
        # For backchannel logout support
        pass

class MemoryTransactionStore:
    """In-memory transaction store for OAuth flows (development only)"""
    def __init__(self):
        self._data = {}
    
    async def get(self, key, options=None):
        return self._data.get(key)
    
    async def set(self, key, value, options=None):
        self._data[key] = value
    
    async def delete(self, key, options=None):
        self._data.pop(key, None)

# Initialize stores
state_store = MemoryStateStore()
transaction_store = MemoryTransactionStore()

# Initialize the Auth0 ServerClient
auth0 = ServerClient(
    domain=os.getenv('AUTH0_DOMAIN'),
    client_id=os.getenv('AUTH0_CLIENT_ID'),
    client_secret=os.getenv('AUTH0_CLIENT_SECRET'),
    secret=os.getenv('AUTH0_SECRET'),
    redirect_uri=os.getenv('AUTH0_REDIRECT_URI'),
    state_store=state_store,
    transaction_store=transaction_store,
    authorization_params={
        'scope': 'openid profile email',
        'audience': os.getenv('AUTH0_AUDIENCE', '')  # Optional: for API access
    }
)


def requires_auth(f):
    """Decorator to require authentication for a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_user_info():
    """Get the current user's info from session."""
    user = session.get('user')
    if not user:
        return None
    
    userinfo = user.get('userinfo', {})
    return {
        'sub': userinfo.get('sub'),
        'name': userinfo.get('name'),
        'email': userinfo.get('email'),
        'picture': userinfo.get('picture'),
    }
