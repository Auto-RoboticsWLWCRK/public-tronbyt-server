"""Supabase authentication middleware.

This module provides authentication middleware for Supabase Auth integration.
It handles JWT token validation, session management, and user authentication.

Usage:
    from tronbyt_server.supabase_auth import require_user, get_current_user

    @router.get("/protected")
    async def protected_route(user: SupabaseUser = Depends(require_user)):
        return {"user": user.username}
"""

import logging
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from tronbyt_server.supabase_client import (
    get_supabase_admin_client,
    get_supabase_client,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class SupabaseUser(BaseModel):
    """Represents an authenticated Supabase user."""

    id: str
    email: str
    username: str
    is_admin: bool = False
    theme_preference: str = "system"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> SupabaseUser | None:
    """Get the current authenticated user from Supabase session.

    This function attempts to authenticate the user via:
    1. Authorization header (Bearer token)
    2. Cookie-based session (sb-access-token)

    Args:
        request: The FastAPI request object.
        credentials: Optional HTTP authorization credentials.

    Returns:
        SupabaseUser if authenticated, None otherwise.
    """
    supabase = get_supabase_client()

    # Try to get token from Authorization header
    token = None
    if credentials:
        token = credentials.credentials

    # Fallback to cookie-based session
    if not token:
        token = request.cookies.get("sb-access-token")

    if not token:
        return None

    try:
        # Verify the token with Supabase
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            return None

        auth_user = user_response.user

        # Get user profile from database
        profile_response = (
            supabase.table("user_profiles")
            .select("*")
            .eq("id", auth_user.id)
            .single()
            .execute()
        )

        if not profile_response.data:
            return None

        profile = profile_response.data

        return SupabaseUser(
            id=auth_user.id,
            email=auth_user.email or "",
            username=profile.get("username", ""),
            is_admin=profile.get("is_admin", False),
            theme_preference=profile.get("theme_preference", "system"),
        )
    except Exception as e:
        logger.warning(f"Auth error: {e}")
        return None


async def require_user(
    user: SupabaseUser | None = Depends(get_current_user),
) -> SupabaseUser:
    """Require an authenticated user, raise 401 if not authenticated.

    Args:
        user: The current user from get_current_user.

    Returns:
        The authenticated SupabaseUser.

    Raises:
        HTTPException: 401 if user is not authenticated.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(
    user: SupabaseUser = Depends(require_user),
) -> SupabaseUser:
    """Require an admin user.

    Args:
        user: The current authenticated user.

    Returns:
        The authenticated admin SupabaseUser.

    Raises:
        HTTPException: 403 if user is not an admin.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def validate_device_ownership(user_id: str, device_id: str) -> bool:
    """Validate that a user owns a specific device.

    This function checks the database to ensure the device
    belongs to the specified user.

    Args:
        user_id: The user's UUID.
        device_id: The device ID (8 hex characters).

    Returns:
        True if the user owns the device, False otherwise.
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("devices")
            .select("id")
            .eq("id", device_id)
            .eq("user_id", user_id)
            .execute()
        )

        return bool(response.data)
    except Exception as e:
        logger.error(f"Device ownership check failed: {e}")
        return False


async def get_user_and_device_from_api_key(
    device_id: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> tuple[SupabaseUser | None, dict | None]:
    """Get user and device from API key (for API routes).

    This function authenticates API requests using either:
    1. User API token (from api_tokens table)
    2. Device-specific API key (from devices table)

    Args:
        device_id: Optional device ID from the route path.
        credentials: HTTP authorization credentials (Bearer token).

    Returns:
        Tuple of (SupabaseUser, device_dict) if authenticated.

    Raises:
        HTTPException: 401 if authentication fails.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )

    api_key = credentials.credentials
    supabase = get_supabase_admin_client()  # Use admin client to bypass RLS

    try:
        # First, try to find user by API token
        token_response = (
            supabase.table("api_tokens")
            .select("user_id")
            .eq("token", api_key)
            .execute()
        )

        if token_response.data:
            user_id = token_response.data[0]["user_id"]

            # Update last_used_at with current timestamp
            from datetime import datetime, timezone

            supabase.table("api_tokens").update(
                {"last_used_at": datetime.now(timezone.utc).isoformat()}
            ).eq("token", api_key).execute()

            # Get user profile
            profile_response = (
                supabase.table("user_profiles")
                .select("*")
                .eq("id", user_id)
                .single()
                .execute()
            )

            if profile_response.data:
                user = SupabaseUser(
                    id=user_id,
                    email=profile_response.data.get("email", ""),
                    username=profile_response.data.get("username", ""),
                    is_admin=profile_response.data.get("is_admin", False),
                )

                # Get device if device_id provided
                device = None
                if device_id:
                    device_response = (
                        supabase.table("devices")
                        .select("*")
                        .eq("id", device_id)
                        .eq("user_id", user_id)
                        .execute()
                    )

                    if device_response.data:
                        device = device_response.data[0]

                return user, device

        # Second, try device-specific API key
        if device_id:
            device_response = (
                supabase.table("devices")
                .select("*, user_profiles!inner(*)")
                .eq("id", device_id)
                .eq("api_key", api_key)
                .execute()
            )

            if device_response.data:
                device_data = device_response.data[0]
                profile = device_data.pop("user_profiles")

                user = SupabaseUser(
                    id=profile["id"],
                    email=profile.get("email", ""),
                    username=profile.get("username", ""),
                    is_admin=profile.get("is_admin", False),
                )

                return user, device_data

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API key auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )
