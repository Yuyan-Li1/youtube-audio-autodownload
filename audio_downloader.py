"""YouTube audio downloader - main entry point.

Downloads audio from YouTube videos of specified channels and moves them
to a target directory (designed for podcast apps like Castro).

Designed for cron job execution with:
- Idempotent operation (safe to run multiple times)
- Download history tracking (prevents duplicate downloads)
- Lock file to prevent concurrent runs
- Proper logging for debugging cron issues
"""

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from config import Config, ConfigError, load_config
from downloader import BatchDownloadResult, download_videos
from file_ops import move_audio_files
from history import (
    DownloadHistory,
    cleanup_old_entries,
    create_video_record,
    filter_new_videos,
    load_history,
    save_history,
)
from lock import lock_context
from youtube_api import (
    VideoInfo,
    create_youtube_client,
    fetch_all_channels_videos,
    filter_shorts_and_streams,
)

logger = logging.getLogger(__name__)


def setup_logging(log_level: str, log_file: Path | None = None) -> None:
    """Configure logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional file to write logs to.
    """
    handlers: list[logging.Handler] = []

    # Console handler (stderr for cron compatibility)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    handlers.append(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level),
        handlers=handlers,
    )


def run(config: Config) -> int:
    """Main execution flow.

    This is the core logic, separated from main() for testability.

    Args:
        config: Configuration object.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    # 1. Load download history
    history = load_history(config.history_file)
    downloaded_ids = history.get_downloaded_ids()
    logger.info(f"Loaded history with {len(downloaded_ids)} previously downloaded videos")

    # 2. Calculate lookback window
    since_date = datetime.now(UTC) - timedelta(days=config.lookback_days)
    logger.info(f"Checking for videos published since {since_date.date()}")

    # 3. Create YouTube client and fetch videos from all channels
    client = create_youtube_client(config.api_key)
    all_videos = fetch_all_channels_videos(
        client, config.channel_ids, since_date, dry_run=config.dry_run
    )

    if not all_videos:
        logger.info("No videos found in the lookback window")
        return 0

    # 4. Filter out shorts and streams
    all_videos = filter_shorts_and_streams(client, all_videos, dry_run=config.dry_run)

    if not all_videos:
        logger.info("No regular videos found (all were shorts or streams)")
        return 0

    # 5. Filter out already downloaded videos (idempotent operation)
    new_videos = filter_new_videos(all_videos, downloaded_ids)

    if not new_videos:
        logger.info("All videos already downloaded, nothing to do")
        return 0

    logger.info(f"Found {len(new_videos)} new video(s) to download")

    # 6. Download each video
    download_results = download_videos(new_videos, config.download_dir)

    # 7. Update history with successful downloads
    history = update_history_with_results(history, download_results, new_videos)

    # 8. Cleanup old history entries
    history = cleanup_old_entries(history, max_age_days=config.history_max_age_days)

    # 9. Save history once (after both update and cleanup)
    if not save_history(history, config.history_file):
        logger.error("Failed to save history file")

    # 10. Move downloaded files to target directory
    move_results = move_audio_files(config.download_dir, config.target_dir, config.audio_extensions)

    # 11. Log summary
    log_summary(download_results, move_results)

    # Return error if any downloads failed
    return 1 if download_results.failure_count > 0 else 0


def update_history_with_results(
    history: DownloadHistory,
    results: BatchDownloadResult,
    videos: list[VideoInfo],
) -> DownloadHistory:
    """Update history with successful downloads.

    Args:
        history: Current download history.
        results: Download results.
        videos: Original video info list.

    Returns:
        Updated history.
    """
    # Create a lookup for video info
    video_lookup = {v["id"]: v for v in videos}

    for result in results.successful:
        video_info = video_lookup.get(result.video_id)
        if video_info:
            record = create_video_record(
                video_id=result.video_id,
                title=result.title,
                channel_id=result.channel_id,
                published_at=video_info["published_at"],
            )
            history = history.add_video(record)

    return history


def log_summary(
    download_results: BatchDownloadResult,
    move_results,
) -> None:
    """Log a summary of the run.

    Args:
        download_results: Results of download operations.
        move_results: Results of file move operations.
    """
    logger.info("=" * 50)
    logger.info("Run Summary")
    logger.info("=" * 50)
    logger.info(
        f"Downloads: {download_results.success_count} successful, "
        f"{download_results.failure_count} failed"
    )
    logger.info(
        f"Files moved: {move_results.success_count} successful, {move_results.failure_count} failed"
    )

    if download_results.failed:
        logger.warning("Failed downloads:")
        for failure in download_results.failed:
            logger.warning(f"  - {failure.title}: {failure.error}")

    if move_results.failed:
        logger.warning("Failed moves:")
        for failure in move_results.failed:
            logger.warning(f"  - {failure.source.name}: {failure.error}")

    logger.info("=" * 50)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Download audio from YouTube channels and move to podcast folder."
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug logging (overrides LOG_LEVEL env var).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode: use mock data instead of calling YouTube API (saves API quota).",
    )
    args = parser.parse_args()

    # Load configuration
    try:
        config = load_config(dry_run=args.dry_run)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Setup logging (debug flag overrides env var)
    log_level = "DEBUG" if args.debug else config.log_level
    setup_logging(log_level, config.log_file)

    logger.info("Starting YouTube audio downloader")
    if config.dry_run:
        logger.info("*** DRY RUN MODE: Using mock data, not consuming API quota ***")

    # Acquire lock to prevent concurrent runs
    lock_file = Path(__file__).parent / "youtube_downloader.lock"

    with lock_context(lock_file) as acquired:
        if not acquired:
            logger.error("Another instance is already running, exiting")
            return 1

        try:
            return run(config)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            return 1
        finally:
            logger.info("Done")


if __name__ == "__main__":
    sys.exit(main())
