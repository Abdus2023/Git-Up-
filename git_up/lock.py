"""Exclusive non-blocking lease (component L)."""

from __future__ import annotations

import errno
import os
from pathlib import Path

from .errors import LockAcquisitionError

try:
    import fcntl as _fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _fcntl = None
    _HAVE_FCNTL = False


class FileLock:
    def __init__(self, path, blocking: bool = False):
        self.path = Path(path)
        self.blocking = blocking
        self._fd = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not _HAVE_FCNTL:
            try:
                flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
                self._fd = os.open(str(self.path), flags, 0o600)
            except OSError as e:
                if e.errno == errno.EEXIST:
                    raise LockAcquisitionError(
                        "another controller holds the lease") from e
                raise
            return self

        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        op = _fcntl.LOCK_EX if self.blocking else _fcntl.LOCK_EX | _fcntl.LOCK_NB
        try:
            _fcntl.flock(fd, op)
        except BlockingIOError as e:
            os.close(fd)
            raise LockAcquisitionError(
                "another controller holds the lease") from e
        except OSError as e:
            os.close(fd)
            raise LockAcquisitionError(f"lock failed: {e}") from e
        self._fd = fd
        return self

    def release(self):
        if self._fd is None:
            return
        try:
            if _HAVE_FCNTL:
                try:
                    _fcntl.flock(self._fd, _fcntl.LOCK_UN)
                except OSError:
                    pass
            os.close(self._fd)
        finally:
            self._fd = None
            try:
                self.path.unlink()
            except OSError:
                pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
