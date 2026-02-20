"""Tests for config module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from config import (
    VALID_SPONSORBLOCK_CATEGORIES,
    Config,
    ConfigError,
    _get_api_key,
    _load_channel_ids,
    _parse_audio_extensions,
    _validate_path_safety,
    load_config,
)


class TestValidatePathSafety:
    """Tests for _validate_path_safety function."""

    def test_valid_absolute_path(self, tmp_path: Path) -> None:
        """Test that valid absolute paths pass validation."""
        test_path = tmp_path / "valid_dir"
        _validate_path_safety(test_path, "test_path")  # Should not raise

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Test that path traversal patterns are rejected."""
        test_path = tmp_path / ".." / "escaped"
        with pytest.raises(ConfigError, match="path traversal"):
            _validate_path_safety(test_path, "test_path")


class TestParseAudioExtensions:
    """Tests for _parse_audio_extensions function."""

    def test_parse_comma_separated(self) -> None:
        """Test parsing comma-separated extensions."""
        result = _parse_audio_extensions(".m4a,.mp3,.opus")
        assert result == frozenset({".m4a", ".mp3", ".opus"})

    def test_adds_leading_dot(self) -> None:
        """Test that leading dots are added if missing."""
        result = _parse_audio_extensions("m4a,mp3")
        assert result == frozenset({".m4a", ".mp3"})

    def test_handles_whitespace(self) -> None:
        """Test that whitespace is handled correctly."""
        result = _parse_audio_extensions(" .m4a , .mp3 , .opus ")
        assert result == frozenset({".m4a", ".mp3", ".opus"})

    def test_lowercases_extensions(self) -> None:
        """Test that extensions are lowercased."""
        result = _parse_audio_extensions(".M4A,.MP3")
        assert result == frozenset({".m4a", ".mp3"})

    def test_empty_string_returns_empty(self) -> None:
        """Test that empty string returns empty frozenset."""
        result = _parse_audio_extensions("")
        assert result == frozenset()


