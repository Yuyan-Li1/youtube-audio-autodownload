# -*- coding: utf-8 -*-
"""Configuration module for YouTube audio downloader.

Loads all configuration from environment variables and files in one place at startup.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os

from dotenv import load_dotenv


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
    log_level: str
    log_file: Optional[Path]
    dry_run: bool = False  # If True, use mock data instead of calling YouTube API


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
    if not target_dir.exists():
        raise ConfigError(f"Target directory does not exist: {target_dir}")

    # Optional: Download directory (default: ./downloads/)
    download_dir_str = os.getenv("DOWNLOAD_DIRECTORY", str(base_dir / "downloads"))
    download_dir = Path(download_dir_str).expanduser()
    download_dir.mkdir(parents=True, exist_ok=True)

    # Optional: Lookback days (default: 7)
    lookback_days_str = os.getenv("LOOKBACK_DAYS", "7")
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

    # Optional: Log level (default: INFO)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level not in valid_levels:
        raise ConfigError(f"LOG_LEVEL must be one of {valid_levels}, got: {log_level}")

    # Optional: Log file path (default: None, logs to stderr)
    log_file_str = os.getenv("LOG_FILE")
    log_file = Path(log_file_str).expanduser() if log_file_str else None
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

    return Config(
        api_key=api_key,
        channel_ids=tuple(channel_ids),
        download_dir=download_dir,
        target_dir=target_dir,
        lookback_days=lookback_days,
        history_file=history_file,
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

    # Fall back to legacy API_key file
    legacy_api_file = base_dir / "API_key"
    if legacy_api_file.exists():
        api_key = legacy_api_file.read_text().strip()
        if api_key:
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
