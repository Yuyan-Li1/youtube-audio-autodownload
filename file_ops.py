# -*- coding: utf-8 -*-
"""File operations module for moving downloaded audio files.

Contains functions for moving files from download directory to target directory.
"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MoveResult:
    """Result of a file move operation."""

    source: Path
    destination: Path
    success: bool
    error: Optional[str] = None


@dataclass
class BatchMoveResult:
    """Result of moving multiple files."""

    successful: list[MoveResult] = field(default_factory=list)
    failed: list[MoveResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of move attempts."""
        return len(self.successful) + len(self.failed)

    @property
    def success_count(self) -> int:
        """Number of successful moves."""
        return len(self.successful)

    @property
    def failure_count(self) -> int:
        """Number of failed moves."""
        return len(self.failed)


def move_file(source: Path, target_dir: Path) -> MoveResult:
    """Move a single file to the target directory.

    Args:
        source: Path to the source file.
        target_dir: Directory to move the file to.

    Returns:
        MoveResult indicating success or failure.
    """
    destination = target_dir / source.name

    try:
        shutil.move(str(source), str(destination))
        logger.debug(f"Moved: {source.name}")
        return MoveResult(
            source=source,
            destination=destination,
            success=True,
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to move {source.name}: {error_msg}")
        return MoveResult(
            source=source,
            destination=destination,
            success=False,
            error=error_msg,
        )


def move_audio_files(
    source_dir: Path,
    target_dir: Path,
    audio_extensions: frozenset[str] | set[str] | None = None,
) -> BatchMoveResult:
    """Move all audio files from source to target directory.

    Args:
        source_dir: Directory containing downloaded audio files.
        target_dir: Directory to move files to.
        audio_extensions: Set of audio file extensions to move (e.g., {".m4a", ".mp3"}).
                         If None, uses default set.

    Returns:
        BatchMoveResult with successful and failed moves.
    """
    result = BatchMoveResult()

    # Use provided extensions or default set (including .flac)
    if audio_extensions is None:
        audio_extensions = {".m4a", ".mp3", ".opus", ".webm", ".aac", ".ogg", ".wav", ".flac"}

    if not source_dir.exists():
        logger.warning(f"Source directory does not exist: {source_dir}")
        return result

    if not target_dir.exists():
        logger.error(f"Target directory does not exist: {target_dir}")
        return result

    # Get all files in source directory
    files = [f for f in source_dir.iterdir() if f.is_file()]

    if not files:
        logger.info("No files to move")
        return result

    # Filter to audio files only (optional - can move all files)
    audio_files = [f for f in files if f.suffix.lower() in audio_extensions]

    if not audio_files:
        logger.info("No audio files found to move")
        return result

    logger.info(f"Moving {len(audio_files)} audio file(s) to {target_dir}")

    for source_file in audio_files:
        move_result = move_file(source_file, target_dir)

        if move_result.success:
            result.successful.append(move_result)
        else:
            result.failed.append(move_result)

    logger.info(
        f"Move complete: {result.success_count} successful, "
        f"{result.failure_count} failed"
    )

    return result


def ensure_directory(path: Path) -> bool:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Path to the directory.

    Returns:
        True if directory exists or was created, False on error.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False


def list_files(directory: Path, extensions: Optional[set[str]] = None) -> list[Path]:
    """List files in a directory, optionally filtered by extension.

    Args:
        directory: Directory to list.
        extensions: Optional set of extensions to filter (e.g., {".m4a", ".mp3"}).

    Returns:
        List of file paths.
    """
    if not directory.exists():
        return []

    files = [f for f in directory.iterdir() if f.is_file()]

    if extensions:
        files = [f for f in files if f.suffix.lower() in extensions]

    return files
