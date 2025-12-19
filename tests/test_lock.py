"""Tests for lock module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lock import (
    LockError,
    _is_process_running,
    acquire_lock,
    lock_context,
    release_lock,
)


class TestIsProcessRunning:
    """Tests for _is_process_running function."""

    def test_current_process_running(self) -> None:
        """Test that current process is detected as running."""
        assert _is_process_running(os.getpid()) is True

    def test_invalid_pid_not_running(self) -> None:
        """Test that invalid PID is not running."""
        # Use a very high PID that's unlikely to exist
        assert _is_process_running(999999999) is False

    def test_nonexistent_pid_not_running(self) -> None:
        """Test that nonexistent high PID is not running."""
        # Use a very high PID that shouldn't exist
        # (different from test_invalid_pid_not_running to avoid test overlap)
        assert _is_process_running(2147483647) is False


class TestAcquireLock:
    """Tests for acquire_lock function."""

    def test_acquire_new_lock(self, tmp_path: Path) -> None:
        """Test acquiring a new lock."""
        lock_file = tmp_path / "test.lock"

        result = acquire_lock(lock_file)

        assert result is True
        assert lock_file.exists()
        assert lock_file.read_text() == str(os.getpid())

    def test_acquire_stale_lock(self, tmp_path: Path) -> None:
        """Test acquiring a stale lock from dead process."""
        lock_file = tmp_path / "test.lock"
        # Create a lock with invalid PID
        lock_file.write_text("999999999")

        result = acquire_lock(lock_file)

        assert result is True
        assert lock_file.read_text() == str(os.getpid())

    def test_cannot_acquire_active_lock(self, tmp_path: Path) -> None:
        """Test that active lock cannot be acquired."""
        lock_file = tmp_path / "test.lock"
        # Create a lock with current process PID
        lock_file.write_text(str(os.getpid()))

        # Simulate another process trying to acquire
        with patch("lock.os.getpid", return_value=12345):
            result = acquire_lock(lock_file)

        assert result is False

    def test_handles_corrupted_lock_file(self, tmp_path: Path) -> None:
        """Test handling of corrupted lock file."""
        lock_file = tmp_path / "test.lock"
        lock_file.write_text("not_a_pid")

        result = acquire_lock(lock_file)

        assert result is True

    def test_handles_empty_lock_file(self, tmp_path: Path) -> None:
        """Test handling of empty lock file."""
        lock_file = tmp_path / "test.lock"
        lock_file.write_text("")

        result = acquire_lock(lock_file)

        assert result is True

    def test_handles_write_error(self, tmp_path: Path) -> None:
        """Test handling of write error."""
        lock_file = tmp_path / "test.lock"

        with patch.object(Path, "write_text", side_effect=OSError("Permission denied")):
            result = acquire_lock(lock_file)

        assert result is False


class TestReleaseLock:
    """Tests for release_lock function."""

    def test_release_own_lock(self, tmp_path: Path) -> None:
        """Test releasing own lock."""
        lock_file = tmp_path / "test.lock"
        lock_file.write_text(str(os.getpid()))

        result = release_lock(lock_file)

        assert result is True
        assert not lock_file.exists()

    def test_release_nonexistent_lock(self, tmp_path: Path) -> None:
        """Test releasing nonexistent lock."""
        lock_file = tmp_path / "test.lock"

        result = release_lock(lock_file)

        assert result is True

    def test_cannot_release_other_process_lock(self, tmp_path: Path) -> None:
        """Test that other process lock cannot be released."""
        lock_file = tmp_path / "test.lock"
        lock_file.write_text("99999")

        result = release_lock(lock_file)

        assert result is False
        assert lock_file.exists()

    def test_handles_read_error(self, tmp_path: Path) -> None:
        """Test handling of read error."""
        lock_file = tmp_path / "test.lock"
        lock_file.write_text(str(os.getpid()))

        with patch.object(Path, "read_text", side_effect=OSError("Read error")):
            result = release_lock(lock_file)

        assert result is False


class TestLockContext:
    """Tests for lock_context context manager."""

    def test_successful_lock_acquisition(self, tmp_path: Path) -> None:
        """Test successful lock acquisition and release."""
        lock_file = tmp_path / "test.lock"

        with lock_context(lock_file) as acquired:
            assert acquired is True
            assert lock_file.exists()

        assert not lock_file.exists()

    def test_failed_lock_acquisition(self, tmp_path: Path) -> None:
        """Test failed lock acquisition."""
        lock_file = tmp_path / "test.lock"
        # Create active lock from "another process"
        lock_file.write_text(str(os.getpid()))

        with patch("lock.os.getpid", return_value=12345):
            with lock_context(lock_file) as acquired:
                assert acquired is False

    def test_lock_released_on_exception(self, tmp_path: Path) -> None:
        """Test that lock is released on exception."""
        lock_file = tmp_path / "test.lock"

        with pytest.raises(ValueError), lock_context(lock_file) as acquired:
            assert acquired is True
            raise ValueError("Test error")

        assert not lock_file.exists()

    def test_nested_locks_not_allowed(self, tmp_path: Path) -> None:
        """Test that nested lock acquisition fails."""
        lock_file = tmp_path / "test.lock"

        with lock_context(lock_file) as outer_acquired:
            assert outer_acquired is True
            # Second lock attempt should fail (same process owns it)
            # but since it's the same process PID, it will see as active
            with patch("lock._is_process_running", return_value=True):
                with lock_context(lock_file) as inner_acquired:
                    assert inner_acquired is False


class TestLockError:
    """Tests for LockError exception."""

    def test_lock_error_message(self) -> None:
        """Test LockError exception message."""
        error = LockError("Unable to acquire lock")
        assert str(error) == "Unable to acquire lock"
