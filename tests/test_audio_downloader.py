"""Tests for audio_downloader module (main entry point)."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from audio_downloader import (
    log_summary,
    main,
    run,
    setup_logging,
    update_history_with_results,
)
from config import Config, ConfigError
from downloader import BatchDownloadResult, DownloadResult
from file_ops import BatchMoveResult, MoveResult
from history import DownloadHistory


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_console_logging(self) -> None:
        """Test setting up console logging."""
        # Reset root logger for clean test
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.NOTSET)

        setup_logging("INFO")
        # Verify logging is configured (handlers exist)
        assert len(root_logger.handlers) > 0

    def test_setup_debug_logging(self) -> None:
        """Test setting up debug logging."""
        # Reset root logger for clean test
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.NOTSET)

        setup_logging("DEBUG")
        # Verify logging is configured
        assert len(root_logger.handlers) > 0

    def test_setup_with_file_logging(self, tmp_path: Path) -> None:
        """Test setting up file logging."""
        # Reset root logger for clean test
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        log_file = tmp_path / "test.log"
        setup_logging("INFO", log_file)

        # Check that file handler was added
        has_file_handler = any(isinstance(h, logging.FileHandler) for h in root_logger.handlers)
        assert has_file_handler


class TestUpdateHistoryWithResults:
    """Tests for update_history_with_results function."""

    def test_updates_history_with_successful_downloads(self) -> None:
        """Test that history is updated with successful downloads."""
        history = DownloadHistory(downloaded_videos={})
        results = BatchDownloadResult(
            successful=[
                DownloadResult("vid1", "Video 1", "UC1", True),
                DownloadResult("vid2", "Video 2", "UC2", True),
            ],
            failed=[],
        )
        videos = [
            {
                "id": "vid1",
                "title": "Video 1",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 15, tzinfo=UTC),
            },
            {
                "id": "vid2",
                "title": "Video 2",
                "channel_id": "UC2",
                "published_at": datetime(2024, 1, 14, tzinfo=UTC),
            },
        ]

        updated = update_history_with_results(history, results, videos)

        assert updated.contains("vid1")
        assert updated.contains("vid2")

    def test_ignores_failed_downloads(self) -> None:
        """Test that failed downloads are not added to history."""
        history = DownloadHistory(downloaded_videos={})
        results = BatchDownloadResult(
            successful=[],
            failed=[
                DownloadResult("vid1", "Video 1", "UC1", False, error="Failed"),
            ],
        )
        videos = [
            {
                "id": "vid1",
                "title": "Video 1",
                "channel_id": "UC1",
                "published_at": datetime(2024, 1, 15, tzinfo=UTC),
            },
        ]

        updated = update_history_with_results(history, results, videos)

        assert not updated.contains("vid1")

    def test_handles_missing_video_info(self) -> None:
        """Test handling when video info is missing."""
        history = DownloadHistory(downloaded_videos={})
        results = BatchDownloadResult(
            successful=[
                DownloadResult("vid_missing", "Missing Video", "UC1", True),
            ],
            failed=[],
        )
        videos: list[dict[str, Any]] = []  # Empty videos list

        updated = update_history_with_results(history, results, videos)

        # Should not crash, video just won't be added
        assert not updated.contains("vid_missing")


class TestLogSummary:
    """Tests for log_summary function."""

    def test_logs_successful_summary(self, tmp_path: Path, caplog) -> None:
        """Test logging summary with successful results."""
        download_results = BatchDownloadResult(
            successful=[DownloadResult("v1", "T1", "C1", True)],
            failed=[],
        )
        move_results = BatchMoveResult(
            successful=[MoveResult(tmp_path / "a.m4a", tmp_path / "b.m4a", True)],
            failed=[],
        )

        with caplog.at_level(logging.INFO):
            log_summary(download_results, move_results)

        assert "1 successful" in caplog.text
        assert "0 failed" in caplog.text

    def test_logs_failed_downloads(self, caplog) -> None:
        """Test logging summary with failed downloads."""
        download_results = BatchDownloadResult(
            successful=[],
            failed=[DownloadResult("v1", "Failed Video", "C1", False, error="Error msg")],
        )
        move_results = BatchMoveResult(successful=[], failed=[])

        with caplog.at_level(logging.WARNING):
            log_summary(download_results, move_results)

        assert "Failed downloads" in caplog.text
        assert "Failed Video" in caplog.text

    def test_logs_failed_moves(self, tmp_path: Path, caplog) -> None:
        """Test logging summary with failed moves."""
        download_results = BatchDownloadResult(successful=[], failed=[])
        move_results = BatchMoveResult(
            successful=[],
            failed=[
                MoveResult(
                    tmp_path / "failed.m4a", tmp_path / "dest.m4a", False, error="Move error"
                )
            ],
        )

        with caplog.at_level(logging.WARNING):
            log_summary(download_results, move_results)

        assert "Failed moves" in caplog.text


class TestRun:
    """Tests for run function."""

    def test_run_no_videos_found(self, tmp_path: Path) -> None:
        """Test run when no videos are found."""
        config = Config(
            api_key="test_key",
            channel_ids=("UC1",),
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
            dry_run=True,
        )
        (tmp_path / "downloads").mkdir()
        (tmp_path / "target").mkdir()

        with patch("audio_downloader.load_history") as mock_load:
            mock_load.return_value = DownloadHistory(downloaded_videos={})
            with patch("audio_downloader.fetch_all_channels_videos") as mock_fetch:
                mock_fetch.return_value = []

                result = run(config)

        assert result == 0

    def test_run_all_videos_downloaded(self, tmp_path: Path) -> None:
        """Test run when all videos already downloaded."""
        config = Config(
            api_key="test_key",
            channel_ids=("UC1",),
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
            dry_run=True,
        )
        (tmp_path / "downloads").mkdir()
        (tmp_path / "target").mkdir()

        with patch("audio_downloader.load_history") as mock_load:
            mock_load.return_value = DownloadHistory(downloaded_videos={"vid1": {}})
            with patch("audio_downloader.fetch_all_channels_videos") as mock_fetch:
                mock_fetch.return_value = [
                    {
                        "id": "vid1",
                        "title": "Video 1",
                        "channel_id": "UC1",
                        "published_at": datetime.now(UTC),
                    }
                ]

                result = run(config)

        assert result == 0

    def test_run_successful_download(self, tmp_path: Path) -> None:
        """Test successful download run."""
        config = Config(
            api_key="test_key",
            channel_ids=("UC1",),
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
            dry_run=True,
        )
        (tmp_path / "downloads").mkdir()
        (tmp_path / "target").mkdir()

        with patch("audio_downloader.load_history") as mock_load:
            mock_load.return_value = DownloadHistory(downloaded_videos={})
            with patch("audio_downloader.fetch_all_channels_videos") as mock_fetch:
                mock_fetch.return_value = [
                    {
                        "id": "vid1",
                        "title": "Video 1",
                        "channel_id": "UC1",
                        "published_at": datetime.now(UTC),
                    }
                ]
                with patch("audio_downloader.download_videos") as mock_download:
                    mock_download.return_value = BatchDownloadResult(
                        successful=[DownloadResult("vid1", "Video 1", "UC1", True)],
                        failed=[],
                    )
                    with patch("audio_downloader.save_history") as mock_save:
                        mock_save.return_value = True
                        with patch("audio_downloader.move_audio_files") as mock_move:
                            mock_move.return_value = BatchMoveResult()

                            result = run(config)

        assert result == 0

    def test_run_with_download_failures(self, tmp_path: Path) -> None:
        """Test run with some download failures."""
        config = Config(
            api_key="test_key",
            channel_ids=("UC1",),
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
            dry_run=True,
        )
        (tmp_path / "downloads").mkdir()
        (tmp_path / "target").mkdir()

        with patch("audio_downloader.load_history") as mock_load:
            mock_load.return_value = DownloadHistory(downloaded_videos={})
            with patch("audio_downloader.fetch_all_channels_videos") as mock_fetch:
                mock_fetch.return_value = [
                    {
                        "id": "vid1",
                        "title": "Video 1",
                        "channel_id": "UC1",
                        "published_at": datetime.now(UTC),
                    }
                ]
                with patch("audio_downloader.download_videos") as mock_download:
                    mock_download.return_value = BatchDownloadResult(
                        successful=[],
                        failed=[DownloadResult("vid1", "Video 1", "UC1", False, error="Failed")],
                    )
                    with (
                        patch("audio_downloader.save_history"),
                        patch("audio_downloader.move_audio_files") as mock_move,
                    ):
                        mock_move.return_value = BatchMoveResult()

                        result = run(config)

        assert result == 1  # Should return error code


class TestMain:
    """Tests for main function."""

    def test_main_config_error(self) -> None:
        """Test main with configuration error."""

        with patch("audio_downloader.load_config") as mock_load:
            mock_load.side_effect = ConfigError("Missing API key")
            with patch("sys.argv", ["audio_downloader.py"]):
                result = main()

        assert result == 1

    def test_main_lock_not_acquired(self, tmp_path: Path) -> None:
        """Test main when lock cannot be acquired."""
        config = Config(
            api_key="test_key",
            channel_ids=("UC1",),
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
            dry_run=True,
        )

        with (
            patch("audio_downloader.load_config", return_value=config),
            patch("audio_downloader.lock_context") as mock_lock,
        ):
            mock_lock.return_value.__enter__ = MagicMock(return_value=False)
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            with patch("sys.argv", ["audio_downloader.py"]):
                result = main()

        assert result == 1

    def test_main_unexpected_exception(self, tmp_path: Path) -> None:
        """Test main with unexpected exception."""
        config = Config(
            api_key="test_key",
            channel_ids=("UC1",),
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
            dry_run=True,
        )

        with (
            patch("audio_downloader.load_config", return_value=config),
            patch("audio_downloader.lock_context") as mock_lock,
        ):
            mock_lock.return_value.__enter__ = MagicMock(return_value=True)
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            with (
                patch("audio_downloader.run", side_effect=RuntimeError("Unexpected")),
                patch("sys.argv", ["audio_downloader.py"]),
            ):
                result = main()

        assert result == 1

    def test_main_debug_flag(self, tmp_path: Path) -> None:
        """Test main with debug flag."""
        config = Config(
            api_key="test_key",
            channel_ids=("UC1",),
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
            dry_run=True,
        )
        (tmp_path / "downloads").mkdir()
        (tmp_path / "target").mkdir()

        with (
            patch("audio_downloader.load_config", return_value=config),
            patch("audio_downloader.lock_context") as mock_lock,
        ):
            mock_lock.return_value.__enter__ = MagicMock(return_value=True)
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            with (
                patch("audio_downloader.run", return_value=0),
                patch("sys.argv", ["audio_downloader.py", "--debug"]),
            ):
                result = main()

        assert result == 0

    def test_main_dry_run_flag(self, tmp_path: Path) -> None:
        """Test main with dry-run flag."""
        config = Config(
            api_key="test_key",
            channel_ids=("UC1",),
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
            dry_run=True,
        )
        (tmp_path / "downloads").mkdir()
        (tmp_path / "target").mkdir()

        with (
            patch("audio_downloader.load_config", return_value=config) as mock_load,
            patch("audio_downloader.lock_context") as mock_lock,
        ):
            mock_lock.return_value.__enter__ = MagicMock(return_value=True)
            mock_lock.return_value.__exit__ = MagicMock(return_value=False)
            with (
                patch("audio_downloader.run", return_value=0),
                patch("sys.argv", ["audio_downloader.py", "--dry-run"]),
            ):
                result = main()

            # Verify dry_run was passed to load_config
            mock_load.assert_called_once_with(dry_run=True)

        assert result == 0
