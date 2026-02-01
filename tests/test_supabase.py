"""Tests for Supabase modules configuration and utilities."""

from unittest.mock import patch, MagicMock

from tronbyt_server.config import Settings, get_settings
from tronbyt_server.supabase_client import is_supabase_enabled, _check_supabase_config


class TestSupabaseConfiguration:
    """Tests for Supabase configuration."""

    def test_default_auth_mode_is_local(self) -> None:
        """Test that default AUTH_MODE is 'local'."""
        settings = Settings()
        assert settings.AUTH_MODE == "local"

    def test_supabase_settings_defaults(self) -> None:
        """Test that Supabase settings have empty defaults."""
        settings = Settings()
        assert settings.SUPABASE_URL == ""
        assert settings.SUPABASE_ANON_KEY == ""
        assert settings.SUPABASE_SERVICE_ROLE_KEY == ""

    def test_rate_limit_defaults(self) -> None:
        """Test rate limiting default values."""
        settings = Settings()
        assert settings.RATE_LIMIT_REQUESTS == 60
        assert settings.RATE_LIMIT_BURST == 10

    @patch.dict(
        "os.environ",
        {
            "AUTH_MODE": "supabase",
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_ANON_KEY": "test-anon-key",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
        },
    )
    def test_supabase_settings_from_env(self) -> None:
        """Test that Supabase settings are read from environment."""
        # Clear the cached settings
        get_settings.cache_clear()
        settings = Settings()
        assert settings.AUTH_MODE == "supabase"
        assert settings.SUPABASE_URL == "https://test.supabase.co"
        assert settings.SUPABASE_ANON_KEY == "test-anon-key"
        assert settings.SUPABASE_SERVICE_ROLE_KEY == "test-service-key"
        # Restore cached settings
        get_settings.cache_clear()


class TestSupabaseClientHelpers:
    """Tests for Supabase client helper functions."""

    @patch("tronbyt_server.supabase_client.get_settings")
    def test_is_supabase_enabled_false_when_local(
        self, mock_get_settings: MagicMock
    ) -> None:
        """Test is_supabase_enabled returns False for local mode."""
        mock_settings = MagicMock()
        mock_settings.AUTH_MODE = "local"
        mock_get_settings.return_value = mock_settings

        assert is_supabase_enabled() is False

    @patch("tronbyt_server.supabase_client.get_settings")
    def test_is_supabase_enabled_true_when_supabase(
        self, mock_get_settings: MagicMock
    ) -> None:
        """Test is_supabase_enabled returns True for supabase mode."""
        mock_settings = MagicMock()
        mock_settings.AUTH_MODE = "supabase"
        mock_get_settings.return_value = mock_settings

        assert is_supabase_enabled() is True

    @patch("tronbyt_server.supabase_client.get_settings")
    def test_check_supabase_config_false_when_missing_url(
        self, mock_get_settings: MagicMock
    ) -> None:
        """Test _check_supabase_config returns False when URL is missing."""
        mock_settings = MagicMock()
        mock_settings.AUTH_MODE = "supabase"
        mock_settings.SUPABASE_URL = ""
        mock_settings.SUPABASE_ANON_KEY = "test-key"
        mock_get_settings.return_value = mock_settings

        assert _check_supabase_config() is False

    @patch("tronbyt_server.supabase_client.get_settings")
    def test_check_supabase_config_false_when_missing_key(
        self, mock_get_settings: MagicMock
    ) -> None:
        """Test _check_supabase_config returns False when anon key is missing."""
        mock_settings = MagicMock()
        mock_settings.AUTH_MODE = "supabase"
        mock_settings.SUPABASE_URL = "https://test.supabase.co"
        mock_settings.SUPABASE_ANON_KEY = ""
        mock_get_settings.return_value = mock_settings

        assert _check_supabase_config() is False

    @patch("tronbyt_server.supabase_client.get_settings")
    def test_check_supabase_config_true_when_configured(
        self, mock_get_settings: MagicMock
    ) -> None:
        """Test _check_supabase_config returns True when properly configured."""
        mock_settings = MagicMock()
        mock_settings.AUTH_MODE = "supabase"
        mock_settings.SUPABASE_URL = "https://test.supabase.co"
        mock_settings.SUPABASE_ANON_KEY = "test-key"
        mock_get_settings.return_value = mock_settings

        assert _check_supabase_config() is True


class TestDeviceClaimValidation:
    """Tests for device claiming validation."""

    def test_validate_device_id_valid(self) -> None:
        """Test validate_device_id with valid ID."""
        from tronbyt_server.device_claim import validate_device_id

        assert validate_device_id("12345678") is True
        assert validate_device_id("ABCDEF12") is True
        assert validate_device_id("abcdef12") is True
        assert validate_device_id("a1b2c3d4") is True

    def test_validate_device_id_invalid_length(self) -> None:
        """Test validate_device_id with invalid length."""
        from tronbyt_server.device_claim import validate_device_id

        assert validate_device_id("1234567") is False  # Too short
        assert validate_device_id("123456789") is False  # Too long
        assert validate_device_id("") is False  # Empty

    def test_validate_device_id_invalid_chars(self) -> None:
        """Test validate_device_id with invalid characters."""
        from tronbyt_server.device_claim import validate_device_id

        assert validate_device_id("1234567g") is False  # 'g' not valid hex
        assert validate_device_id("1234567Z") is False  # 'Z' not valid hex
        assert validate_device_id("12-45678") is False  # Dash not valid
        assert validate_device_id("12 45678") is False  # Space not valid


class TestRateLimitHelpers:
    """Tests for rate limiting helpers."""

    def test_get_rate_limit_key_from_client(self) -> None:
        """Test get_rate_limit_key extracts client IP."""
        from tronbyt_server.rate_limit import get_rate_limit_key
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.client.host = "192.168.1.100"

        key = get_rate_limit_key(mock_request)
        assert key == "192.168.1.100"

    def test_get_rate_limit_key_from_forwarded_for(self) -> None:
        """Test get_rate_limit_key uses X-Forwarded-For header."""
        from tronbyt_server.rate_limit import get_rate_limit_key
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.headers.get.side_effect = (
            lambda key: "10.0.0.1, 192.168.1.1" if key == "X-Forwarded-For" else None
        )

        key = get_rate_limit_key(mock_request)
        assert key == "10.0.0.1"

    def test_get_rate_limit_key_from_real_ip(self) -> None:
        """Test get_rate_limit_key uses X-Real-IP header."""
        from tronbyt_server.rate_limit import get_rate_limit_key
        from unittest.mock import MagicMock

        mock_request = MagicMock()

        def header_getter(key: str) -> str | None:
            if key == "X-Forwarded-For":
                return None
            if key == "X-Real-IP":
                return "203.0.113.50"
            return None

        mock_request.headers.get.side_effect = header_getter

        key = get_rate_limit_key(mock_request)
        assert key == "203.0.113.50"

    def test_get_rate_limit_key_fallback_unknown(self) -> None:
        """Test get_rate_limit_key falls back to 'unknown'."""
        from tronbyt_server.rate_limit import get_rate_limit_key
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.client = None

        key = get_rate_limit_key(mock_request)
        assert key == "unknown"
