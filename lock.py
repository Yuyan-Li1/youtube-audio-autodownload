"""Lock file mechanism to prevent concurrent cron job runs.

Uses a simple file-based lock with PID verification to handle stale locks.
"""

import contextlib
import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

# Default lock file location
DEFAULT_LOCK_FILE = Path(__file__).parent / "youtube_downloader.lock"


class LockError(Exception):
    """Raised when unable to acquire lock."""

    pass


def acquire_lock(lock_file: Path = DEFAULT_LOCK_FILE) -> bool:
    """Attempt to acquire the lock.

    Args:
        lock_file: Path to the lock file.

    Returns:
        True if lock acquired, False if another instance is running.
    """
    # Check if lock file exists
    if lock_file.exists():
        try:
            # Read PID from lock file
            pid_str = lock_file.read_text().strip()
            if pid_str:
                pid = int(pid_str)
                # Check if process is still running
                if _is_process_running(pid):
                    logger.warning(f"Another instance is running (PID: {pid})")
                    return False
                else:
                    logger.info(f"Stale lock file found (PID {pid} not running), removing")
                    lock_file.unlink()
        except (ValueError, OSError) as e:
            logger.warning(f"Invalid lock file, removing: {e}")
            with contextlib.suppress(OSError):
                lock_file.unlink()

    # Create lock file with our PID
    try:
        lock_file.write_text(str(os.getpid()))
        logger.debug(f"Lock acquired (PID: {os.getpid()})")
        return True
    except OSError as e:
        logger.error(f"Failed to create lock file: {e}")
        return False


def release_lock(lock_file: Path = DEFAULT_LOCK_FILE) -> bool:
    """Release the lock.

    Args:
        lock_file: Path to the lock file.

    Returns:
        True if lock released, False on error.
    """
    try:
        if lock_file.exists():
            # Verify it's our lock before removing
            pid_str = lock_file.read_text().strip()
            if pid_str and int(pid_str) == os.getpid():
                lock_file.unlink()
                logger.debug("Lock released")
                return True
            else:
                logger.warning("Lock file belongs to different process, not removing")
                return False
        return True
    except (ValueError, OSError) as e:
        logger.error(f"Error releasing lock: {e}")
        return False


@contextmanager
def lock_context(lock_file: Path = DEFAULT_LOCK_FILE) -> Generator[bool, None, None]:
    """Context manager for lock acquisition.

    Usage:
        with lock_context() as acquired:
            if not acquired:
                return  # Another instance running
            # Do work...

    Args:
        lock_file: Path to the lock file.

    Yields:
        True if lock acquired, False otherwise.
    """
    acquired = acquire_lock(lock_file)
    try:
        yield acquired
    finally:
        if acquired:
            release_lock(lock_file)


def _is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is running.

    Args:
        pid: Process ID to check.

    Returns:
        True if process is running, False otherwise.
    """
    try:
        # On Unix, sending signal 0 checks if process exists
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        # On Windows or other platforms, assume not running if we can't check
        return False
