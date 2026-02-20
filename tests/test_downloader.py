"""Tests for downloader module."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from downloader import (
    BatchDownloadResult,
    DownloadResult,
    _build_sponsorblock_postprocessors,
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
            mock_instance.extract_info.return_value = {"title": "Test"}
            mock_instance.prepare_filename.return_value = str(tmp_path / "test.m4a")
            mock_ydl.return_value.__enter__.return_value = mock_instance

            success, error, retry_count, file_path, info_dict = _download_with_retry(
                "https://youtube.com/watch?v=test",
                {"paths": {"home": str(tmp_path)}},
                "Test Video",
                max_retries=3,
                initial_backoff=0.01,
            )

        assert success is True
        assert error is None
        assert retry_count == 0
        assert info_dict == {"title": "Test"}

    def test_retry_on_temporary_error(self, tmp_path: Path) -> None:
        """Test retry behavior on temporary errors."""
        with patch("yt_dlp.YoutubeDL") as mock_ydl:
            mock_instance = MagicMock()
            mock_instance.extract_info.side_effect = [
                yt_dlp.utils.DownloadError("Network error"),
                yt_dlp.utils.DownloadError("Network error"),
                {"title": "Test"},  # Success on third attempt
            ]
            mock_instance.prepare_filename.return_value = str(tmp_path / "test.m4a")
            mock_ydl.return_value.__enter__.return_value = mock_instance

            with patch("time.sleep"):  # Skip actual sleep
                success, error, retry_count, file_path, info_dict = _download_with_retry(
                    "https://youtube.com/watch?v=test",
                    {"paths": {"home": str(tmp_path)}},
                    "Test Video",
                    max_retries=3,
                    initial_backoff=0.01,
                )

        assert success is True
        assert error is None
        assert retry_count == 1
        assert info_dict == {"title": "Test"}

    def test_no_retry_on_permanent_error(self, tmp_path: Path) -> None:
        """Test that permanent errors don't trigger retry."""
        with patch("yt_dlp.YoutubeDL") as mock_ydl:
            mock_instance = MagicMock()
            mock_instance.extract_info.side_effect = yt_dlp.utils.DownloadError("Video unavailable")
            mock_ydl.return_value.__enter__.return_value = mock_instance

            with patch("time.sleep") as mock_sleep:
                success, error, retry_count, file_path, info_dict = _download_with_retry(
                    "https://youtube.com/watch?v=test",
                    {"paths": {"home": str(tmp_path)}},
                    "Test Video",
                    max_retries=3,
                    initial_backoff=0.01,
                )

        assert success is False
        assert error is not None
        assert "Video unavailable" in error
        assert retry_count == 0
        assert file_path is None
        assert info_dict is None
        mock_sleep.assert_not_called()

    def test_max_retries_exceeded(self, tmp_path: Path) -> None:
        """Test failure after max retries exceeded."""
        with patch("yt_dlp.YoutubeDL") as mock_ydl:
            mock_instance = MagicMock()
            mock_instance.extract_info.side_effect = yt_dlp.utils.DownloadError("Network error")
            mock_ydl.return_value.__enter__.return_value = mock_instance

            with patch("time.sleep"):
                success, error, retry_count, file_path, info_dict = _download_with_retry(
                    "https://youtube.com/watch?v=test",
                    {"paths": {"home": str(tmp_path)}},
                    "Test Video",
                    max_retries=2,
                    initial_backoff=0.01,
                )

        assert success is False
        assert error is not None
        assert "Network error" in error
        assert retry_count == 2
        assert file_path is None
        assert info_dict is None

    def test_handles_unexpected_exception(self, tmp_path: Path) -> None:
        """Test handling of unexpected exceptions."""
        with patch("yt_dlp.YoutubeDL") as mock_ydl:
            mock_instance = MagicMock()
            mock_instance.extract_info.side_effect = RuntimeError("Unexpected error")
            mock_ydl.return_value.__enter__.return_value = mock_instance

            success, error, retry_count, file_path, info_dict = _download_with_retry(
                "https://youtube.com/watch?v=test",
                {"paths": {"home": str(tmp_path)}},
                "Test Video",
                max_retries=3,
                initial_backoff=0.01,
            )

        assert success is False
        assert error is not None
        assert "Unexpected error" in error
        assert retry_count == 0
        assert file_path is None
        assert info_dict is None


