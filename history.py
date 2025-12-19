"""Download history management for YouTube audio downloader.

Tracks which videos have been successfully downloaded to prevent duplicates
and enable automatic retry of failed downloads.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from youtube_api import VideoInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoRecord:
    """Record of a successfully downloaded video."""

    video_id: str
    title: str
    channel_id: str
    downloaded_at: str  # ISO format
    published_at: str  # ISO format


@dataclass
class DownloadHistory:
    """Container for download history with helper methods."""

    downloaded_videos: dict[str, dict]  # video_id -> metadata

    def contains(self, video_id: str) -> bool:
        """Check if a video has been downloaded."""
        return video_id in self.downloaded_videos

    def get_downloaded_ids(self) -> frozenset[str]:
        """Get immutable set of all downloaded video IDs."""
        return frozenset(self.downloaded_videos.keys())

    def add_video(self, record: VideoRecord) -> "DownloadHistory":
        """Add a video record, returning a new history (immutable pattern)."""
        new_videos = dict(self.downloaded_videos)
        new_videos[record.video_id] = {
            "title": record.title,
            "channel_id": record.channel_id,
            "downloaded_at": record.downloaded_at,
            "published_at": record.published_at,
        }
        return DownloadHistory(downloaded_videos=new_videos)


def load_history(history_file: Path) -> DownloadHistory:
    """Load download history from JSON file.

    Args:
        history_file: Path to the history JSON file.

    Returns:
        DownloadHistory object. Returns empty history if file doesn't exist.
    """
    if not history_file.exists():
        logger.info(f"No history file found at {history_file}, starting fresh")
        return DownloadHistory(downloaded_videos={})

    try:
        with open(history_file, encoding="utf-8") as f:
            data = json.load(f)

        downloaded = data.get("downloaded_videos", {})
        logger.info(f"Loaded history with {len(downloaded)} videos")
        return DownloadHistory(downloaded_videos=downloaded)

    except json.JSONDecodeError as e:
        logger.warning(f"Corrupted history file, starting fresh: {e}")
        return DownloadHistory(downloaded_videos={})
    except Exception as e:
        logger.error(f"Error loading history: {e}")
        return DownloadHistory(downloaded_videos={})


def save_history(history: DownloadHistory, history_file: Path) -> bool:
    """Save download history to JSON file.

    Uses atomic write pattern with temp file cleanup on failure.

    Args:
        history: The history to save.
        history_file: Path to save to.

    Returns:
        True if successful, False otherwise.
    """
    temp_file = history_file.with_suffix(".tmp")

    try:
        # Ensure parent directory exists
        history_file.parent.mkdir(parents=True, exist_ok=True)

        data = {"downloaded_videos": history.downloaded_videos}

        # Write atomically by writing to temp file first
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        temp_file.replace(history_file)
        logger.debug(f"Saved history with {len(history.downloaded_videos)} videos")
        return True

    except Exception as e:
        logger.error(f"Error saving history: {e}")
        # Clean up temp file on failure
        try:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temp file: {temp_file}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up temp file {temp_file}: {cleanup_error}")
        return False


def create_video_record(
    video_id: str,
    title: str,
    channel_id: str,
    published_at: datetime,
) -> VideoRecord:
    """Create a video record with current timestamp.

    Args:
        video_id: YouTube video ID.
        title: Video title.
        channel_id: YouTube channel ID.
        published_at: When the video was published.

    Returns:
        VideoRecord with download timestamp set to now.
    """
    return VideoRecord(
        video_id=video_id,
        title=title,
        channel_id=channel_id,
        downloaded_at=datetime.now().isoformat(),
        published_at=published_at.isoformat()
        if isinstance(published_at, datetime)
        else published_at,
    )


def filter_new_videos(
    videos: list[VideoInfo],
    downloaded_ids: frozenset[str],
) -> list[VideoInfo]:
    """Filter out videos that have already been downloaded.

    This is a pure function - no side effects.

    Args:
        videos: List of VideoInfo dictionaries.
        downloaded_ids: Set of already downloaded video IDs.

    Returns:
        New list containing only videos not in downloaded_ids.
    """
    new_videos = [v for v in videos if v["id"] not in downloaded_ids]
    skipped = len(videos) - len(new_videos)
    if skipped > 0:
        logger.debug(f"Filtered out {skipped} already downloaded videos")
    return new_videos


def cleanup_old_entries(
    history: DownloadHistory,
    max_age_days: int,
) -> DownloadHistory:
    """Remove entries older than max_age_days.

    This keeps the history file from growing indefinitely.

    Args:
        history: Current history.
        max_age_days: Maximum age of entries to keep.

    Returns:
        New history with old entries removed.
    """
    cutoff = datetime.now() - timedelta(days=max_age_days)
    cutoff_str = cutoff.isoformat()

    new_videos = {
        vid: meta
        for vid, meta in history.downloaded_videos.items()
        if meta.get("downloaded_at", "") >= cutoff_str
    }

    removed = len(history.downloaded_videos) - len(new_videos)
    if removed > 0:
        logger.info(f"Cleaned up {removed} entries older than {max_age_days} days")

    return DownloadHistory(downloaded_videos=new_videos)
