"""Supabase authentication router.

This router provides authentication endpoints for Supabase multi-tenant mode.
It handles login, signup, logout, and device claiming.

These routes are only active when AUTH_MODE=supabase.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from tronbyt_server.config import Settings, get_settings
from tronbyt_server.device_claim import claim_device, generate_pairing_token
from tronbyt_server.supabase_auth import (
    SupabaseUser,
    get_current_user,
    require_user,
)
from tronbyt_server.supabase_client import get_supabase_client, is_supabase_enabled
from tronbyt_server.supabase_db import create_api_token, get_user_api_tokens

router = APIRouter(prefix="/auth/supabase", tags=["supabase-auth"])
logger = logging.getLogger(__name__)


class SignupRequest(BaseModel):
    """Request body for user signup."""

    email: str
    password: str
    username: str


class LoginRequest(BaseModel):
    """Request body for user login."""

    email: str
    password: str


class ClaimDeviceRequest(BaseModel):
    """Request body for device claiming."""

    pairing_token: str


class GeneratePairingTokenRequest(BaseModel):
    """Request body for generating a pairing token."""

    device_id: str


@router.post("/signup")
async def signup(
    request: SignupRequest,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Sign up a new user with Supabase Auth.

    Args:
        request: The signup request with email, password, and username.
        settings: Application settings.

    Returns:
        JSONResponse with success status or error message.
    """
    if not is_supabase_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supabase authentication is not enabled",
        )

    if settings.ENABLE_USER_REGISTRATION != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User registration is disabled",
        )

    supabase = get_supabase_client()

    try:
        # Sign up with Supabase Auth
        response = supabase.auth.sign_up(
            {
                "email": request.email,
                "password": request.password,
                "options": {
                    "data": {
                        "username": request.username,
                    }
                },
            }
        )

        if response.user:
            logger.info(f"User signed up: {request.email}")
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={
                    "success": True,
                    "message": "User created successfully. Please check your email for verification.",
                    "user_id": response.user.id,
                },
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Failed to create user",
                },
            )
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login")
async def login(request: LoginRequest) -> JSONResponse:
    """Log in a user with Supabase Auth.

    Args:
        request: The login request with email and password.

    Returns:
        JSONResponse with session tokens or error message.
    """
    if not is_supabase_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supabase authentication is not enabled",
        )

    supabase = get_supabase_client()

    try:
        response = supabase.auth.sign_in_with_password(
            {
                "email": request.email,
                "password": request.password,
            }
        )

        if response.session:
            logger.info(f"User logged in: {request.email}")

            # Create response with session cookie
            json_response = JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "expires_in": response.session.expires_in,
                },
            )

            # Set the access token as a cookie for web clients
            json_response.set_cookie(
                key="sb-access-token",
                value=response.session.access_token,
                max_age=response.session.expires_in,
                httponly=True,
                samesite="lax",
            )

            return json_response
        else:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "success": False,
                    "message": "Invalid credentials",
                },
            )
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )


@router.post("/logout")
async def logout(
    user: SupabaseUser | None = Depends(get_current_user),
) -> Response:
    """Log out the current user.

    Args:
        user: The current authenticated user.

    Returns:
        Response with cleared session cookie.
    """
    if not is_supabase_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supabase authentication is not enabled",
        )

    if user:
        supabase = get_supabase_client()
        try:
            supabase.auth.sign_out()
            logger.info(f"User logged out: {user.email}")
        except Exception as e:
            logger.warning(f"Logout error: {e}")

    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("sb-access-token")
    return response


@router.get("/me")
async def get_me(
    user: SupabaseUser = Depends(require_user),
) -> JSONResponse:
    """Get the current authenticated user's profile.

    Args:
        user: The current authenticated user.

    Returns:
        JSONResponse with user profile information.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "is_admin": user.is_admin,
            "theme_preference": user.theme_preference,
        },
    )


@router.post("/claim-device")
async def claim_device_endpoint(
    request: ClaimDeviceRequest,
    user: SupabaseUser = Depends(require_user),
) -> JSONResponse:
    """Claim a device using a pairing token.

    Args:
        request: The claim request with pairing token.
        user: The current authenticated user.

    Returns:
        JSONResponse with claim result.
    """
    if not is_supabase_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supabase authentication is not enabled",
        )

    result = claim_device(user.id, request.pairing_token)

    if result.success:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "device_id": result.device_id,
                "message": result.message,
            },
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": result.message,
            },
        )


@router.post("/generate-pairing-token")
async def generate_pairing_token_endpoint(
    request: GeneratePairingTokenRequest,
) -> JSONResponse:
    """Generate a pairing token for a device.

    This endpoint is called by the firmware during device setup.
    It does not require authentication (firmware calls this directly).

    Args:
        request: The request with device ID.

    Returns:
        JSONResponse with pairing token and expiration.
    """
    if not is_supabase_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supabase authentication is not enabled",
        )

    token = generate_pairing_token(request.device_id)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "device_id": token.device_id,
            "token": token.token,
            "expires_at": token.expires_at.isoformat(),
        },
    )


@router.post("/generate-api-key")
async def generate_api_key_endpoint(
    user: SupabaseUser = Depends(require_user),
    name: Annotated[str, Form()] = "Default",
) -> JSONResponse:
    """Generate a new API key for the current user.

    Args:
        user: The current authenticated user.
        name: A friendly name for the API key.

    Returns:
        JSONResponse with the new API key.
    """
    if not is_supabase_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supabase authentication is not enabled",
        )

    token = create_api_token(user.id, name)

    if token:
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "success": True,
                "token": token["token"],
                "name": token["name"],
                "created_at": token["created_at"],
            },
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API key",
        )


@router.get("/api-keys")
async def list_api_keys(
    user: SupabaseUser = Depends(require_user),
) -> JSONResponse:
    """List all API keys for the current user.

    Args:
        user: The current authenticated user.

    Returns:
        JSONResponse with list of API keys (tokens are masked).
    """
    if not is_supabase_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supabase authentication is not enabled",
        )

    tokens = get_user_api_tokens(user.id)

    # Mask the token values for security
    masked_tokens = []
    for t in tokens:
        masked_tokens.append(
            {
                "id": t["id"],
                "name": t["name"],
                "token_preview": t["token"][:8] + "..." if t["token"] else "",
                "created_at": t["created_at"],
                "last_used_at": t["last_used_at"],
            }
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"api_keys": masked_tokens},
    )
