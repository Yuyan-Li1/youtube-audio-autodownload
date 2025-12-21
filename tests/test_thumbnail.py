"""Tests for thumbnail module."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from thumbnail import (
    SUPPORTED_EXTENSIONS,
    THUMBNAIL_URLS,
    download_thumbnail,
    embed_thumbnail,
    embed_thumbnail_m4a,
    embed_thumbnail_mp3,
    embed_thumbnail_ogg,
    pad_to_square,
    process_thumbnail,
)


class TestDownloadThumbnail:
    """Tests for download_thumbnail function."""

    def test_downloads_first_available_thumbnail(self) -> None:
        """Test that highest resolution thumbnail is downloaded first."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"x" * 2000  # Larger than placeholder threshold

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = download_thumbnail("test_video_id")

        assert result == b"x" * 2000
        # Should have called with the first (highest res) URL
        expected_url = THUMBNAIL_URLS[0].format(video_id="test_video_id")
        mock_get.assert_called_once_with(expected_url, timeout=30)

    def test_falls_back_to_lower_resolution(self) -> None:
        """Test fallback to lower resolution when highest fails."""
        mock_responses = [
            MagicMock(status_code=404),  # maxresdefault fails
            MagicMock(status_code=200, content=b"y" * 2000),  # sddefault succeeds
        ]

        with patch("requests.get", side_effect=mock_responses) as mock_get:
            result = download_thumbnail("test_video_id")

        assert result == b"y" * 2000
        assert mock_get.call_count == 2

    def test_returns_none_when_all_fail(self) -> None:
        """Test that None is returned when all URLs fail."""
        mock_response = MagicMock(status_code=404)

        with patch("requests.get", return_value=mock_response):
            result = download_thumbnail("test_video_id")

        assert result is None

    def test_ignores_placeholder_images(self) -> None:
        """Test that small placeholder images are ignored."""
        # First response is a small placeholder
        mock_responses = [
            MagicMock(status_code=200, content=b"x" * 500),  # Too small
            MagicMock(status_code=200, content=b"y" * 2000),  # Real image
        ]

        with patch("requests.get", side_effect=mock_responses):
            result = download_thumbnail("test_video_id")

        assert result == b"y" * 2000

    def test_handles_request_exception(self) -> None:
        """Test handling of request exceptions."""
        import requests

        with patch("requests.get", side_effect=requests.RequestException("Network error")):
            result = download_thumbnail("test_video_id")

        assert result is None


class TestPadToSquare:
    """Tests for pad_to_square function."""

    def _create_test_image(self, width: int, height: int) -> bytes:
        """Create a test image of specified dimensions."""
        img = Image.new("RGB", (width, height), color="red")
        output = io.BytesIO()
        img.save(output, format="JPEG")
        return output.getvalue()

    def test_pads_landscape_image(self) -> None:
        """Test padding of a landscape (wide) image."""
        # 200x100 image should become 200x200
        image_data = self._create_test_image(200, 100)
        result = pad_to_square(image_data)

        with Image.open(io.BytesIO(result)) as img:
            assert img.size == (200, 200)

    def test_pads_portrait_image(self) -> None:
        """Test padding of a portrait (tall) image."""
        # 100x200 image should become 200x200
        image_data = self._create_test_image(100, 200)
        result = pad_to_square(image_data)

        with Image.open(io.BytesIO(result)) as img:
            assert img.size == (200, 200)

    def test_square_image_unchanged_size(self) -> None:
        """Test that square image dimensions are preserved."""
        # 200x200 image should stay 200x200
        image_data = self._create_test_image(200, 200)
        result = pad_to_square(image_data)

        with Image.open(io.BytesIO(result)) as img:
            assert img.size == (200, 200)

    def test_output_is_jpeg(self) -> None:
        """Test that output is always JPEG format."""
        image_data = self._create_test_image(200, 100)
        result = pad_to_square(image_data)

        with Image.open(io.BytesIO(result)) as img:
            assert img.format == "JPEG"

    def test_handles_png_with_alpha(self) -> None:
        """Test handling of PNG with alpha channel."""
        # Create RGBA image
        img = Image.new("RGBA", (200, 100), color=(255, 0, 0, 128))
        output = io.BytesIO()
        img.save(output, format="PNG")
        image_data = output.getvalue()

        result = pad_to_square(image_data)

        with Image.open(io.BytesIO(result)) as img:
            assert img.size == (200, 200)
            assert img.mode == "RGB"  # Should be converted from RGBA