class TestGetApiKey:
    """Tests for _get_api_key function."""

    def test_api_key_from_environment(self, tmp_path: Path) -> None:
        """Test getting API key from environment variable."""
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key_123"}):
            result = _get_api_key(tmp_path)
            assert result == "test_key_123"

    def test_api_key_stripped(self, tmp_path: Path) -> None:
        """Test that API key is stripped of whitespace."""
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "  test_key_123  "}):
            result = _get_api_key(tmp_path)
            assert result == "test_key_123"

    def test_legacy_api_key_file(self, tmp_path: Path) -> None:
        """Test fallback to legacy API_key file."""
        api_file = tmp_path / "API_key"
        api_file.write_text("legacy_key_456")

        with patch.dict(os.environ, {}, clear=True):
            # Remove YOUTUBE_API_KEY if it exists
            os.environ.pop("YOUTUBE_API_KEY", None)
            with pytest.warns(DeprecationWarning):
                result = _get_api_key(tmp_path)
            assert result == "legacy_key_456"

    def test_missing_api_key_raises(self, tmp_path: Path) -> None:
        """Test that missing API key raises ConfigError."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("YOUTUBE_API_KEY", None)
            with pytest.raises(ConfigError, match="API key not found"):
                _get_api_key(tmp_path)


class TestLoadChannelIds:
    """Tests for _load_channel_ids function."""

    def test_load_channel_ids(self, tmp_path: Path) -> None:
        """Test loading channel IDs from file."""
        channel_file = tmp_path / "channel_ids"
        channel_file.write_text("UCchannel1\nUCchannel2\nUCchannel3\n")

        result = _load_channel_ids(tmp_path)
        assert result == ["UCchannel1", "UCchannel2", "UCchannel3"]

    def test_ignores_comments(self, tmp_path: Path) -> None:
        """Test that comments are ignored."""
        channel_file = tmp_path / "channel_ids"
        channel_file.write_text("UCchannel1\n# This is a comment\nUCchannel2\n")

        result = _load_channel_ids(tmp_path)
        assert result == ["UCchannel1", "UCchannel2"]

    def test_ignores_empty_lines(self, tmp_path: Path) -> None:
        """Test that empty lines are ignored."""
        channel_file = tmp_path / "channel_ids"
        channel_file.write_text("UCchannel1\n\n\nUCchannel2\n")

        result = _load_channel_ids(tmp_path)
        assert result == ["UCchannel1", "UCchannel2"]

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Test that missing file raises ConfigError."""
        with pytest.raises(ConfigError, match="channel_ids file not found"):
            _load_channel_ids(tmp_path)

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        """Test that empty file raises ConfigError."""
        channel_file = tmp_path / "channel_ids"
        channel_file.write_text("")

        with pytest.raises(ConfigError, match="channel_ids file is empty"):
            _load_channel_ids(tmp_path)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_success(self, tmp_path: Path) -> None:
        """Test successful config loading."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        with (
            patch.dict(
                os.environ,
                {
                    "TARGET_DIRECTORY": str(target_dir),
                },
            ),
            patch("config._load_channel_ids", return_value=["UCchannel1"]),
            patch("config._get_api_key", return_value="test_key"),
        ):
            config = load_config()

        assert config.api_key == "test_key"
        assert config.channel_ids == ("UCchannel1",)
        assert config.target_dir == target_dir

    def test_missing_target_directory_raises(self) -> None:
        """Test that missing TARGET_DIRECTORY raises ConfigError."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TARGET_DIRECTORY", None)
            with patch("config._get_api_key", return_value="test_key"):  # noqa: SIM117
                with patch("config._load_channel_ids", return_value=["UCchannel1"]):
                    with patch("config.load_dotenv"):  # Prevent loading from .env file
                        with pytest.raises(ConfigError, match="TARGET_DIRECTORY"):
                            load_config()

    def test_invalid_lookback_days_raises(self, tmp_path: Path) -> None:
        """Test that invalid LOOKBACK_DAYS raises ConfigError."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        with (  # noqa: SIM117
            patch.dict(
                os.environ,
                {
                    "TARGET_DIRECTORY": str(target_dir),
                    "LOOKBACK_DAYS": "invalid",
                },
            ),
            patch("config._get_api_key", return_value="test_key"),
            patch("config._load_channel_ids", return_value=["UCchannel1"]),
        ):
            with pytest.raises(ConfigError, match="LOOKBACK_DAYS"):
                load_config()

    def test_negative_lookback_days_raises(self, tmp_path: Path) -> None:
        """Test that negative LOOKBACK_DAYS raises ConfigError."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        with (  # noqa: SIM117
            patch.dict(
                os.environ,
                {
                    "TARGET_DIRECTORY": str(target_dir),
                    "LOOKBACK_DAYS": "-1",
                },
            ),
            patch("config._get_api_key", return_value="test_key"),
            patch("config._load_channel_ids", return_value=["UCchannel1"]),
        ):
            with pytest.raises(ConfigError, match="LOOKBACK_DAYS"):
                load_config()

    def test_invalid_log_level_raises(self, tmp_path: Path) -> None:
        """Test that invalid LOG_LEVEL raises ConfigError."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        with (  # noqa: SIM117
            patch.dict(
                os.environ,
                {
                    "TARGET_DIRECTORY": str(target_dir),
                    "LOG_LEVEL": "INVALID",
                },
            ),
            patch("config._get_api_key", return_value="test_key"),
            patch("config._load_channel_ids", return_value=["UCchannel1"]),
        ):
            with pytest.raises(ConfigError, match="LOG_LEVEL"):
                load_config()

    def test_nonexistent_target_directory_raises(self, tmp_path: Path) -> None:
        """Test that nonexistent target directory raises ConfigError."""
        with (  # noqa: SIM117
            patch.dict(
                os.environ,
                {
                    "TARGET_DIRECTORY": str(tmp_path / "nonexistent"),
                },
            ),
            patch("config._get_api_key", return_value="test_key"),
            patch("config._load_channel_ids", return_value=["UCchannel1"]),
        ):
            with pytest.raises(ConfigError, match="does not exist"):
                load_config()

    def test_dry_run_mode(self, tmp_path: Path) -> None:
        """Test that dry_run flag is set correctly."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        with (
            patch.dict(
                os.environ,
                {
                    "TARGET_DIRECTORY": str(target_dir),
                },
            ),
            patch("config._get_api_key", return_value="test_key"),
            patch("config._load_channel_ids", return_value=["UCchannel1"]),
        ):
            config = load_config(dry_run=True)

        assert config.dry_run is True

    def test_invalid_history_max_age_raises(self, tmp_path: Path) -> None:
        """Test that invalid HISTORY_MAX_AGE_DAYS raises ConfigError."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        with (  # noqa: SIM117
            patch.dict(
                os.environ,
                {
                    "TARGET_DIRECTORY": str(target_dir),
                    "HISTORY_MAX_AGE_DAYS": "invalid",
                },
            ),
            patch("config._get_api_key", return_value="test_key"),
            patch("config._load_channel_ids", return_value=["UCchannel1"]),
        ):
            with pytest.raises(ConfigError, match="HISTORY_MAX_AGE_DAYS"):
                load_config()


class TestConfig:
    """Tests for Config dataclass."""

    def test_config_is_frozen(self, tmp_path: Path) -> None:
        """Test that Config is immutable."""
        config = Config(
            api_key="test_key",
            channel_ids=("UCchannel1",),
            download_dir=tmp_path / "downloads",
            target_dir=tmp_path / "target",
            lookback_days=7,
            history_file=tmp_path / "history.json",
            history_max_age_days=90,
            audio_extensions=frozenset({".m4a"}),
            log_level="INFO",
            log_file=None,
            sponsorblock_enabled=False,
            sponsorblock_categories=(),
            sponsorblock_action="remove",
            dry_run=False,
        )

        with pytest.raises(AttributeError):
            config.api_key = "new_key"  # type: ignore


class TestSponsorBlockConfig:
    """Tests for SponsorBlock configuration."""

    def _load_with_env(self, tmp_path: Path, env_overrides: dict | None = None) -> Config:
        """Helper to load config with patched env and mocks."""
        target_dir = tmp_path / "target"
        target_dir.mkdir(exist_ok=True)

        env = {"TARGET_DIRECTORY": str(target_dir)}
        if env_overrides:
            env.update(env_overrides)

        with (
            patch.dict(os.environ, env),
            patch("config._get_api_key", return_value="test_key"),
            patch("config._load_channel_ids", return_value=["UCchannel1"]),
        ):
            return load_config()

    def test_disabled_by_default(self, tmp_path: Path) -> None:
        """Test that SponsorBlock is disabled by default."""
        config = self._load_with_env(tmp_path)
        assert config.sponsorblock_enabled is False

    def test_enabled_with_defaults(self, tmp_path: Path) -> None:
        """Test enabling SponsorBlock with default categories and action."""
        config = self._load_with_env(tmp_path, {"SPONSORBLOCK_ENABLED": "true"})
        assert config.sponsorblock_enabled is True
        assert "sponsor" in config.sponsorblock_categories
        assert "intro" in config.sponsorblock_categories
        assert "outro" in config.sponsorblock_categories
        assert config.sponsorblock_action == "remove"

    def test_custom_categories(self, tmp_path: Path) -> None:
        """Test custom SponsorBlock categories."""
        config = self._load_with_env(
            tmp_path,
            {
                "SPONSORBLOCK_ENABLED": "true",
                "SPONSORBLOCK_CATEGORIES": "sponsor,outro",
            },
        )
        assert config.sponsorblock_categories == ("sponsor", "outro")

    def test_all_categories_keyword(self, tmp_path: Path) -> None:
        """Test 'all' keyword expands to all valid categories."""
        config = self._load_with_env(
            tmp_path,
            {
                "SPONSORBLOCK_ENABLED": "true",
                "SPONSORBLOCK_CATEGORIES": "all",
            },
        )
        assert set(config.sponsorblock_categories) == VALID_SPONSORBLOCK_CATEGORIES

    def test_mark_action(self, tmp_path: Path) -> None:
        """Test setting action to 'mark'."""
        config = self._load_with_env(
            tmp_path,
            {
                "SPONSORBLOCK_ENABLED": "true",
                "SPONSORBLOCK_ACTION": "mark",
            },
        )
        assert config.sponsorblock_action == "mark"

    def test_invalid_category_raises(self, tmp_path: Path) -> None:
        """Test that invalid categories raise ConfigError."""
        with pytest.raises(ConfigError, match="invalid categories"):
            self._load_with_env(
                tmp_path,
                {"SPONSORBLOCK_CATEGORIES": "sponsor,bogus_category"},
            )

    def test_invalid_action_raises(self, tmp_path: Path) -> None:
        """Test that invalid action raises ConfigError."""
        with pytest.raises(ConfigError, match="SPONSORBLOCK_ACTION"):
            self._load_with_env(
                tmp_path,
                {"SPONSORBLOCK_ACTION": "delete"},
            )
