"""Shared low-impact Linux directory opening and enumeration primitives."""

import errno
import os


MINIMUM_PYTHON = (3, 5)
FD_SCANDIR = (os.scandir in getattr(os, "supports_fd", ())
              if hasattr(os, "scandir") else False)
NOATIME_RETRY = frozenset((
    errno.EPERM,
    errno.EINVAL,
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    getattr(errno, "ENOSYS", errno.EINVAL),
))


def open_directory(name, parent_fd=None, nofollow=False, noatime=True):
    """Open one directory with the common descriptor and atime policy.

    O_NOATIME avoids changing directory access times when ownership and the
    filesystem permit it. Only errors plausibly caused by O_NOATIME retry
    without that flag. Child traversal can require O_NOFOLLOW atomically.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    if nofollow:
        flags |= os.O_NOFOLLOW
    atime_flag = getattr(os, "O_NOATIME", 0) if noatime else 0
    if atime_flag:
        try:
            return os.open(name, flags | atime_flag, dir_fd=parent_fd)
        except OSError as exc:
            if exc.errno not in NOATIME_RETRY:
                raise
    return os.open(name, flags, dir_fd=parent_fd)


def open_scan(directory):
    """Return an iterator and its owned fd for one non-recursive scan."""
    if not FD_SCANDIR:
        return os.scandir(directory), None
    fd = open_directory(directory)
    try:
        return os.scandir(fd), fd
    except BaseException:
        os.close(fd)
        raise


def close_scan(entries, directory_fd):
    """Close a scandir iterator and its separately owned descriptor."""
    try:
        # close() was added in 3.6. CPython 3.5 closes on exhaustion or
        # destruction; callers retain no reference after this function.
        close = getattr(entries, "close", None)
        if close is not None:
            close()
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