class TestEmbedThumbnail:
    """Tests for embed_thumbnail function."""

    def test_routes_to_m4a_handler(self, tmp_path: Path) -> None:
        """Test that .m4a files are routed to M4A handler."""
        audio_file = tmp_path / "test.m4a"
        audio_file.touch()

        with patch("thumbnail.embed_thumbnail_m4a", return_value=True) as mock:
            result = embed_thumbnail(audio_file, b"image_data")

        mock.assert_called_once_with(audio_file, b"image_data")
        assert result is True

    def test_routes_to_mp3_handler(self, tmp_path: Path) -> None:
        """Test that .mp3 files are routed to MP3 handler."""
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch("thumbnail.embed_thumbnail_mp3", return_value=True) as mock:
            result = embed_thumbnail(audio_file, b"image_data")

        mock.assert_called_once_with(audio_file, b"image_data")
        assert result is True

    def test_routes_to_ogg_handler(self, tmp_path: Path) -> None:
        """Test that .ogg files are routed to OGG handler."""
        audio_file = tmp_path / "test.ogg"
        audio_file.touch()

        with patch("thumbnail.embed_thumbnail_ogg", return_value=True) as mock:
            result = embed_thumbnail(audio_file, b"image_data")

        mock.assert_called_once_with(audio_file, b"image_data")
        assert result is True

    def test_routes_to_ogg_handler_for_opus(self, tmp_path: Path) -> None:
        """Test that .opus files are routed to OGG handler."""
        audio_file = tmp_path / "test.opus"
        audio_file.touch()

        with patch("thumbnail.embed_thumbnail_ogg", return_value=True) as mock:
            result = embed_thumbnail(audio_file, b"image_data")

        mock.assert_called_once_with(audio_file, b"image_data")
        assert result is True

    def test_returns_false_for_unsupported_format(self, tmp_path: Path) -> None:
        """Test that unsupported formats return False."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        result = embed_thumbnail(audio_file, b"image_data")

        assert result is False


class TestEmbedThumbnailM4A:
    """Tests for embed_thumbnail_m4a function."""

    def test_embeds_thumbnail_successfully(self, tmp_path: Path) -> None:
        """Test successful thumbnail embedding in M4A."""
        audio_file = tmp_path / "test.m4a"

        mock_audio = MagicMock()
        mock_audio.tags = {}

        with patch("thumbnail.MP4", return_value=mock_audio):
            result = embed_thumbnail_m4a(audio_file, b"image_data")

        assert result is True
        assert "covr" in mock_audio.tags
        mock_audio.save.assert_called_once()

    def test_handles_exception(self, tmp_path: Path) -> None:
        """Test exception handling."""
        audio_file = tmp_path / "test.m4a"

        with patch("thumbnail.MP4", side_effect=Exception("Test error")):
            result = embed_thumbnail_m4a(audio_file, b"image_data")

        assert result is False


class TestEmbedThumbnailMP3:
    """Tests for embed_thumbnail_mp3 function."""

    def test_embeds_thumbnail_successfully(self, tmp_path: Path) -> None:
        """Test successful thumbnail embedding in MP3."""
        audio_file = tmp_path / "test.mp3"

        mock_tags = MagicMock()
        mock_audio = MagicMock()
        mock_audio.tags = mock_tags

        with patch("thumbnail.MP3", return_value=mock_audio):
            result = embed_thumbnail_mp3(audio_file, b"image_data")

        assert result is True
        mock_tags.delall.assert_called_once_with("APIC")
        mock_tags.add.assert_called_once()
        mock_audio.save.assert_called_once()

    def test_creates_tags_if_missing(self, tmp_path: Path) -> None:
        """Test that ID3 tags are created if missing."""
        audio_file = tmp_path / "test.mp3"

        mock_tags = MagicMock()
        mock_audio = MagicMock()
        # After add_tags is called, tags should be accessible
        mock_audio.tags = None

        def set_tags():
            mock_audio.tags = mock_tags

        mock_audio.add_tags.side_effect = set_tags

        with patch("thumbnail.MP3", return_value=mock_audio):
            result = embed_thumbnail_mp3(audio_file, b"image_data")

        assert result is True
        mock_audio.add_tags.assert_called_once()
        mock_tags.delall.assert_called_once_with("APIC")
        mock_tags.add.assert_called_once()

    def test_handles_exception(self, tmp_path: Path) -> None:
        """Test exception handling."""
        audio_file = tmp_path / "test.mp3"

        with patch("thumbnail.MP3", side_effect=Exception("Test error")):
            result = embed_thumbnail_mp3(audio_file, b"image_data")

        assert result is False


class TestEmbedThumbnailOGG:
    """Tests for embed_thumbnail_ogg function."""

    def _create_test_image(self) -> bytes:
        """Create a test image."""
        img = Image.new("RGB", (100, 100), color="red")
        output = io.BytesIO()
        img.save(output, format="JPEG")
        return output.getvalue()

    def test_uses_opus_for_opus_files(self, tmp_path: Path) -> None:
        """Test that OggOpus is used for .opus files."""
        audio_file = tmp_path / "test.opus"

        mock_audio = MagicMock()
        mock_audio.__setitem__ = MagicMock()

        with (
            patch("thumbnail.OggOpus", return_value=mock_audio) as mock_opus,
            patch("thumbnail.OggVorbis") as mock_vorbis,
        ):
            result = embed_thumbnail_ogg(audio_file, self._create_test_image())

        mock_opus.assert_called_once_with(audio_file)
        mock_vorbis.assert_not_called()
        assert result is True

    def test_uses_vorbis_for_ogg_files(self, tmp_path: Path) -> None:
        """Test that OggVorbis is used for .ogg files."""
        audio_file = tmp_path / "test.ogg"

        mock_audio = MagicMock()
        mock_audio.__setitem__ = MagicMock()

        with (
            patch("thumbnail.OggOpus") as mock_opus,
            patch("thumbnail.OggVorbis", return_value=mock_audio) as mock_vorbis,
        ):
            result = embed_thumbnail_ogg(audio_file, self._create_test_image())

        mock_vorbis.assert_called_once_with(audio_file)
        mock_opus.assert_not_called()
        assert result is True

    def test_handles_exception(self, tmp_path: Path) -> None:
        """Test exception handling."""
        audio_file = tmp_path / "test.ogg"

        with patch("thumbnail.OggVorbis", side_effect=Exception("Test error")):
            result = embed_thumbnail_ogg(audio_file, self._create_test_image())

        assert result is False


class TestProcessThumbnail:
    """Tests for process_thumbnail function."""

    def _create_test_image(self) -> bytes:
        """Create a test image."""
        img = Image.new("RGB", (200, 100), color="red")
        output = io.BytesIO()
        img.save(output, format="JPEG")
        return output.getvalue()

    def test_full_pipeline_success(self, tmp_path: Path) -> None:
        """Test successful full thumbnail processing pipeline."""
        audio_file = tmp_path / "test.m4a"
        audio_file.touch()

        with (
            patch("thumbnail.download_thumbnail", return_value=self._create_test_image()),
            patch("thumbnail.embed_thumbnail", return_value=True) as mock_embed,
        ):
            result = process_thumbnail("test_video_id", audio_file)

        assert result is True
        mock_embed.assert_called_once()
        # Check that the image was padded to square
        embedded_data = mock_embed.call_args[0][1]
        with Image.open(io.BytesIO(embedded_data)) as img:
            assert img.size[0] == img.size[1]  # Should be square

    def test_skips_unsupported_format(self, tmp_path: Path) -> None:
        """Test that unsupported formats are skipped early."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        with patch("thumbnail.download_thumbnail") as mock_download:
            result = process_thumbnail("test_video_id", audio_file)

        assert result is False
        mock_download.assert_not_called()

    def test_returns_false_on_download_failure(self, tmp_path: Path) -> None:
        """Test handling of thumbnail download failure."""
        audio_file = tmp_path / "test.m4a"
        audio_file.touch()

        with patch("thumbnail.download_thumbnail", return_value=None):
            result = process_thumbnail("test_video_id", audio_file)

        assert result is False

    def test_returns_false_on_embed_failure(self, tmp_path: Path) -> None:
        """Test handling of embed failure."""
        audio_file = tmp_path / "test.m4a"
        audio_file.touch()

        with (
            patch("thumbnail.download_thumbnail", return_value=self._create_test_image()),
            patch("thumbnail.embed_thumbnail", return_value=False),
        ):
            result = process_thumbnail("test_video_id", audio_file)

        assert result is False


class TestSupportedExtensions:
    """Tests for SUPPORTED_EXTENSIONS constant."""

    def test_contains_expected_extensions(self) -> None:
        """Test that expected extensions are in the set."""
        assert ".m4a" in SUPPORTED_EXTENSIONS
        assert ".mp4" in SUPPORTED_EXTENSIONS
        assert ".mp3" in SUPPORTED_EXTENSIONS
        assert ".ogg" in SUPPORTED_EXTENSIONS
        assert ".opus" in SUPPORTED_EXTENSIONS

    def test_excludes_unsupported(self) -> None:
        """Test that unsupported formats are not in the set."""
        assert ".wav" not in SUPPORTED_EXTENSIONS
        assert ".flac" not in SUPPORTED_EXTENSIONS
        assert ".aac" not in SUPPORTED_EXTENSIONS
