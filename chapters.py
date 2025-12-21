"""Chapter handling for YouTube audio downloads.

Extracts chapter information from YouTube videos and embeds them
into audio files (MP3, M4A) for podcast player compatibility.
"""

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mutagen.id3 import CHAP, CTOC, TIT2, CTOCFlags
from mutagen.mp3 import MP3

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".m4a", ".mp4"}


@dataclass
class Chapter:
    """Represents a single chapter in an audio file."""

    title: str
    start_time: float
    end_time: float


def extract_chapters(info_dict: dict) -> list[Chapter]:
    """Extract chapter information from yt-dlp info_dict.

    Args:
        info_dict: The info dictionary returned by yt-dlp extract_info().

    Returns:
        List of Chapter objects, empty if no chapters found.
    """
    chapters_data = info_dict.get("chapters")
    if not chapters_data:
        logger.debug("No chapters found in video")
        return []

    chapters = []
    for chapter in chapters_data:
        start_time = chapter.get("start_time", 0)
        end_time = chapter.get("end_time", 0)
        title = chapter.get("title", "")

        if title and end_time > start_time:
            chapters.append(
                Chapter(
                    title=title,
                    start_time=float(start_time),
                    end_time=float(end_time),
                )
            )

    if chapters:
        logger.debug("Extracted %d chapters from video", len(chapters))

    return chapters


def embed_chapters_mp3(audio_path: Path, chapters: list[Chapter]) -> bool:
    """Embed chapters into an MP3 file using ID3 CHAP/CTOC frames.

    Args:
        audio_path: Path to the MP3 file.
        chapters: List of Chapter objects to embed.

    Returns:
        True if successful, False otherwise.
    """
    try:
        audio = MP3(audio_path)

        if audio.tags is None:
            audio.add_tags()

        assert audio.tags is not None

        audio.tags.delall("CHAP")
        audio.tags.delall("CTOC")

        chapter_ids = []
        for i, chapter in enumerate(chapters):
            element_id = f"chp{i}"
            chapter_ids.append(element_id)

            start_ms = int(chapter.start_time * 1000)
            end_ms = int(chapter.end_time * 1000)

            audio.tags.add(
                CHAP(
                    element_id=element_id,
                    start_time=start_ms,
                    end_time=end_ms,
                    sub_frames=[TIT2(encoding=3, text=[chapter.title])],
                )
            )

        audio.tags.add(
            CTOC(
                element_id="toc",
                flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
                child_element_ids=chapter_ids,
                sub_frames=[TIT2(encoding=3, text=["Table of Contents"])],
            )
        )

        audio.save()
        return True

    except Exception as e:
        logger.error("Failed to embed chapters in MP3 %s: %s", audio_path, e)
        return False


def _create_ffmpeg_metadata(chapters: list[Chapter]) -> str:
    """Create ffmpeg metadata file content for chapters.

    Args:
        chapters: List of Chapter objects.

    Returns:
        String content for ffmpeg metadata file.
    """
    lines = [";FFMETADATA1"]

    for chapter in chapters:
        start_ms = int(chapter.start_time * 1000)
        end_ms = int(chapter.end_time * 1000)
        title = (
            chapter.title.replace("\\", "\\\\")
            .replace("=", "\\=")
            .replace(";", "\\;")
            .replace("#", "\\#")
            .replace("\n", "\\\n")
        )

        lines.append("")
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start_ms}")
        lines.append(f"END={end_ms}")
        lines.append(f"title={title}")

    return "\n".join(lines)


def embed_chapters_m4a(audio_path: Path, chapters: list[Chapter]) -> bool:
    """Embed chapters into an M4A file using ffmpeg.

    Args:
        audio_path: Path to the M4A file.
        chapters: List of Chapter objects to embed.

    Returns:
        True if successful, False otherwise.
    """
    try:
        metadata_content = _create_ffmpeg_metadata(chapters)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as metadata_file:
            metadata_file.write(metadata_content)
            metadata_path = Path(metadata_file.name)

        output_path = audio_path.with_suffix(".tmp.m4a")

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(audio_path),
                    "-i",
                    str(metadata_path),
                    "-map_metadata",
                    "1",
                    "-map_chapters",
                    "1",
                    "-codec",
                    "copy",
                    "-y",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error("ffmpeg failed to embed chapters: %s", result.stderr)
                if output_path.exists():
                    output_path.unlink()
                return False

            output_path.replace(audio_path)
            return True

        finally:
            metadata_path.unlink(missing_ok=True)
            if output_path.exists():
                output_path.unlink()

    except FileNotFoundError:
        logger.error("ffmpeg not found. Cannot embed chapters in M4A files.")
        return False
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out while embedding chapters in %s", audio_path)
        return False
    except Exception as e:
        logger.error("Failed to embed chapters in M4A %s: %s", audio_path, e)
        return False


def embed_chapters(audio_path: Path, chapters: list[Chapter]) -> bool:
    """Embed chapters into an audio file based on its format.

    Supports MP3 and M4A formats.

    Args:
        audio_path: Path to the audio file.
        chapters: List of Chapter objects to embed.

    Returns:
        True if successful, False otherwise.
    """
    suffix = audio_path.suffix.lower()

    if suffix == ".mp3":
        return embed_chapters_mp3(audio_path, chapters)
    elif suffix in (".m4a", ".mp4"):
        return embed_chapters_m4a(audio_path, chapters)
    else:
        logger.debug("Unsupported format for chapter embedding: %s", suffix)
        return False


def process_chapters(info_dict: dict, audio_path: Path) -> bool:
    """Extract and embed chapters from yt-dlp info_dict into audio file.

    This is the main entry point for chapter processing. It:
    1. Extracts chapter information from the info_dict
    2. Embeds chapters into the audio file if any were found

    Args:
        info_dict: The info dictionary returned by yt-dlp extract_info().
        audio_path: Path to the audio file.

    Returns:
        True if chapters were successfully embedded, False otherwise.
    """
    if audio_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        logger.debug("Skipping chapters for unsupported format: %s", audio_path.suffix)
        return False

    chapters = extract_chapters(info_dict)
    if not chapters:
        return False

    success = embed_chapters(audio_path, chapters)
    if success:
        logger.info("Embedded %d chapters in %s", len(chapters), audio_path.name)

    return success
