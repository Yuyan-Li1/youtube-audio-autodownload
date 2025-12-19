# -*- coding: utf-8 -*-
"""Configuration module for YouTube audio downloader.

Loads all configuration from environment variables and files in one place at startup.
"""

import logging
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Default values for configurable options
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_HISTORY_MAX_AGE_DAYS = 90
DEFAULT_AUDIO_EXTENSIONS = ".m4a,.mp3,.opus,.webm,.aac,.ogg,.wav,.flac"


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""

    pass


@dataclass(frozen=True)
class Config:
    """Immutable configuration object for the downloader.

    All file I/O for configuration happens at construction time.
    """

    api_key: str
    channel_ids: tuple[str, ...]  # Using tuple for immutability
    download_dir: Path
    target_dir: Path
    lookback_days: int
    history_file: Path
    history_max_age_days: int
    audio_extensions: frozenset[str]
    log_level: str
    log_file: Optional[Path]
    dry_run: bool = False  # If True, use mock data instead of calling YouTube API


def _validate_path_safety(path: Path, name: str, base_dir: Path | None = None) -> None:
    """Validate a path doesn't escape expected boundaries.

    Args:
        path: The path to validate.
        name: Name of the path for error messages.
        base_dir: Optional base directory to check against.

    Raises:
        ConfigError: If the path is unsafe.
    """
    # Resolve to absolute path
    resolved = path.resolve()

    # Check for suspicious patterns
    path_str = str(path)
    if ".." in path_str:
        raise ConfigError(
            f"{name} contains path traversal pattern '..': {path}"
        )

    # If base_dir is provided, ensure path is within it
    if base_dir is not None:
        base_resolved = base_dir.resolve()
        try:
            resolved.relative_to(base_resolved)
        except ValueError:
            # Path is not relative to base - that's OK for some paths
            pass


def _parse_audio_extensions(extensions_str: str) -> frozenset[str]:
    """Parse comma-separated audio extensions string.

    Args:
        extensions_str: Comma-separated list of extensions (e.g., ".m4a,.mp3").

    Returns:
        Frozenset of lowercase extensions with leading dots.
    """
    extensions = set()
    for ext in extensions_str.split(","):
        ext = ext.strip().lower()
        if ext:
            # Ensure extension starts with a dot
            if not ext.startswith("."):
                ext = "." + ext
            extensions.add(ext)
    return frozenset(extensions)


