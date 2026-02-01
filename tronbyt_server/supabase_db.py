"""Supabase database operations.

This module provides database operations for Supabase multi-tenant mode.
It mirrors the functionality of db.py but uses Supabase PostgreSQL.

Usage:
    from tronbyt_server.supabase_db import get_user_devices, save_device

    devices = get_user_devices(user_id)
    save_device(user_id, device_data)
"""

import logging
import secrets
import string
from typing import Any

from tronbyt_server.supabase_client import (
    get_supabase_admin_client,
    get_supabase_client,
)

logger = logging.getLogger(__name__)


def generate_api_key() -> str:
    """Generate a random API key.

    Returns:
        A 32-character alphanumeric API key.
    """
    return "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(32)
    )


# ============================================
# USER OPERATIONS
# ============================================


def get_user_profile(user_id: str) -> dict[str, Any] | None:
    """Get a user profile by ID.

    Args:
        user_id: The user's UUID.

    Returns:
        User profile dict or None if not found.
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("user_profiles")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Failed to get user profile: {e}")
        return None


def update_user_profile(user_id: str, updates: dict[str, Any]) -> bool:
    """Update a user profile.

    Args:
        user_id: The user's UUID.
        updates: Dictionary of fields to update.

    Returns:
        True if successful, False otherwise.
    """
    supabase = get_supabase_client()

    try:
        supabase.table("user_profiles").update(updates).eq("id", user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to update user profile: {e}")
        return False


# ============================================
# API TOKEN OPERATIONS
# ============================================


def get_user_api_tokens(user_id: str) -> list[dict[str, Any]]:
    """Get all API tokens for a user.

    Args:
        user_id: The user's UUID.

    Returns:
        List of API token records.
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("api_tokens")
            .select("id, name, token, created_at, last_used_at, expires_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get API tokens: {e}")
        return []


def create_api_token(user_id: str, name: str = "Default") -> dict[str, Any] | None:
    """Create a new API token for a user.

    Args:
        user_id: The user's UUID.
        name: A friendly name for the token.

    Returns:
        The created token record or None on failure.
    """
    supabase = get_supabase_client()
    token = generate_api_key()

    try:
        response = (
            supabase.table("api_tokens")
            .insert(
                {
                    "user_id": user_id,
                    "token": token,
                    "name": name,
                }
            )
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Failed to create API token: {e}")
        return None


def delete_api_token(user_id: str, token_id: str) -> bool:
    """Delete an API token.

    Args:
        user_id: The user's UUID (for ownership verification).
        token_id: The token's UUID.

    Returns:
        True if successful, False otherwise.
    """
    supabase = get_supabase_client()

    try:
        supabase.table("api_tokens").delete().eq("id", token_id).eq(
            "user_id", user_id
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to delete API token: {e}")
        return False


# ============================================
# DEVICE OPERATIONS
# ============================================


def get_user_devices(user_id: str) -> list[dict[str, Any]]:
    """Get all devices for a user.

    Args:
        user_id: The user's UUID.

    Returns:
        List of device records.
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("devices")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get devices: {e}")
        return []


def get_device(user_id: str, device_id: str) -> dict[str, Any] | None:
    """Get a specific device.

    Args:
        user_id: The user's UUID.
        device_id: The device ID.

    Returns:
        Device record or None if not found.
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("devices")
            .select("*")
            .eq("id", device_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Failed to get device: {e}")
        return None


def save_device(user_id: str, device_data: dict[str, Any]) -> bool:
    """Save or update a device.

    Args:
        user_id: The user's UUID.
        device_data: The device data to save.

    Returns:
        True if successful, False otherwise.
    """
    supabase = get_supabase_client()

    try:
        # Ensure user_id is set
        device_data["user_id"] = user_id

        supabase.table("devices").upsert(device_data).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save device: {e}")
        return False


def delete_device(user_id: str, device_id: str) -> bool:
    """Delete a device.

    Args:
        user_id: The user's UUID (for ownership verification).
        device_id: The device ID.

    Returns:
        True if successful, False otherwise.
    """
    supabase = get_supabase_client()

    try:
        supabase.table("devices").delete().eq("id", device_id).eq(
            "user_id", user_id
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to delete device: {e}")
        return False


# ============================================
# APP INSTALLATION OPERATIONS
# ============================================


def get_device_apps(user_id: str, device_id: str) -> list[dict[str, Any]]:
    """Get all app installations for a device.

    Args:
        user_id: The user's UUID.
        device_id: The device ID.

    Returns:
        List of app installation records.
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("app_installations")
            .select("*")
            .eq("device_id", device_id)
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get device apps: {e}")
        return []


def get_app_installation(
    user_id: str, device_id: str, iname: str
) -> dict[str, Any] | None:
    """Get a specific app installation.

    Args:
        user_id: The user's UUID.
        device_id: The device ID.
        iname: The installation name.

    Returns:
        App installation record or None if not found.
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("app_installations")
            .select("*")
            .eq("device_id", device_id)
            .eq("user_id", user_id)
            .eq("iname", iname)
            .single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Failed to get app installation: {e}")
        return None


def save_app_installation(
    user_id: str, device_id: str, app_data: dict[str, Any]
) -> bool:
    """Save or update an app installation.

    Args:
        user_id: The user's UUID.
        device_id: The device ID.
        app_data: The app installation data to save.

    Returns:
        True if successful, False otherwise.
    """
    supabase = get_supabase_client()

    try:
        # Ensure user_id and device_id are set
        app_data["user_id"] = user_id
        app_data["device_id"] = device_id

        supabase.table("app_installations").upsert(
            app_data, on_conflict="device_id,iname"
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save app installation: {e}")
        return False


def delete_app_installation(user_id: str, device_id: str, iname: str) -> bool:
    """Delete an app installation.

    Args:
        user_id: The user's UUID.
        device_id: The device ID.
        iname: The installation name.

    Returns:
        True if successful, False otherwise.
    """
    supabase = get_supabase_client()

    try:
        supabase.table("app_installations").delete().eq("device_id", device_id).eq(
            "user_id", user_id
        ).eq("iname", iname).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to delete app installation: {e}")
        return False


# ============================================
# ADMIN OPERATIONS (require service role key)
# ============================================


def get_user_by_api_key(api_key: str) -> dict[str, Any] | None:
    """Get a user by their API key (admin operation).

    Args:
        api_key: The API token.

    Returns:
        User profile dict or None if not found.
    """
    supabase = get_supabase_admin_client()

    try:
        # Find the token
        token_response = (
            supabase.table("api_tokens")
            .select("user_id")
            .eq("token", api_key)
            .single()
            .execute()
        )

        if not token_response.data:
            return None

        user_id = token_response.data["user_id"]

        # Get user profile
        profile_response = (
            supabase.table("user_profiles")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )

        return profile_response.data
    except Exception as e:
        logger.error(f"Failed to get user by API key: {e}")
        return None


def get_device_by_api_key(
    device_id: str, api_key: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Get a device and its owner by device API key (admin operation).

    Args:
        device_id: The device ID.
        api_key: The device-specific API key.

    Returns:
        Tuple of (device_dict, user_profile_dict) or (None, None).
    """
    supabase = get_supabase_admin_client()

    try:
        response = (
            supabase.table("devices")
            .select("*, user_profiles!inner(*)")
            .eq("id", device_id)
            .eq("api_key", api_key)
            .single()
            .execute()
        )

        if not response.data:
            return None, None

        device_data = response.data
        user_profile = device_data.pop("user_profiles", None)

        return device_data, user_profile
    except Exception as e:
        logger.error(f"Failed to get device by API key: {e}")
        return None, None
