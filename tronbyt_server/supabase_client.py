"""Supabase client initialization.

This module provides Supabase client instances for authentication
and database operations in multi-tenant mode.

Usage:
    from tronbyt_server.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    # Use supabase.auth for authentication
    # Use supabase.table() for database operations
"""

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from tronbyt_server.config import get_settings

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


def _check_supabase_config() -> bool:
    """Check if Supabase is properly configured."""
    settings = get_settings()
    return bool(
        settings.AUTH_MODE == "supabase"
        and settings.SUPABASE_URL
        and settings.SUPABASE_ANON_KEY
    )


@lru_cache
def get_supabase_client() -> "Client":
    """Get a Supabase client instance.

    This client uses the anonymous key and is suitable for
    user-authenticated requests.

    Returns:
        Supabase client configured with anon key.

    Raises:
        RuntimeError: If Supabase is not configured.
    """
    settings = get_settings()

    if not _check_supabase_config():
        raise RuntimeError(
            "Supabase is not configured. Set AUTH_MODE=supabase and "
            "provide SUPABASE_URL and SUPABASE_ANON_KEY environment variables."
        )

    # Import here to avoid import errors when supabase is not installed
    from supabase import create_client

    logger.info(f"Initializing Supabase client for {settings.SUPABASE_URL}")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


@lru_cache
def get_supabase_admin_client() -> "Client":
    """Get a Supabase client with service role (admin) permissions.

    This client uses the service role key and bypasses Row Level Security.
    Use with caution and only for server-side operations that require
    elevated privileges.

    Returns:
        Supabase client configured with service role key.

    Raises:
        RuntimeError: If Supabase service role key is not configured.
    """
    settings = get_settings()

    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "Supabase service role key is not configured. "
            "Set SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    if not _check_supabase_config():
        raise RuntimeError(
            "Supabase is not configured. Set AUTH_MODE=supabase and "
            "provide SUPABASE_URL environment variable."
        )

    # Import here to avoid import errors when supabase is not installed
    from supabase import create_client

    logger.info("Initializing Supabase admin client")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def is_supabase_enabled() -> bool:
    """Check if Supabase authentication mode is enabled.

    Returns:
        True if AUTH_MODE is set to 'supabase', False otherwise.
    """
    settings = get_settings()
    return settings.AUTH_MODE == "supabase"
