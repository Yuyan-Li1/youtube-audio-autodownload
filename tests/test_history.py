"""Tests for history module."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from history import (
    DownloadHistory,
    VideoRecord,
    cleanup_old_entries,
    create_video_record,
    filter_new_videos,
    load_history,
    save_history,
)


class TestVideoRecord:
    """Tests for VideoRecord dataclass."""

    def test_create_record(self) -> None:
        """Test creating a VideoRecord."""
        record = VideoRecord(
            video_id="test_id",
            title="Test Video",
            channel_id="UCtest",
            downloaded_at="2024-01-15T12:00:00",
            published_at="2024-01-14T10:00:00",
        )

        assert record.video_id == "test_id"
        assert record.title == "Test Video"
        assert record.channel_id == "UCtest"

    def test_record_is_frozen(self) -> None:
        """Test that VideoRecord is immutable."""
        record = VideoRecord(
            video_id="test_id",
            title="Test Video",
            channel_id="UCtest",
            downloaded_at="2024-01-15T12:00:00",
            published_at="2024-01-14T10:00:00",
        )

        with pytest.raises(AttributeError):
            record.video_id = "new_id"  # type: ignore


class TestDownloadHistory:
    """Tests for DownloadHistory class."""

    def test_contains(self) -> None:
        """Test contains method."""
        history = DownloadHistory(downloaded_videos={"vid1": {"title": "Video 1"}})

        assert history.contains("vid1") is True
        assert history.contains("vid2") is False

    def test_get_downloaded_ids(self) -> None:
        """Test get_downloaded_ids method."""
        history = DownloadHistory(downloaded_videos={"vid1": {}, "vid2": {}, "vid3": {}})

        ids = history.get_downloaded_ids()
        assert ids == frozenset({"vid1", "vid2", "vid3"})
        assert isinstance(ids, frozenset)

    def test_add_video(self) -> None:
        """Test add_video method returns new history."""
        history = DownloadHistory(downloaded_videos={})
        record = VideoRecord(
            video_id="new_vid",
            title="New Video",
            channel_id="UCtest",
            downloaded_at="2024-01-15T12:00:00",
            published_at="2024-01-14T10:00:00",
        )

        new_history = history.add_video(record)

        # Original unchanged
        assert "new_vid" not in history.downloaded_videos
        # New history has the video
        assert "new_vid" in new_history.downloaded_videos
        assert new_history.downloaded_videos["new_vid"]["title"] == "New Video"


class TestLoadHistory:
    """Tests for load_history function."""

    def test_load_existing_history(self, tmp_path: Path) -> None:
        """Test loading existing history file."""
        history_file = tmp_path / "history.json"
        history_file.write_text(
            json.dumps(
                {
                    "downloaded_videos": {
                        "vid1": {"title": "Video 1", "channel_id": "UC1"},
                        "vid2": {"title": "Video 2", "channel_id": "UC2"},
                    }
                }
            )
        )

        history = load_history(history_file)

        assert len(history.downloaded_videos) == 2
        assert history.contains("vid1")
        assert history.contains("vid2")

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        """Test loading nonexistent file returns empty history."""
        history_file = tmp_path / "nonexistent.json"

        history = load_history(history_file)

        assert len(history.downloaded_videos) == 0

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        """Test loading corrupted file returns empty history."""
        history_file = tmp_path / "corrupted.json"
        history_file.write_text("not valid json {{{")

        history = load_history(history_file)

        assert len(history.downloaded_videos) == 0

    def test_load_file_with_error(self, tmp_path: Path) -> None:
        """Test handling of read errors."""
        history_file = tmp_path / "history.json"
        history_file.write_text("{}")

        with patch("builtins.open", side_effect=OSError("Read error")):
            history = load_history(history_file)

        assert len(history.downloaded_videos) == 0


class TestSaveHistory:
    """Tests for save_history function."""

    def test_save_history(self, tmp_path: Path) -> None:
        """Test saving history to file."""
        history_file = tmp_path / "history.json"
        history = DownloadHistory(
            downloaded_videos={
                "vid1": {"title": "Video 1", "channel_id": "UC1"},
            }
        )

        result = save_history(history, history_file)

        assert result is True
        assert history_file.exists()

        saved_data = json.loads(history_file.read_text())
        assert "vid1" in saved_data["downloaded_videos"]

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test that save creates parent directories."""
        history_file = tmp_path / "subdir" / "history.json"
        history = DownloadHistory(downloaded_videos={})

        result = save_history(history, history_file)

        assert result is True
        assert history_file.exists()

    def test_save_handles_error(self, tmp_path: Path) -> None:
        """Test handling of write errors."""
        history_file = tmp_path / "history.json"
        history = DownloadHistory(downloaded_videos={})

        with patch("builtins.open", side_effect=OSError("Write error")):
            result = save_history(history, history_file)

        assert result is False

    def test_atomic_write(self, tmp_path: Path) -> None:
        """Test that save uses atomic write pattern."""
        history_file = tmp_path / "history.json"
        history = DownloadHistory(downloaded_videos={"vid1": {}})

        result = save_history(history, history_file)

        assert result is True
        # Temp file should not exist after successful save
        temp_file = history_file.with_suffix(".tmp")
        assert not temp_file.exists()


