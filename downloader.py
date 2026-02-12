"""Audio download module using yt-dlp.

Handles downloading audio from YouTube videos with retry logic.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp

from chapters import process_chapters
from thumbnail import process_thumbnail
from youtube_api import VideoInfo

logger = logging.getLogger(__name__)

# YouTube URL prefix
YOUTUBE_URL_PREFIX = "https://www.youtube.com/watch?v="

# Retry configuration defaults
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 2.0  # seconds


@dataclass
class DownloadResult:
    """Result of a single download attempt."""

    video_id: str
    title: str
    channel_id: str
    success: bool
    error: str | None = None
    retry_count: int = 0
    file_path: Path | None = None


@dataclass
class BatchDownloadResult:
    """Result of downloading multiple videos."""

    successful: list[DownloadResult] = field(default_factory=list)
    failed: list[DownloadResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of download attempts."""
        return len(self.successful) + len(self.failed)

    @property
    def success_count(self) -> int:
        """Number of successful downloads."""
        return len(self.successful)

    @property
    def failure_count(self) -> int:
        """Number of failed downloads."""
        return len(self.failed)


def _download_with_retry(
    video_url: str,
    ydl_opts: dict,
    title: str,
    max_retries: int,
    initial_backoff: float,
) -> tuple[bool, str | None, int, Path | None, dict | None]:
    """Attempt to download with exponential backoff retry.

    Args:
        video_url: YouTube video URL.
        ydl_opts: yt-dlp options dictionary.
        title: Video title for logging.
        max_retries: Maximum number of retry attempts.
        initial_backoff: Initial backoff delay in seconds.

    Returns:
        Tuple of (success, error_message, retry_count, file_path, info_dict).
    """
    last_error: str | None = None
    retry_count = 0
    file_path: Path | None = None
    info_dict: dict | None = None

    for attempt in range(max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                if info:
                    info_dict = dict(info)
                    filename = ydl.prepare_filename(info)
                    file_path = Path(filename)
                    if not file_path.exists():
                        for ext in [".m4a", ".mp3", ".opus", ".ogg", ".webm"]:
                            candidate = file_path.with_suffix(ext)
                            if candidate.exists():
                                file_path = candidate
                                break
            return True, None, retry_count, file_path, info_dict

        except yt_dlp.utils.DownloadError as e:
            last_error = str(e)
            retry_count = attempt

            # Check if this is a permanent error (don't retry)
            if _is_permanent_error(last_error):
                logger.error("Permanent error for %s: %s", title, last_error)
                break

            # Retry with backoff if we have attempts left
            if attempt < max_retries:
                backoff = initial_backoff * (2**attempt)
                logger.warning(
                    "Download failed for %s, retrying in %ss (attempt %s/%s): %s",
                    title,
                    backoff,
                    attempt + 1,
                    max_retries + 1,
                    last_error,
                )
                time.sleep(backoff)
            else:
                logger.error(
                    "Download failed for %s after %s attempts: %s",
                    title,
                    max_retries + 1,
                    last_error,
                )

        except (OSError, ValueError, KeyError, RuntimeError, TypeError) as e:
            last_error = str(e)
            retry_count = attempt
            logger.error("Unexpected error downloading %s: %s", title, last_error)
            break

    return False, last_error, retry_count, None, None


def _is_permanent_error(error_msg: str) -> bool:
    """Check if an error is permanent and shouldn't be retried.

    Args:
        error_msg: The error message from yt-dlp.

    Returns:
        True if the error is permanent (video unavailable, private, etc.).
    """
    permanent_indicators = [
        "Video unavailable",
        "Private video",
        "This video is not available",
        "Sign in to confirm your age",
        "members-only content",
        "This video has been removed",
        "copyright claim",
        "This video is no longer available",
    ]
    return any(indicator.lower() in error_msg.lower() for indicator in permanent_indicators)


def download_audio(
    video_id: str,
    download_dir: Path,
    title: str = "",
    channel_id: str = "",
    max_retries: int | None = None,
    initial_backoff: float | None = None,
) -> DownloadResult:
    """Download audio from a YouTube video with retry logic.

    Also downloads and embeds the video thumbnail into the audio file.

    Args:
        video_id: YouTube video ID.
        download_dir: Directory to save the audio file.
        title: Video title (for result tracking).
        channel_id: Channel ID (for result tracking).
        max_retries: Maximum retry attempts (default from env or 3).
        initial_backoff: Initial backoff delay in seconds (default from env or 2.0).

    Returns:
        DownloadResult indicating success or failure.
    """
    video_url = f"{YOUTUBE_URL_PREFIX}{video_id}"

    # Get retry config from environment or use defaults
    if max_retries is None:
        max_retries = int(os.getenv("DOWNLOAD_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)))
    if initial_backoff is None:
        initial_backoff = float(os.getenv("DOWNLOAD_INITIAL_BACKOFF", str(DEFAULT_INITIAL_BACKOFF)))

    ydl_opts = {
        "paths": {"home": str(download_dir)},
        "format": "m4a/bestaudio/best",
        "outtmpl": "%(title)s - %(channel)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {"key": "FFmpegMetadata"},  # Embeds title, artist, date, etc.
        ],
    }

    success, error, retry_count, file_path, info_dict = _download_with_retry(
        video_url, ydl_opts, title or video_id, max_retries, initial_backoff
    )

    if success:
        if retry_count > 0:
            logger.info("Downloaded: %s (after %s retries)", title or video_id, retry_count)
        else:
            logger.info("Downloaded: %s", title or video_id)

        if file_path and file_path.exists():
            process_thumbnail(video_id, file_path)
            if info_dict:
                process_chapters(info_dict, file_path)

    return DownloadResult(
        video_id=video_id,
        title=title,
        channel_id=channel_id,
        success=success,
        error=error,
        retry_count=retry_count,
        file_path=file_path,
    )


def download_videos(
    videos: list[VideoInfo],
    download_dir: Path,
    max_retries: int | None = None,
    initial_backoff: float | None = None,
) -> BatchDownloadResult:
    """Download audio from multiple videos with retry logic.

    Args:
        videos: List of VideoInfo dictionaries.
        download_dir: Directory to save audio files.
        max_retries: Maximum retry attempts per video.
        initial_backoff: Initial backoff delay in seconds.

    Returns:
        BatchDownloadResult with successful and failed downloads.
    """
    result = BatchDownloadResult()

    if not videos:
        logger.info("No videos to download")
        return result

    logger.info("Downloading %s video(s)...", len(videos))

    for video in videos:
        download_result = download_audio(
            video_id=video["id"],
            download_dir=download_dir,
            title=video["title"],
            channel_id=video["channel_id"],
            max_retries=max_retries,
            initial_backoff=initial_backoff,
        )

        if download_result.success:
            result.successful.append(download_result)
        else:
            result.failed.append(download_result)

    logger.info(
        "Download complete: %s successful, %s failed", result.success_count, result.failure_count
    )

    return result
