"""Tests for chapters module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from chapters import (
    SUPPORTED_EXTENSIONS,
    Chapter,
    _create_ffmpeg_metadata,
    embed_chapters,
    embed_chapters_m4a,
    embed_chapters_mp3,
    extract_chapters,
    process_chapters,
)


class TestChapter:
    """Tests for Chapter dataclass."""

    def test_chapter_creation(self) -> None:
        """Test creating a Chapter object."""
        chapter = Chapter(title="Introduction", start_time=0.0, end_time=60.0)
        assert chapter.title == "Introduction"
        assert chapter.start_time == 0.0
        assert chapter.end_time == 60.0


class TestExtractChapters:
    """Tests for extract_chapters function."""

    def test_extracts_chapters_from_info_dict(self) -> None:
        """Test extracting chapters from yt-dlp info_dict."""
        info_dict = {
            "chapters": [
                {"title": "Intro", "start_time": 0, "end_time": 60},
                {"title": "Main Content", "start_time": 60, "end_time": 300},
                {"title": "Outro", "start_time": 300, "end_time": 360},
            ]
        }

        chapters = extract_chapters(info_dict)

        assert len(chapters) == 3
        assert chapters[0].title == "Intro"
        assert chapters[0].start_time == 0.0
        assert chapters[0].end_time == 60.0
        assert chapters[1].title == "Main Content"
        assert chapters[2].title == "Outro"

    def test_returns_empty_list_when_no_chapters(self) -> None:
        """Test that empty list is returned when no chapters."""
        info_dict = {"title": "Video Title"}

        chapters = extract_chapters(info_dict)

        assert chapters == []

    def test_returns_empty_list_when_chapters_is_none(self) -> None:
        """Test handling of None chapters."""
        info_dict = {"chapters": None}

        chapters = extract_chapters(info_dict)

        assert chapters == []

    def test_returns_empty_list_when_chapters_is_empty(self) -> None:
        """Test handling of empty chapters list."""
        info_dict = {"chapters": []}

        chapters = extract_chapters(info_dict)

        assert chapters == []

    def test_skips_chapters_without_title(self) -> None:
        """Test that chapters without titles are skipped."""
        info_dict = {
            "chapters": [
                {"title": "Valid", "start_time": 0, "end_time": 60},
                {"title": "", "start_time": 60, "end_time": 120},
                {"start_time": 120, "end_time": 180},
            ]
        }

        chapters = extract_chapters(info_dict)

        assert len(chapters) == 1
        assert chapters[0].title == "Valid"

    def test_skips_chapters_with_invalid_times(self) -> None:
        """Test that chapters with invalid times are skipped."""
        info_dict = {
            "chapters": [
                {"title": "Valid", "start_time": 0, "end_time": 60},
                {"title": "Invalid", "start_time": 60, "end_time": 60},
                {"title": "Negative", "start_time": 120, "end_time": 100},
            ]
        }

        chapters = extract_chapters(info_dict)

        assert len(chapters) == 1
        assert chapters[0].title == "Valid"

    def test_handles_float_times(self) -> None:
        """Test handling of floating point times."""
        info_dict = {
            "chapters": [
                {"title": "Chapter", "start_time": 0.5, "end_time": 60.75},
            ]
        }

        chapters = extract_chapters(info_dict)

        assert len(chapters) == 1
        assert chapters[0].start_time == 0.5
        assert chapters[0].end_time == 60.75


class TestCreateFfmpegMetadata:
    """Tests for _create_ffmpeg_metadata function."""

    def test_creates_valid_metadata(self) -> None:
        """Test creating valid ffmpeg metadata format."""
        chapters = [
            Chapter(title="Intro", start_time=0.0, end_time=60.0),
            Chapter(title="Main", start_time=60.0, end_time=300.0),
        ]

        metadata = _create_ffmpeg_metadata(chapters)

        assert ";FFMETADATA1" in metadata
        assert "[CHAPTER]" in metadata
        assert "TIMEBASE=1/1000" in metadata
        assert "START=0" in metadata
        assert "END=60000" in metadata
        assert "title=Intro" in metadata
        assert "START=60000" in metadata
        assert "END=300000" in metadata
        assert "title=Main" in metadata

    def test_escapes_special_characters(self) -> None:
        """Test that special characters are escaped."""
        chapters = [
            Chapter(title="Title=with;special#chars", start_time=0.0, end_time=60.0),
        ]

        metadata = _create_ffmpeg_metadata(chapters)

        assert "title=Title\\=with\\;special\\#chars" in metadata

    def test_escapes_backslashes(self) -> None:
        """Test that backslashes are escaped."""
        chapters = [
            Chapter(title="Path\\to\\file", start_time=0.0, end_time=60.0),
        ]

        metadata = _create_ffmpeg_metadata(chapters)

        assert "title=Path\\\\to\\\\file" in metadata


class TestEmbedChaptersMp3:
    """Tests for embed_chapters_mp3 function."""

    def test_embeds_chapters_successfully(self, tmp_path: Path) -> None:
        """Test successful chapter embedding in MP3."""
        audio_file = tmp_path / "test.mp3"
        chapters = [
            Chapter(title="Intro", start_time=0.0, end_time=60.0),
            Chapter(title="Main", start_time=60.0, end_time=300.0),
        ]

        mock_tags = MagicMock()
        mock_audio = MagicMock()
        mock_audio.tags = mock_tags

        with patch("chapters.MP3", return_value=mock_audio):
            result = embed_chapters_mp3(audio_file, chapters)

        assert result is True
        mock_tags.delall.assert_any_call("CHAP")
        mock_tags.delall.assert_any_call("CTOC")
        assert mock_tags.add.call_count == 3  # 2 CHAP + 1 CTOC
        mock_audio.save.assert_called_once()

    def test_creates_tags_if_missing(self, tmp_path: Path) -> None:
        """Test that ID3 tags are created if missing."""
        audio_file = tmp_path / "test.mp3"
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        mock_tags = MagicMock()
        mock_audio = MagicMock()
        mock_audio.tags = None

        def set_tags() -> None:
            mock_audio.tags = mock_tags

        mock_audio.add_tags.side_effect = set_tags

        with patch("chapters.MP3", return_value=mock_audio):
            result = embed_chapters_mp3(audio_file, chapters)

        assert result is True
        mock_audio.add_tags.assert_called_once()

    def test_handles_exception(self, tmp_path: Path) -> None:
        """Test exception handling."""
        audio_file = tmp_path / "test.mp3"
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        with patch("chapters.MP3", side_effect=Exception("Test error")):
            result = embed_chapters_mp3(audio_file, chapters)

        assert result is False

    def test_converts_times_to_milliseconds(self, tmp_path: Path) -> None:
        """Test that times are converted to milliseconds."""
        audio_file = tmp_path / "test.mp3"
        chapters = [Chapter(title="Intro", start_time=1.5, end_time=60.5)]

        mock_tags = MagicMock()
        mock_audio = MagicMock()
        mock_audio.tags = mock_tags

        with patch("chapters.MP3", return_value=mock_audio):
            embed_chapters_mp3(audio_file, chapters)

        chap_call = mock_tags.add.call_args_list[0]
        chap_frame = chap_call[0][0]
        assert chap_frame.start_time == 1500
        assert chap_frame.end_time == 60500


class TestEmbedChaptersM4a:
    """Tests for embed_chapters_m4a function."""

    def test_embeds_chapters_successfully(self, tmp_path: Path) -> None:
        """Test successful chapter embedding in M4A."""
        audio_file = tmp_path / "test.m4a"
        audio_file.touch()
        chapters = [
            Chapter(title="Intro", start_time=0.0, end_time=60.0),
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            with patch("pathlib.Path.replace"):
                result = embed_chapters_m4a(audio_file, chapters)

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "ffmpeg" in call_args[0][0]
        assert "-map_chapters" in call_args[0][0]

    def test_handles_ffmpeg_failure(self, tmp_path: Path) -> None:
        """Test handling of ffmpeg failure."""
        audio_file = tmp_path / "test.m4a"
        audio_file.touch()
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Error")
            result = embed_chapters_m4a(audio_file, chapters)

        assert result is False

    def test_handles_ffmpeg_not_found(self, tmp_path: Path) -> None:
        """Test handling of ffmpeg not being installed."""
        audio_file = tmp_path / "test.m4a"
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = embed_chapters_m4a(audio_file, chapters)

        assert result is False

    def test_handles_timeout(self, tmp_path: Path) -> None:
        """Test handling of ffmpeg timeout."""
        import subprocess

        audio_file = tmp_path / "test.m4a"
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 120)):
            result = embed_chapters_m4a(audio_file, chapters)

        assert result is False

    def test_cleans_up_temp_files_on_failure(self, tmp_path: Path) -> None:
        """Test that temporary files are cleaned up on failure."""
        audio_file = tmp_path / "test.m4a"
        audio_file.touch()
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Error")
            embed_chapters_m4a(audio_file, chapters)

        temp_files = list(tmp_path.glob("*.tmp.*"))
        assert len(temp_files) == 0


class TestEmbedChapters:
    """Tests for embed_chapters function."""

    def test_routes_to_mp3_handler(self, tmp_path: Path) -> None:
        """Test that .mp3 files are routed to MP3 handler."""
        audio_file = tmp_path / "test.mp3"
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        with patch("chapters.embed_chapters_mp3", return_value=True) as mock:
            result = embed_chapters(audio_file, chapters)

        mock.assert_called_once_with(audio_file, chapters)
        assert result is True

    def test_routes_to_m4a_handler(self, tmp_path: Path) -> None:
        """Test that .m4a files are routed to M4A handler."""
        audio_file = tmp_path / "test.m4a"
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        with patch("chapters.embed_chapters_m4a", return_value=True) as mock:
            result = embed_chapters(audio_file, chapters)

        mock.assert_called_once_with(audio_file, chapters)
        assert result is True

    def test_routes_to_m4a_handler_for_mp4(self, tmp_path: Path) -> None:
        """Test that .mp4 files are routed to M4A handler."""
        audio_file = tmp_path / "test.mp4"
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        with patch("chapters.embed_chapters_m4a", return_value=True) as mock:
            result = embed_chapters(audio_file, chapters)

        mock.assert_called_once_with(audio_file, chapters)
        assert result is True

    def test_returns_false_for_unsupported_format(self, tmp_path: Path) -> None:
        """Test that unsupported formats return False."""
        audio_file = tmp_path / "test.ogg"
        chapters = [Chapter(title="Intro", start_time=0.0, end_time=60.0)]

        result = embed_chapters(audio_file, chapters)

        assert result is False


class TestProcessChapters:
    """Tests for process_chapters function."""

    def test_full_pipeline_success(self, tmp_path: Path) -> None:
        """Test successful full chapter processing pipeline."""
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()
        info_dict = {
            "chapters": [
                {"title": "Intro", "start_time": 0, "end_time": 60},
                {"title": "Main", "start_time": 60, "end_time": 300},
            ]
        }

        with patch("chapters.embed_chapters", return_value=True) as mock_embed:
            result = process_chapters(info_dict, audio_file)

        assert result is True
        mock_embed.assert_called_once()
        chapters_arg = mock_embed.call_args[0][1]
        assert len(chapters_arg) == 2

    def test_skips_unsupported_format(self, tmp_path: Path) -> None:
        """Test that unsupported formats are skipped early."""
        audio_file = tmp_path / "test.ogg"
        audio_file.touch()
        info_dict = {"chapters": [{"title": "Intro", "start_time": 0, "end_time": 60}]}

        with patch("chapters.extract_chapters") as mock_extract:
            result = process_chapters(info_dict, audio_file)

        assert result is False
        mock_extract.assert_not_called()

    def test_returns_false_when_no_chapters(self, tmp_path: Path) -> None:
        """Test handling of videos without chapters."""
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()
        info_dict = {"title": "Video without chapters"}

        with patch("chapters.embed_chapters") as mock_embed:
            result = process_chapters(info_dict, audio_file)

        assert result is False
        mock_embed.assert_not_called()

    def test_returns_false_on_embed_failure(self, tmp_path: Path) -> None:
        """Test handling of embed failure."""
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()
        info_dict = {"chapters": [{"title": "Intro", "start_time": 0, "end_time": 60}]}

        with patch("chapters.embed_chapters", return_value=False):
            result = process_chapters(info_dict, audio_file)

        assert result is False


class TestSupportedExtensions:
    """Tests for SUPPORTED_EXTENSIONS constant."""

    def test_contains_expected_extensions(self) -> None:
        """Test that expected extensions are in the set."""
        assert ".mp3" in SUPPORTED_EXTENSIONS
        assert ".m4a" in SUPPORTED_EXTENSIONS
        assert ".mp4" in SUPPORTED_EXTENSIONS

    def test_excludes_unsupported(self) -> None:
        """Test that unsupported formats are not in the set."""
        assert ".ogg" not in SUPPORTED_EXTENSIONS
        assert ".opus" not in SUPPORTED_EXTENSIONS
        assert ".wav" not in SUPPORTED_EXTENSIONS
        assert ".flac" not in SUPPORTED_EXTENSIONS
