"""Shared pytest fixtures for YouTube audio downloader tests."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for tests."""
    return tmp_path


@pytest.fixture
def sample_video_info() -> dict[str, Any]:
    """Create a sample VideoInfo dictionary."""
    return {
        "id": "test_video_id",
        "title": "Test Video Title",
        "channel_id": "UCtest123456",
        "published_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
    }


@pytest.fixture
def sample_video_list() -> list[dict[str, Any]]:
    """Create a list of sample VideoInfo dictionaries."""
    return [
        {
            "id": "video_1",
            "title": "First Video",
            "channel_id": "UCchannel1",
            "published_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        },
        {
            "id": "video_2",
            "title": "Second Video",
            "channel_id": "UCchannel2",
            "published_at": datetime(2024, 1, 14, 10, 0, 0, tzinfo=UTC),
        },
        {
            "id": "video_3",
            "title": "Third Video",
            "channel_id": "UCchannel1",
            "published_at": datetime(2024, 1, 13, 8, 0, 0, tzinfo=UTC),
        },
    ]


@pytest.fixture
def mock_youtube_client() -> MagicMock:
    """Create a mock YouTube API client."""
    client = MagicMock()
    return client


@pytest.fixture
def sample_env_vars(tmp_path: Path) -> dict[str, str]:
    """Create sample environment variables for config tests."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    return {
        "YOUTUBE_API_KEY": "test_api_key_12345",
        "TARGET_DIRECTORY": str(target_dir),
        "DOWNLOAD_DIRECTORY": str(download_dir),
        "LOOKBACK_DAYS": "7",
        "HISTORY_MAX_AGE_DAYS": "90",
        "LOG_LEVEL": "INFO",
    }


@pytest.fixture
def channel_ids_file(tmp_path: Path) -> Path:
    """Create a sample channel_ids file."""
    channel_file = tmp_path / "channel_ids"
    channel_file.write_text("UCchannel1\nUCchannel2\n# This is a comment\nUCchannel3\n")
    return channel_file


@pytest.fixture
def sample_history_data() -> dict[str, Any]:
    """Create sample history data."""
    return {
        "downloaded_videos": {
            "video_1": {
                "title": "First Video",
                "channel_id": "UCchannel1",
                "downloaded_at": "2024-01-15T12:00:00",
                "published_at": "2024-01-14T10:00:00",
            },
            "video_2": {
                "title": "Second Video",
                "channel_id": "UCchannel2",
                "downloaded_at": "2024-01-14T11:00:00",
                "published_at": "2024-01-13T09:00:00",
            },
        }
    }


@pytest.fixture
def sample_audio_files(tmp_path: Path) -> list[Path]:
    """Create sample audio files in a temporary directory."""
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()

    files = []
    for ext in [".m4a", ".mp3", ".opus"]:
        file = audio_dir / f"test_audio{ext}"
        file.write_text("fake audio content")
        files.append(file)

    return files
