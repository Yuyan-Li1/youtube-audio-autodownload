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
                    logger.warning("Another instance is running (PID: %s)", pid)
                    return False
                else:
                    logger.info("Stale lock file found (PID %s not running), removing", pid)
                    lock_file.unlink()
        except (ValueError, OSError) as e:
            logger.warning("Invalid lock file, removing: %s", e)
            with contextlib.suppress(OSError):
                lock_file.unlink()

    # Create lock file with our PID
    try:
        lock_file.write_text(str(os.getpid()))
        logger.debug("Lock acquired (PID: %s)", os.getpid())
        return True
    except OSError as e:
        logger.error("Failed to create lock file: %s", e)
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
        logger.error("Error releasing lock: %s", e)
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
    except (ValueError, TypeError):
        # Invalid PID type or value
        return False
