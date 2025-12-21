"""Thumbnail handling for YouTube audio downloads.

Downloads YouTube video thumbnails, pads them to square, and embeds them
into audio files (M4A, MP3, OGG/OPUS) for podcast player compatibility.
"""

import base64
import io
import logging
from pathlib import Path

import requests
from mutagen.flac import Picture
from mutagen.id3 import APIC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from PIL import Image

logger = logging.getLogger(__name__)

# YouTube thumbnail URLs in order of preference (highest resolution first)
THUMBNAIL_URLS = [
    "https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",  # 1280x720
    "https://img.youtube.com/vi/{video_id}/sddefault.jpg",  # 640x480
    "https://img.youtube.com/vi/{video_id}/hqdefault.jpg",  # 480x360
    "https://img.youtube.com/vi/{video_id}/mqdefault.jpg",  # 320x180
    "https://img.youtube.com/vi/{video_id}/default.jpg",  # 120x90
]

# Supported audio formats for thumbnail embedding
SUPPORTED_EXTENSIONS = {".m4a", ".mp4", ".mp3", ".ogg", ".opus"}

# Request timeout in seconds
REQUEST_TIMEOUT = 30


def download_thumbnail(video_id: str) -> bytes | None:
    """Download the highest resolution thumbnail available for a YouTube video.

    Tries multiple thumbnail URLs in order of resolution (highest first),
    returning the first successful download.

    Args:
        video_id: YouTube video ID.

    Returns:
        Raw image bytes if successful, None if all URLs fail.
    """
    for url_template in THUMBNAIL_URLS:
        url = url_template.format(video_id=video_id)
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                # Check if we got actual image data (not a placeholder)
                # YouTube returns a gray placeholder for non-existent thumbnails
                content = response.content
                if len(content) > 1000:  # Real thumbnails are much larger
                    logger.debug("Downloaded thumbnail from %s", url)
                    return content
        except requests.RequestException as e:
            logger.debug("Failed to download thumbnail from %s: %s", url, e)
            continue

    logger.warning("Failed to download thumbnail for video %s", video_id)
    return None


def pad_to_square(image_data: bytes) -> bytes:
    """Pad an image to square dimensions with black bars.

    Takes a rectangular image and adds black padding to make it square,
    centering the original image.

    Args:
        image_data: Raw image bytes (JPEG or PNG).

    Returns:
        Padded image as JPEG bytes.
    """
    with Image.open(io.BytesIO(image_data)) as img:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        width, height = img.size

        if width == height:
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=95)
            return output.getvalue()

        size = max(width, height)
        square_img = Image.new("RGB", (size, size), (0, 0, 0))

        x_offset = (size - width) // 2
        y_offset = (size - height) // 2
        square_img.paste(img, (x_offset, y_offset))

        output = io.BytesIO()
        square_img.save(output, format="JPEG", quality=95)
        return output.getvalue()


def embed_thumbnail_mp3(audio_path: Path, image_data: bytes) -> bool:
    """Embed thumbnail into an MP3 file using ID3 APIC tag.

    Args:
        audio_path: Path to the MP3 file.
        image_data: JPEG image bytes.

    Returns:
        True if successful, False otherwise.
    """
    try:
        audio = MP3(audio_path)

        if audio.tags is None:
            audio.add_tags()

        # mypy doesn't understand that add_tags() ensures tags is not None
        assert audio.tags is not None

        audio.tags.delall("APIC")

        audio.tags.add(
            APIC(
                encoding=3,  # UTF-8
                mime="image/jpeg",
                type=3,  # Cover (front)
                desc="Cover",
                data=image_data,
            )
        )

        audio.save()
        return True

    except Exception as e:
        logger.error("Failed to embed thumbnail in MP3 %s: %s", audio_path, e)
        return False


def embed_thumbnail_m4a(audio_path: Path, image_data: bytes) -> bool:
    """Embed thumbnail into an M4A/MP4 file using 'covr' tag.

    Args:
        audio_path: Path to the M4A/MP4 file.
        image_data: JPEG image bytes.

    Returns:
        True if successful, False otherwise.
    """
    try:
        audio = MP4(audio_path)

        # Ensure tags exist (MP4 creates them automatically, but mypy needs to know)
        assert audio.tags is not None

        audio.tags["covr"] = [MP4Cover(image_data, imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()
        return True

    except Exception as e:
        logger.error("Failed to embed thumbnail in M4A %s: %s", audio_path, e)
        return False


def embed_thumbnail_ogg(audio_path: Path, image_data: bytes) -> bool:
    """Embed thumbnail into an OGG/OPUS file using FLAC picture block.

    Args:
        audio_path: Path to the OGG/OPUS file.
        image_data: JPEG image bytes.

    Returns:
        True if successful, False otherwise.
    """
    try:
        suffix = audio_path.suffix.lower()
        audio = OggOpus(audio_path) if suffix == ".opus" else OggVorbis(audio_path)

        picture = Picture()
        picture.type = 3  # Cover (front)
        picture.mime = "image/jpeg"
        picture.desc = "Cover"
        picture.data = image_data

        with Image.open(io.BytesIO(image_data)) as img:
            picture.width, picture.height = img.size
            picture.depth = 24  # 8 bits per channel * 3 channels

        picture_data = base64.b64encode(picture.write()).decode("ascii")
        audio["metadata_block_picture"] = [picture_data]

        audio.save()
        return True

    except Exception as e:
        logger.error("Failed to embed thumbnail in OGG %s: %s", audio_path, e)
        return False


def embed_thumbnail(audio_path: Path, image_data: bytes) -> bool:
    """Embed thumbnail into an audio file based on its format.

    Supports M4A, MP3, OGG, and OPUS formats.

    Args:
        audio_path: Path to the audio file.
        image_data: JPEG image bytes.

    Returns:
        True if successful, False otherwise.
    """
    suffix = audio_path.suffix.lower()

    if suffix in (".m4a", ".mp4"):
        return embed_thumbnail_m4a(audio_path, image_data)
    elif suffix == ".mp3":
        return embed_thumbnail_mp3(audio_path, image_data)
    elif suffix in (".ogg", ".opus"):
        return embed_thumbnail_ogg(audio_path, image_data)
    else:
        logger.debug("Unsupported format for thumbnail embedding: %s", suffix)
        return False


def process_thumbnail(video_id: str, audio_path: Path) -> bool:
    """Download, pad, and embed thumbnail for a YouTube video.

    This is the main entry point for thumbnail processing. It:
    1. Downloads the highest resolution thumbnail available
    2. Pads it to square with black bars
    3. Embeds it into the audio file

    Args:
        video_id: YouTube video ID.
        audio_path: Path to the audio file.

    Returns:
        True if thumbnail was successfully embedded, False otherwise.
    """
    if audio_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        logger.debug("Skipping thumbnail for unsupported format: %s", audio_path.suffix)
        return False

    thumbnail_data = download_thumbnail(video_id)
    if thumbnail_data is None:
        return False

    try:
        squared_data = pad_to_square(thumbnail_data)
    except Exception as e:
        logger.error("Failed to pad thumbnail for video %s: %s", video_id, e)
        return False

    success = embed_thumbnail(audio_path, squared_data)
    if success:
        logger.info("Embedded thumbnail in %s", audio_path.name)

    return success