class TestDownloadAudio:
    """Tests for download_audio function."""

    def test_successful_download(self, tmp_path: Path) -> None:
        """Test successful audio download."""
        test_file = tmp_path / "test.m4a"
        test_file.touch()
        info_dict = {"title": "Test Video", "chapters": []}

        with (
            patch("downloader._download_with_retry") as mock_retry,
            patch("downloader.process_thumbnail") as mock_thumb,
            patch("downloader.process_chapters") as mock_chapters,
        ):
            mock_retry.return_value = (True, None, 0, test_file, info_dict)

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
        assert result.file_path == test_file
        mock_thumb.assert_called_once_with("test_video_id", test_file)
        mock_chapters.assert_called_once_with(info_dict, test_file)

    def test_failed_download(self, tmp_path: Path) -> None:
        """Test failed audio download."""
        with patch("downloader._download_with_retry") as mock_retry:
            mock_retry.return_value = (False, "Download failed", 2, None, None)

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
        assert result.file_path is None

    def test_uses_env_defaults(self, tmp_path: Path) -> None:
        """Test that environment defaults are used."""
        with (
            patch.dict(
                os.environ,
                {"DOWNLOAD_MAX_RETRIES": "5", "DOWNLOAD_INITIAL_BACKOFF": "1.0"},
            ),
            patch("downloader._download_with_retry") as mock_retry,
            patch("downloader.process_thumbnail"),
            patch("downloader.process_chapters"),
        ):
            mock_retry.return_value = (True, None, 0, None, None)

            download_audio("test_id", tmp_path)

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


class TestBuildSponsorblockPostprocessors:
    """Tests for _build_sponsorblock_postprocessors function."""

    def test_remove_action_produces_two_postprocessors(self) -> None:
        """Test that remove action produces SponsorBlock + ModifyChapters PPs."""
        pps = _build_sponsorblock_postprocessors(("sponsor", "intro"), "remove")
        assert len(pps) == 2
        assert pps[0]["key"] == "SponsorBlock"
        assert pps[0]["categories"] == ["sponsor", "intro"]
        assert pps[1]["key"] == "ModifyChapters"
        assert pps[1]["remove_sponsor_segments"] == ["sponsor", "intro"]

    def test_mark_action_produces_one_postprocessor(self) -> None:
        """Test that mark action produces only SponsorBlock PP."""
        pps = _build_sponsorblock_postprocessors(("sponsor",), "mark")
        assert len(pps) == 1
        assert pps[0]["key"] == "SponsorBlock"
        assert pps[0]["categories"] == ["sponsor"]

    def test_categories_passed_through(self) -> None:
        """Test that all categories are passed through correctly."""
        cats = ("sponsor", "outro", "selfpromo", "interaction")
        pps = _build_sponsorblock_postprocessors(cats, "remove")
        assert pps[0]["categories"] == list(cats)
        assert pps[1]["remove_sponsor_segments"] == list(cats)


class TestSponsorblockIntegration:
    """Tests for SponsorBlock integration in download functions."""

    def test_download_audio_adds_postprocessors(self, tmp_path: Path) -> None:
        """Test that download_audio adds SponsorBlock postprocessors to ydl_opts."""
        with (
            patch("downloader._download_with_retry") as mock_retry,
            patch("downloader.process_thumbnail"),
            patch("downloader.process_chapters"),
        ):
            mock_retry.return_value = (True, None, 0, None, None)

            download_audio(
                "test_id",
                tmp_path,
                max_retries=0,
                sponsorblock_categories=("sponsor",),
                sponsorblock_action="remove",
            )

            call_args = mock_retry.call_args
            ydl_opts = call_args[0][1]
            assert "postprocessors" in ydl_opts
            assert ydl_opts["postprocessors"][0]["key"] == "SponsorBlock"

    def test_download_audio_no_postprocessors_when_empty(self, tmp_path: Path) -> None:
        """Test that no postprocessors added when categories are empty."""
        with (
            patch("downloader._download_with_retry") as mock_retry,
            patch("downloader.process_thumbnail"),
            patch("downloader.process_chapters"),
        ):
            mock_retry.return_value = (True, None, 0, None, None)

            download_audio("test_id", tmp_path, max_retries=0)

            call_args = mock_retry.call_args
            ydl_opts = call_args[0][1]
            assert "postprocessors" not in ydl_opts

    def test_download_videos_passes_sponsorblock_params(self, tmp_path: Path) -> None:
        """Test that download_videos passes SponsorBlock params to download_audio."""
        videos = [{"id": "vid1", "title": "Video 1", "channel_id": "UC1"}]

        with patch("downloader.download_audio") as mock_download:
            mock_download.return_value = DownloadResult("vid1", "Video 1", "UC1", True)

            download_videos(
                videos,
                tmp_path,
                sponsorblock_categories=("sponsor", "outro"),
                sponsorblock_action="mark",
            )

            mock_download.assert_called_once()
            call_kwargs = mock_download.call_args[1]
            assert call_kwargs["sponsorblock_categories"] == ("sponsor", "outro")
            assert call_kwargs["sponsorblock_action"] == "mark"
