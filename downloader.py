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

# Prefer audio-only formats. The trailing "best" is a last-resort combined video stream,
# used when YouTube withholds audio-only formats; FFmpegExtractAudio strips it back down
# to audio so a fallback never leaves a video file behind.
AUDIO_FORMAT_SELECTOR = "bestaudio[ext=m4a]/bestaudio/best"

# Extensions to probe when postprocessing has changed the file extension.
POSTPROCESSED_EXTENSIONS = (".m4a", ".mp3", ".opus", ".ogg", ".webm", ".aac", ".flac", ".wav")

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
                    file_path = _resolve_output_path(ydl, info)

            # yt-dlp did not raise, but nothing landed on disk. Reporting success here would
            # record the video in history and it would never be retried, while move_audio_files
            # has no file to warn about either.
            if file_path is None or not file_path.exists():
                logger.error("Download of %s reported success but produced no file", title)
                return (
                    False,
                    "Download reported success but produced no file",
                    retry_count,
                    None,
                    None,
                )

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


def _resolve_output_path(ydl: yt_dlp.YoutubeDL, info: dict) -> Path:
    """Determine the final path of a downloaded file.

    Postprocessing (audio extraction, SponsorBlock cuts) can change the extension after
    the download, so the path yt-dlp reports for the raw download may not exist.

    Args:
        ydl: The YoutubeDL instance used for the download.
        info: Info dictionary returned by extract_info.

    Returns:
        Path to the downloaded file. May not exist if the file cannot be located.
    """
    # yt-dlp records the post-processed path here; prefer it over prepare_filename(),
    # which reports the extension of the raw download.
    for download in info.get("requested_downloads") or ():
        final_path = download.get("filepath")
        if final_path and Path(final_path).exists():
            return Path(final_path)

    file_path = Path(ydl.prepare_filename(info))
    if file_path.exists():
        return file_path

    for ext in POSTPROCESSED_EXTENSIONS:
        candidate = file_path.with_suffix(ext)
        if candidate.exists():
            return candidate

    return file_path


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


def _build_sponsorblock_postprocessors(
    categories: tuple[str, ...],
    action: str,
) -> list[dict]:
    """Build yt-dlp postprocessor config for SponsorBlock.

    Args:
        categories: SponsorBlock segment categories to process.
        action: Either "remove" (cut segments) or "mark" (chapter markers only).

    Returns:
        List of postprocessor dicts for yt-dlp.
    """
    postprocessors: list[dict] = [
        {
            "key": "SponsorBlock",
            "categories": list(categories),
            "when": "after_filter",
        },
    ]
    if action == "remove":
        postprocessors.append(
            {
                "key": "ModifyChapters",
                "remove_sponsor_segments": list(categories),
            }
        )
    return postprocessors


def download_audio(
    video_id: str,
    download_dir: Path,
    title: str = "",
    channel_id: str = "",
    max_retries: int | None = None,
    initial_backoff: float | None = None,
    sponsorblock_categories: tuple[str, ...] = (),
    sponsorblock_action: str = "remove",
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

    postprocessors: list[dict] = []

    if sponsorblock_categories:
        postprocessors.extend(
            _build_sponsorblock_postprocessors(sponsorblock_categories, sponsorblock_action)
        )

    # Runs last: keeps the audio stream as-is when the download is already audio-only, and
    # discards the video stream when the format selector had to fall back to a combined one.
    # Ordering relies on yt-dlp running postprocessors of the same stage in insertion order,
    # so extraction happens after ModifyChapters has made its cuts. That is an implicit
    # dependency on yt-dlp internals; test_extract_audio_runs_after_sponsorblock pins it so a
    # future upgrade that changes the default stages fails in CI rather than in production.
    postprocessors.append({"key": "FFmpegExtractAudio", "preferredcodec": "best"})

    ydl_opts = {
        "paths": {"home": str(download_dir)},
        "format": AUDIO_FORMAT_SELECTOR,
        "outtmpl": "%(title)s - %(channel)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "postprocessors": postprocessors,
    }

    success, error, retry_count, file_path, info_dict = _download_with_retry(
        video_url, ydl_opts, title or video_id, max_retries, initial_backoff
    )

    if success:
        if retry_count > 0:
            logger.info("Downloaded: %s (after %s retries)", title or video_id, retry_count)
        else:
            logger.info("Downloaded: %s", title or video_id)

        # Normalizes both a missing key and an explicit None, which some extractors return.
        if info_dict and (info_dict.get("vcodec") or "none") != "none":
            logger.warning(
                "No audio-only format was available for %s; fell back to video format %s "
                "and extracted the audio. Check that yt-dlp is up to date.",
                title or video_id,
                info_dict.get("format_id", "unknown"),
            )

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
    sponsorblock_categories: tuple[str, ...] = (),
    sponsorblock_action: str = "remove",
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
            sponsorblock_categories=sponsorblock_categories,
            sponsorblock_action=sponsorblock_action,
        )

        if download_result.success:
            result.successful.append(download_result)
        else:
            result.failed.append(download_result)

    logger.info(
        "Download complete: %s successful, %s failed", result.success_count, result.failure_count
    )

    return result