def load_config(env_file: Optional[Path] = None, dry_run: bool = False) -> Config:
    """Load all configuration from environment and files.

    Args:
        env_file: Optional path to .env file. Defaults to .env in script directory.
        dry_run: If True, use mock data instead of calling YouTube API.

    Returns:
        Immutable Config object with all settings.

    Raises:
        ConfigError: If required configuration is missing or invalid.
    """
    # Determine base directory (where the script lives)
    base_dir = Path(__file__).parent.resolve()

    # Load environment variables from .env file
    env_path = env_file or base_dir / ".env"
    load_dotenv(env_path)

    # Required: API key
    api_key = _get_api_key(base_dir)

    # Required: Channel IDs
    channel_ids = _load_channel_ids(base_dir)

    # Required: Target directory (where to move completed downloads)
    target_dir_str = os.getenv("TARGET_DIRECTORY")
    if not target_dir_str:
        raise ConfigError(
            "TARGET_DIRECTORY environment variable is required. "
            "Set it in .env file or environment."
        )
    target_dir = Path(target_dir_str).expanduser()
    _validate_path_safety(target_dir, "TARGET_DIRECTORY")
    if not target_dir.exists():
        raise ConfigError(f"Target directory does not exist: {target_dir}")

    # Optional: Download directory (default: ./downloads/)
    download_dir_str = os.getenv("DOWNLOAD_DIRECTORY", str(base_dir / "downloads"))
    download_dir = Path(download_dir_str).expanduser()
    _validate_path_safety(download_dir, "DOWNLOAD_DIRECTORY")
    download_dir.mkdir(parents=True, exist_ok=True)

    # Optional: Lookback days (default: 7)
    lookback_days_str = os.getenv("LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS))
    try:
        lookback_days = int(lookback_days_str)
        if lookback_days < 1:
            raise ValueError("Must be positive")
    except ValueError:
        raise ConfigError(
            f"LOOKBACK_DAYS must be a positive integer, got: {lookback_days_str}"
        )

    # Optional: History file path (default: ./download_history.json)
    history_file_str = os.getenv(
        "HISTORY_FILE", str(base_dir / "download_history.json")
    )
    history_file = Path(history_file_str).expanduser()
    _validate_path_safety(history_file, "HISTORY_FILE")

    # Optional: History max age in days (default: 90)
    history_max_age_str = os.getenv(
        "HISTORY_MAX_AGE_DAYS", str(DEFAULT_HISTORY_MAX_AGE_DAYS)
    )
    try:
        history_max_age_days = int(history_max_age_str)
        if history_max_age_days < 1:
            raise ValueError("Must be positive")
    except ValueError:
        raise ConfigError(
            f"HISTORY_MAX_AGE_DAYS must be a positive integer, got: {history_max_age_str}"
        )

    # Optional: Audio extensions (default: common audio formats including flac)
    audio_extensions_str = os.getenv("AUDIO_EXTENSIONS", DEFAULT_AUDIO_EXTENSIONS)
    audio_extensions = _parse_audio_extensions(audio_extensions_str)

    # Optional: Log level (default: INFO)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level not in valid_levels:
        raise ConfigError(f"LOG_LEVEL must be one of {valid_levels}, got: {log_level}")

    # Optional: Log file path (default: None, logs to stderr)
    log_file_str = os.getenv("LOG_FILE")
    log_file = Path(log_file_str).expanduser() if log_file_str else None
    if log_file:
        _validate_path_safety(log_file, "LOG_FILE")
        log_file.parent.mkdir(parents=True, exist_ok=True)

    return Config(
        api_key=api_key,
        channel_ids=tuple(channel_ids),
        download_dir=download_dir,
        target_dir=target_dir,
        lookback_days=lookback_days,
        history_file=history_file,
        history_max_age_days=history_max_age_days,
        audio_extensions=audio_extensions,
        log_level=log_level,
        log_file=log_file,
        dry_run=dry_run,
    )


def _get_api_key(base_dir: Path) -> str:
    """Get API key from environment or legacy file.

    Checks YOUTUBE_API_KEY env var first, falls back to API_key file for backwards compatibility.
    """
    # Try environment variable first
    api_key = os.getenv("YOUTUBE_API_KEY")
    if api_key:
        return api_key.strip()

    # Fall back to legacy API_key file with deprecation warning
    legacy_api_file = base_dir / "API_key"
    if legacy_api_file.exists():
        api_key = legacy_api_file.read_text().strip()
        if api_key:
            warnings.warn(
                "Using legacy API_key file is deprecated. "
                "Please set YOUTUBE_API_KEY in your .env file instead. "
                "The API_key file will be removed in a future version.",
                DeprecationWarning,
                stacklevel=2,
            )
            logger.warning(
                "DEPRECATION: Using legacy API_key file. "
                "Please migrate to YOUTUBE_API_KEY environment variable."
            )
            return api_key

    raise ConfigError(
        "YouTube API key not found. Set YOUTUBE_API_KEY in .env file or environment, "
        "or create an API_key file."
    )


def _load_channel_ids(base_dir: Path) -> list[str]:
    """Load channel IDs from the channel_ids file.

    Returns:
        List of channel ID strings.

    Raises:
        ConfigError: If file doesn't exist or is empty.
    """
    channel_file = base_dir / "channel_ids"

    if not channel_file.exists():
        raise ConfigError(
            f"channel_ids file not found at {channel_file}. "
            "Create this file with one YouTube channel ID per line."
        )

    channel_ids = [
        line.strip()
        for line in channel_file.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not channel_ids:
        raise ConfigError("channel_ids file is empty. Add at least one channel ID.")

    return channel_ids
