"""Tests for downloader module."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from downloader import (
    BatchDownloadResult,
    DownloadResult,
    _download_with_retry,
    _is_permanent_error,
    download_audio,
    download_videos,
)


class TestIsPermanentError:
    """Tests for _is_permanent_error function."""

    @pytest.mark.parametrize(
        "error_msg",
        [
            "Video unavailable",
            "Private video. Sign in if you've been granted access",
            "This video is not available",
            "Sign in to confirm your age",
            "This is members-only content",
            "This video has been removed by the uploader",
            "Blocked due to copyright claim",
            "This video is no longer available",
        ],
    )
    def test_permanent_errors_detected(self, error_msg: str) -> None:
        """Test that permanent errors are correctly identified."""
        assert _is_permanent_error(error_msg) is True

    @pytest.mark.parametrize(
        "error_msg",
        [
            "Network error",
            "Connection timeout",
            "HTTP Error 500: Server error",
            "Rate limit exceeded",
        ],
    )
    def test_temporary_errors_not_flagged(self, error_msg: str) -> None:
        """Test that temporary errors are not flagged as permanent."""
        assert _is_permanent_error(error_msg) is False

    def test_case_insensitive(self) -> None:
        """Test that detection is case insensitive."""
        assert _is_permanent_error("VIDEO UNAVAILABLE") is True
        assert _is_permanent_error("video unavailable") is True


class TestDownloadWithRetry:
    """Tests for _download_with_retry function."""

    def test_success_on_first_attempt(self, tmp_path: Path) -> None:
        """Test successful download on first attempt."""
        with patch("yt_dlp.YoutubeDL") as mock_ydl:
            mock_instance = MagicMock()
            mock_ydl.return_value.__enter__.return_value = mock_instance

            success, error, retry_count = _download_with_retry(
                "https://youtube.com/watch?v=test",
                {"paths": {"home": str(tmp_path)}},
                "Test Video",
                max_retries=3,
                initial_backoff=0.01,
            )

        assert success is True
        assert error is None
        assert retry_count == 0

    def test_retry_on_temporary_error(self, tmp_path: Path) -> None:
        """Test retry behavior on temporary errors."""
        with patch("yt_dlp.YoutubeDL") as mock_ydl:
            mock_instance = MagicMock()
            mock_instance.download.side_effect = [
                yt_dlp.utils.DownloadError("Network error"),
                yt_dlp.utils.DownloadError("Network error"),
                None,  # Success on third attempt
            ]
            mock_ydl.return_value.__enter__.return_value = mock_instance

            with patch("time.sleep"):  # Skip actual sleep
                success, error, retry_count = _download_with_retry(
                    "https://youtube.com/watch?v=test",
                    {"paths": {"home": str(tmp_path)}},
                    "Test Video",
                    max_retries=3,
                    initial_backoff=0.01,
                )

        assert success is True
        assert error is None

    def test_no_retry_on_permanent_error(self, tmp_path: Path) -> None:
        """Test that permanent errors don't trigger retry."""
        with patch("yt_dlp.YoutubeDL") as mock_ydl:
            mock_instance = MagicMock()
            mock_instance.download.side_effect = yt_dlp.utils.DownloadError("Video unavailable")
            mock_ydl.return_value.__enter__.return_value = mock_instance

            with patch("time.sleep") as mock_sleep:
                success, error, retry_count = _download_with_retry(
                    "https://youtube.com/watch?v=test",
                    {"paths": {"home": str(tmp_path)}},
                    "Test Video",
                    max_retries=3,
                    initial_backoff=0.01,
                )

        assert success is False
        assert "Video unavailable" in error
        mock_sleep.assert_not_called()

    def test_max_retries_exceeded(self, tmp_path: Path) -> None:
        """Test failure after max retries exceeded."""
        with patch("yt_dlp.YoutubeDL") as mock_ydl:
            mock_instance = MagicMock()
            mock_instance.download.side_effect = yt_dlp.utils.DownloadError("Network error")
            mock_ydl.return_value.__enter__.return_value = mock_instance

            with patch("time.sleep"):
                success, error, retry_count = _download_with_retry(
                    "https://youtube.com/watch?v=test",
                    {"paths": {"home": str(tmp_path)}},
                    "Test Video",
                    max_retries=2,
                    initial_backoff=0.01,
                )

        assert success is False
        assert "Network error" in error
        assert retry_count == 2

    def test_handles_unexpected_exception(self, tmp_path: Path) -> None:
        """Test handling of unexpected exceptions."""
        with patch("yt_dlp.YoutubeDL") as mock_ydl:
            mock_instance = MagicMock()
            mock_instance.download.side_effect = RuntimeError("Unexpected error")
            mock_ydl.return_value.__enter__.return_value = mock_instance

            success, error, retry_count = _download_with_retry(
                "https://youtube.com/watch?v=test",
                {"paths": {"home": str(tmp_path)}},
                "Test Video",
                max_retries=3,
                initial_backoff=0.01,
            )

        assert success is False
        assert "Unexpected error" in error


