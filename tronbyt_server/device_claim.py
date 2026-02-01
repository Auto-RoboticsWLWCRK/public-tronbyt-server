"""Device claiming and pairing logic.

This module handles the device claiming flow for multi-tenant mode:
1. Firmware generates a pairing token during device setup
2. User enters the token in the web dashboard
3. Server binds the device to the user permanently

Usage:
    from tronbyt_server.device_claim import claim_device, generate_pairing_token

    # Firmware calls this to generate a token
    token = generate_pairing_token(device_id)

    # User claims the device
    result = claim_device(user_id, pairing_token)
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from pydantic import BaseModel

from tronbyt_server.supabase_client import get_supabase_admin_client

logger = logging.getLogger(__name__)

# Pairing token validity period (minutes)
PAIRING_TOKEN_VALIDITY_MINUTES = 30


class PairingToken(BaseModel):
    """Represents a device pairing token."""

    device_id: str
    token: str
    expires_at: datetime


class ClaimResult(BaseModel):
    """Result of a device claim operation."""

    success: bool
    device_id: str | None = None
    message: str


def generate_pairing_token(device_id: str) -> PairingToken:
    """Generate a time-limited, single-use pairing token for a device.

    This is called by the firmware during initial setup.
    Requires service role key (called from firmware endpoint).

    Args:
        device_id: The device ID (8 hex characters).

    Returns:
        PairingToken with token and expiration time.

    Raises:
        HTTPException: If token generation fails.
    """
    if not validate_device_id(device_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format. Must be 8 hex characters.",
        )

    supabase = get_supabase_admin_client()

    # Generate a secure random token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=PAIRING_TOKEN_VALIDITY_MINUTES
    )

    try:
        # Delete any existing token for this device
        supabase.table("device_pairing_tokens").delete().eq(
            "device_id", device_id
        ).execute()

        # Create new pairing token
        response = (
            supabase.table("device_pairing_tokens")
            .insert(
                {
                    "device_id": device_id,
                    "token": token,
                    "expires_at": expires_at.isoformat(),
                }
            )
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create pairing token",
            )

        logger.info(f"Generated pairing token for device {device_id}")

        return PairingToken(
            device_id=device_id,
            token=token,
            expires_at=expires_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate pairing token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate pairing token",
        )


def claim_device(user_id: str, pairing_token: str) -> ClaimResult:
    """Claim a device using a pairing token.

    This binds the device to the user permanently.
    The pairing token is single-use and time-limited.

    Args:
        user_id: The user's UUID.
        pairing_token: The pairing token from the device.

    Returns:
        ClaimResult indicating success or failure.
    """
    supabase = get_supabase_admin_client()

    try:
        # Find the pairing token
        token_response = (
            supabase.table("device_pairing_tokens")
            .select("*")
            .eq("token", pairing_token)
            .is_("claimed_by", "null")
            .execute()
        )

        if not token_response.data:
            return ClaimResult(
                success=False,
                message="Invalid or expired pairing token",
            )

        token_data = token_response.data[0]
        device_id = token_data["device_id"]
        expires_at_str = token_data["expires_at"]

        # Parse expiration time
        if expires_at_str.endswith("Z"):
            expires_at_str = expires_at_str[:-1] + "+00:00"
        expires_at = datetime.fromisoformat(expires_at_str)

        # Check if token has expired
        if datetime.now(timezone.utc) > expires_at:
            return ClaimResult(
                success=False,
                message="Pairing token has expired",
            )

        # Check if device already exists and is owned by someone else
        existing_device = (
            supabase.table("devices").select("user_id").eq("id", device_id).execute()
        )

        if existing_device.data:
            existing_user_id = existing_device.data[0]["user_id"]
            if existing_user_id != user_id:
                return ClaimResult(
                    success=False,
                    message="Device is already claimed by another user",
                )

        # Create or update the device record
        device_data = {
            "id": device_id,
            "user_id": user_id,
            "name": f"Tronbyt-{device_id[:4]}",
        }

        supabase.table("devices").upsert(device_data).execute()

        # Mark the token as claimed
        supabase.table("device_pairing_tokens").update(
            {
                "claimed_by": user_id,
                "claimed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("token", pairing_token).execute()

        logger.info(f"Device {device_id} claimed by user {user_id}")

        return ClaimResult(
            success=True,
            device_id=device_id,
            message="Device claimed successfully",
        )
    except Exception as e:
        logger.error(f"Failed to claim device: {e}")
        return ClaimResult(
            success=False,
            message=f"Failed to claim device: {str(e)}",
        )


def validate_device_id(device_id: str) -> bool:
    """Validate device ID format (8 hex characters).

    Args:
        device_id: The device ID to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not device_id or len(device_id) != 8:
        return False
    try:
        int(device_id, 16)
        return True
    except ValueError:
        return False


def get_pending_devices(user_id: str) -> list[dict]:
    """Get devices that have unclaimed pairing tokens.

    This is used by the dashboard to show available devices
    for claiming.

    Args:
        user_id: The user's UUID.

    Returns:
        List of pending device information.
    """
    supabase = get_supabase_admin_client()

    try:
        # Get all unclaimed, non-expired tokens
        now = datetime.now(timezone.utc).isoformat()
        response = (
            supabase.table("device_pairing_tokens")
            .select("device_id, created_at, expires_at")
            .is_("claimed_by", "null")
            .gt("expires_at", now)
            .execute()
        )

        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get pending devices: {e}")
        return []
