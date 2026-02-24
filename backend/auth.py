"""
Authentication module stub.
Provides user authentication for API endpoints.
"""

from typing import Any, Dict


async def get_current_user() -> Dict[str, Any]:
    """
    Get current user from request.
    
    For local development, returns a default anonymous user.
    In production, this should validate JWT tokens or session cookies.
    """
    return {
        "id": "anonymous",
        "name": "Anonymous User",
        "authenticated": False
    }
