# -*- coding: utf-8 -*-
"""Audio download module using yt-dlp.

Handles downloading audio from YouTube videos.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yt_dlp

from youtube_api import VideoInfo

logger = logging.getLogger(__name__)

# YouTube URL prefix
YOUTUBE_URL_PREFIX = "https://www.youtube.com/watch?v="


@dataclass
class DownloadResult:
    """Result of a single download attempt."""

    video_id: str
    title: str
    channel_id: str
    success: bool
    error: Optional[str] = None


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


def download_audio(
    video_id: str,
    download_dir: Path,
    title: str = "",
    channel_id: str = "",
) -> DownloadResult:
    """Download audio from a YouTube video.

    Args:
        video_id: YouTube video ID.
        download_dir: Directory to save the audio file.
        title: Video title (for result tracking).
        channel_id: Channel ID (for result tracking).

    Returns:
        DownloadResult indicating success or failure.
    """
    video_url = f"{YOUTUBE_URL_PREFIX}{video_id}"

    ydl_opts = {
        "paths": {"home": str(download_dir)},
        "format": "m4a/bestaudio/best",
        "outtmpl": "%(title)s - %(channel)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        # Postprocessors for extracting audio if needed
        # 'postprocessors': [{
        #     'key': 'FFmpegExtractAudio',
        #     'preferredcodec': 'm4a',
        # }]
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        logger.info(f"Downloaded: {title or video_id}")
        return DownloadResult(
            video_id=video_id,
            title=title,
            channel_id=channel_id,
            success=True,
        )

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"Download failed for {title or video_id}: {error_msg}")
        return DownloadResult(
            video_id=video_id,
            title=title,
            channel_id=channel_id,
            success=False,
            error=error_msg,
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unexpected error downloading {title or video_id}: {error_msg}")
        return DownloadResult(
            video_id=video_id,
            title=title,
            channel_id=channel_id,
            success=False,
            error=error_msg,
        )


def download_videos(
    videos: list[VideoInfo],
    download_dir: Path,
) -> BatchDownloadResult:
    """Download audio from multiple videos.

    Args:
        videos: List of VideoInfo dictionaries.
        download_dir: Directory to save audio files.

    Returns:
        BatchDownloadResult with successful and failed downloads.
    """
    result = BatchDownloadResult()

    if not videos:
        logger.info("No videos to download")
        return result

    logger.info(f"Downloading {len(videos)} video(s)...")

    for video in videos:
        download_result = download_audio(
            video_id=video["id"],
            download_dir=download_dir,
            title=video["title"],
            channel_id=video["channel_id"],
        )

        if download_result.success:
            result.successful.append(download_result)
        else:
            result.failed.append(download_result)

    logger.info(
        f"Download complete: {result.success_count} successful, "
        f"{result.failure_count} failed"
    )

    return result
