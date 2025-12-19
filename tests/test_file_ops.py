"""Tests for file_ops module."""

from pathlib import Path
from unittest.mock import patch

from file_ops import (
    BatchMoveResult,
    MoveResult,
    ensure_directory,
    list_files,
    move_audio_files,
    move_file,
)


class TestMoveResult:
    """Tests for MoveResult dataclass."""

    def test_successful_result(self, tmp_path: Path) -> None:
        """Test creating a successful MoveResult."""
        result = MoveResult(
            source=tmp_path / "source.m4a",
            destination=tmp_path / "dest.m4a",
            success=True,
        )

        assert result.success is True
        assert result.error is None

    def test_failed_result(self, tmp_path: Path) -> None:
        """Test creating a failed MoveResult."""
        result = MoveResult(
            source=tmp_path / "source.m4a",
            destination=tmp_path / "dest.m4a",
            success=False,
            error="Permission denied",
        )

        assert result.success is False
        assert result.error == "Permission denied"


class TestBatchMoveResult:
    """Tests for BatchMoveResult dataclass."""

    def test_properties(self, tmp_path: Path) -> None:
        """Test BatchMoveResult properties."""
        result = BatchMoveResult(
            successful=[
                MoveResult(tmp_path / "a.m4a", tmp_path / "dest/a.m4a", True),
                MoveResult(tmp_path / "b.m4a", tmp_path / "dest/b.m4a", True),
            ],
            failed=[
                MoveResult(tmp_path / "c.m4a", tmp_path / "dest/c.m4a", False, "Error"),
            ],
        )

        assert result.total == 3
        assert result.success_count == 2
        assert result.failure_count == 1


class TestMoveFile:
    """Tests for move_file function."""

    def test_successful_move(self, tmp_path: Path) -> None:
        """Test successful file move."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        source_file = source_dir / "test.m4a"
        source_file.write_text("test content")

        result = move_file(source_file, target_dir)

        assert result.success is True
        assert not source_file.exists()
        assert (target_dir / "test.m4a").exists()

    def test_failed_move(self, tmp_path: Path) -> None:
        """Test failed file move."""
        source_file = tmp_path / "nonexistent.m4a"
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        result = move_file(source_file, target_dir)

        assert result.success is False
        assert result.error is not None


class TestMoveAudioFiles:
    """Tests for move_audio_files function."""

    def test_moves_audio_files(self, tmp_path: Path) -> None:
        """Test moving multiple audio files."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        # Create test audio files
        (source_dir / "audio1.m4a").write_text("audio1")
        (source_dir / "audio2.mp3").write_text("audio2")
        (source_dir / "audio3.opus").write_text("audio3")

        result = move_audio_files(source_dir, target_dir)

        assert result.success_count == 3
        assert result.failure_count == 0
        assert (target_dir / "audio1.m4a").exists()
        assert (target_dir / "audio2.mp3").exists()
        assert (target_dir / "audio3.opus").exists()

    def test_only_moves_audio_extensions(self, tmp_path: Path) -> None:
        """Test that only audio files are moved."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        # Create audio and non-audio files
        (source_dir / "audio.m4a").write_text("audio")
        (source_dir / "document.txt").write_text("text")
        (source_dir / "image.jpg").write_text("image")

        result = move_audio_files(source_dir, target_dir)

        assert result.success_count == 1
        assert (target_dir / "audio.m4a").exists()
        assert not (target_dir / "document.txt").exists()
        assert not (target_dir / "image.jpg").exists()

    def test_custom_extensions(self, tmp_path: Path) -> None:
        """Test using custom audio extensions."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        (source_dir / "audio.m4a").write_text("audio")
        (source_dir / "audio.custom").write_text("custom")

        result = move_audio_files(source_dir, target_dir, audio_extensions={".custom"})

        assert result.success_count == 1
        assert (target_dir / "audio.custom").exists()
        assert not (target_dir / "audio.m4a").exists()

    def test_source_dir_not_exists(self, tmp_path: Path) -> None:
        """Test handling of nonexistent source directory."""
        source_dir = tmp_path / "nonexistent"
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        result = move_audio_files(source_dir, target_dir)

        assert result.total == 0

    def test_target_dir_not_exists(self, tmp_path: Path) -> None:
        """Test handling of nonexistent target directory."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "nonexistent"
        source_dir.mkdir()

        (source_dir / "audio.m4a").write_text("audio")

        result = move_audio_files(source_dir, target_dir)

        assert result.total == 0

    def test_no_audio_files(self, tmp_path: Path) -> None:
        """Test handling when no audio files exist."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        (source_dir / "document.txt").write_text("text")

        result = move_audio_files(source_dir, target_dir)

        assert result.total == 0

    def test_empty_source_dir(self, tmp_path: Path) -> None:
        """Test handling of empty source directory."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        result = move_audio_files(source_dir, target_dir)

        assert result.total == 0


class TestEnsureDirectory:
    """Tests for ensure_directory function."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """Test creating a new directory."""
        new_dir = tmp_path / "new_directory"

        result = ensure_directory(new_dir)

        assert result is True
        assert new_dir.exists()

    def test_existing_directory(self, tmp_path: Path) -> None:
        """Test with existing directory."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()

        result = ensure_directory(existing_dir)

        assert result is True

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test creating nested directories."""
        nested_dir = tmp_path / "a" / "b" / "c"

        result = ensure_directory(nested_dir)

        assert result is True
        assert nested_dir.exists()

    def test_handles_error(self, tmp_path: Path) -> None:
        """Test handling of creation errors."""
        with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
            result = ensure_directory(tmp_path / "new_dir")

        assert result is False


class TestListFiles:
    """Tests for list_files function."""

    def test_lists_all_files(self, tmp_path: Path) -> None:
        """Test listing all files in directory."""
        (tmp_path / "file1.txt").write_text("1")
        (tmp_path / "file2.txt").write_text("2")
        (tmp_path / "file3.m4a").write_text("3")

        result = list_files(tmp_path)

        assert len(result) == 3

    def test_filters_by_extension(self, tmp_path: Path) -> None:
        """Test filtering files by extension."""
        (tmp_path / "file1.txt").write_text("1")
        (tmp_path / "file2.m4a").write_text("2")
        (tmp_path / "file3.mp3").write_text("3")

        result = list_files(tmp_path, extensions={".m4a", ".mp3"})

        assert len(result) == 2

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test listing nonexistent directory."""
        result = list_files(tmp_path / "nonexistent")

        assert result == []

    def test_ignores_subdirectories(self, tmp_path: Path) -> None:
        """Test that subdirectories are not included."""
        (tmp_path / "file.txt").write_text("file")
        (tmp_path / "subdir").mkdir()

        result = list_files(tmp_path)

        assert len(result) == 1
        assert result[0].name == "file.txt"