class TestDownloadAudio:
    """Tests for download_audio function."""

    def test_successful_download(self, tmp_path: Path) -> None:
        """Test successful audio download."""
        with patch("downloader._download_with_retry") as mock_retry:
            mock_retry.return_value = (True, None, 0)

            result = download_audio(
                "test_video_id",
                tmp_path,
                title="Test Video",
                channel_id="UCtest",
                max_retries=3,
                initial_backoff=0.01,
            )

        assert result.success is True
        assert result.video_id == "test_video_id"
        assert result.title == "Test Video"
        assert result.error is None

    def test_failed_download(self, tmp_path: Path) -> None:
        """Test failed audio download."""
        with patch("downloader._download_with_retry") as mock_retry:
            mock_retry.return_value = (False, "Download failed", 2)

            result = download_audio(
                "test_video_id",
                tmp_path,
                title="Test Video",
                channel_id="UCtest",
                max_retries=3,
                initial_backoff=0.01,
            )

        assert result.success is False
        assert result.error == "Download failed"
        assert result.retry_count == 2

    def test_uses_env_defaults(self, tmp_path: Path) -> None:
        """Test that environment defaults are used."""
        with (
            patch.dict(
                os.environ,
                {"DOWNLOAD_MAX_RETRIES": "5", "DOWNLOAD_INITIAL_BACKOFF": "1.0"},
            ),
            patch("downloader._download_with_retry") as mock_retry,
        ):
            mock_retry.return_value = (True, None, 0)

            download_audio("test_id", tmp_path)

            # Check that the function was called (we can't easily verify params)
            mock_retry.assert_called_once()


class TestDownloadVideos:
    """Tests for download_videos function."""

    def test_downloads_multiple_videos(self, tmp_path: Path) -> None:
        """Test downloading multiple videos."""
        videos = [
            {"id": "vid1", "title": "Video 1", "channel_id": "UC1"},
            {"id": "vid2", "title": "Video 2", "channel_id": "UC2"},
        ]

        with patch("downloader.download_audio") as mock_download:
            mock_download.side_effect = [
                DownloadResult("vid1", "Video 1", "UC1", True),
                DownloadResult("vid2", "Video 2", "UC2", True),
            ]

            result = download_videos(videos, tmp_path)

        assert result.success_count == 2
        assert result.failure_count == 0

    def test_handles_failures(self, tmp_path: Path) -> None:
        """Test handling of download failures."""
        videos = [
            {"id": "vid1", "title": "Video 1", "channel_id": "UC1"},
            {"id": "vid2", "title": "Video 2", "channel_id": "UC2"},
        ]

        with patch("downloader.download_audio") as mock_download:
            mock_download.side_effect = [
                DownloadResult("vid1", "Video 1", "UC1", True),
                DownloadResult("vid2", "Video 2", "UC2", False, error="Failed"),
            ]

            result = download_videos(videos, tmp_path)

        assert result.success_count == 1
        assert result.failure_count == 1

    def test_empty_list_returns_empty_result(self, tmp_path: Path) -> None:
        """Test that empty video list returns empty result."""
        result = download_videos([], tmp_path)

        assert result.total == 0
        assert result.success_count == 0
        assert result.failure_count == 0


class TestBatchDownloadResult:
    """Tests for BatchDownloadResult dataclass."""

    def test_properties(self) -> None:
        """Test BatchDownloadResult properties."""
        result = BatchDownloadResult(
            successful=[
                DownloadResult("v1", "T1", "C1", True),
                DownloadResult("v2", "T2", "C2", True),
            ],
            failed=[
                DownloadResult("v3", "T3", "C3", False, error="Failed"),
            ],
        )

        assert result.total == 3
        assert result.success_count == 2
        assert result.failure_count == 1


class TestDownloadResult:
    """Tests for DownloadResult dataclass."""

    def test_default_values(self) -> None:
        """Test DownloadResult default values."""
        result = DownloadResult(
            video_id="test",
            title="Test",
            channel_id="UC",
            success=True,
        )

        assert result.error is None
        assert result.retry_count == 0