class TestCreateVideoRecord:
    """Tests for create_video_record function."""

    def test_creates_record_with_datetime(self) -> None:
        """Test creating record with datetime published_at."""
        published = datetime(2024, 1, 14, 10, 0, 0)

        record = create_video_record(
            video_id="test_id",
            title="Test Video",
            channel_id="UCtest",
            published_at=published,
        )

        assert record.video_id == "test_id"
        assert record.title == "Test Video"
        assert record.published_at == "2024-01-14T10:00:00"
        assert record.downloaded_at  # Should have current timestamp

    def test_creates_record_with_string(self) -> None:
        """Test creating record with string published_at."""
        record = create_video_record(
            video_id="test_id",
            title="Test Video",
            channel_id="UCtest",
            published_at="2024-01-14T10:00:00",  # type: ignore
        )

        assert record.published_at == "2024-01-14T10:00:00"


class TestFilterNewVideos:
    """Tests for filter_new_videos function."""

    def test_filters_downloaded_videos(self) -> None:
        """Test filtering out already downloaded videos."""
        videos = [
            {"id": "vid1", "title": "Video 1"},
            {"id": "vid2", "title": "Video 2"},
            {"id": "vid3", "title": "Video 3"},
        ]
        downloaded_ids = frozenset({"vid1", "vid3"})

        result = filter_new_videos(videos, downloaded_ids)

        assert len(result) == 1
        assert result[0]["id"] == "vid2"

    def test_returns_all_if_none_downloaded(self) -> None:
        """Test that all videos returned if none downloaded."""
        videos = [
            {"id": "vid1", "title": "Video 1"},
            {"id": "vid2", "title": "Video 2"},
        ]
        downloaded_ids: frozenset[str] = frozenset()

        result = filter_new_videos(videos, downloaded_ids)

        assert len(result) == 2

    def test_returns_empty_if_all_downloaded(self) -> None:
        """Test that empty list returned if all downloaded."""
        videos = [
            {"id": "vid1", "title": "Video 1"},
            {"id": "vid2", "title": "Video 2"},
        ]
        downloaded_ids = frozenset({"vid1", "vid2"})

        result = filter_new_videos(videos, downloaded_ids)

        assert len(result) == 0


class TestCleanupOldEntries:
    """Tests for cleanup_old_entries function."""

    def test_removes_old_entries(self) -> None:
        """Test removing entries older than max_age_days."""
        old_date = (datetime.now() - timedelta(days=100)).isoformat()
        new_date = (datetime.now() - timedelta(days=10)).isoformat()

        history = DownloadHistory(
            downloaded_videos={
                "old_vid": {"downloaded_at": old_date},
                "new_vid": {"downloaded_at": new_date},
            }
        )

        result = cleanup_old_entries(history, max_age_days=90)

        assert "old_vid" not in result.downloaded_videos
        assert "new_vid" in result.downloaded_videos

    def test_keeps_all_within_age(self) -> None:
        """Test that entries within max age are kept."""
        recent_date = (datetime.now() - timedelta(days=5)).isoformat()

        history = DownloadHistory(
            downloaded_videos={
                "vid1": {"downloaded_at": recent_date},
                "vid2": {"downloaded_at": recent_date},
            }
        )

        result = cleanup_old_entries(history, max_age_days=90)

        assert len(result.downloaded_videos) == 2

    def test_handles_missing_downloaded_at(self) -> None:
        """Test handling of entries without downloaded_at field."""
        history = DownloadHistory(
            downloaded_videos={
                "vid_no_date": {"title": "No Date"},
            }
        )

        result = cleanup_old_entries(history, max_age_days=90)

        # Entry without date should be removed (empty string < cutoff)
        assert "vid_no_date" not in result.downloaded_videos
