#!/usr/bin/env python3
"""List regular-file names in one Linux directory as JSON. Python >= 3.5.

No recursion, sorting, content reads, or temporary files. Symlinks are not
followed when classifying entries. The directory argument itself may be a
symlink. Output order is the filesystem's order, not a snapshot.

Successful data output is one ASCII JSON array, or one integer with -n.
On failure, discard stdout: a streamed array may be incomplete.
"""

import errno
import os
import sys

# Limits the number of names retained, not the directory size. JSON encoding
# works on whole batches (using CPython's accelerator when available).
BATCH_SIZE = 4096
FD_SCANDIR = os.scandir in getattr(os, "supports_fd", ()) if hasattr(os, "scandir") else False

HELP = """Usage: list_files_in_a_directory_to_json.py [OPTIONS] DIRECTORY

List regular-file basenames, including hidden files, as a JSON array.
Exclude directories, symlinks, sockets, FIFOs and devices. Never recurse.

  -n, --number       Output a JSON integer instead of filenames.
      --all-entries  Include every directory entry except . and ..;
                     do not request per-entry file-type metadata.
      --base64       Encode each raw filename as a base64 ASCII string.
                     Useful for arbitrary bytes and non-Python JSON readers.
  -h, --help         Show this help on stderr; no JSON is produced.
      --            End options (for a directory name beginning with '-').

Options may appear before or after DIRECTORY. Exactly one directory is required.
Default names use Python's filesystem decoding and JSON ASCII escaping.
Python 3.7+ attempts O_NOATIME, falling back if unavailable/not permitted.
Python 3.5/3.6 uses path-based scandir, without O_NOATIME.

Exit: 0 success/help; 1 I/O/runtime failure; 2 usage/unsupported platform;
      130 interrupted; 141 broken output pipe. Discard stdout on any failure.
"""


class UsageError(Exception):
    pass


def write_all(fd, data):
    """Write bytes without TextIO encoding, buffering, or shutdown flush errors."""
    while True:
        try:
            written = os.write(fd, data)
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError(errno.EIO, "output write made no progress")
        if written == len(data):
            return
        # A short write is unusual on blocking stdout; allocate a view only then.
        data = memoryview(data)[written:]


def diagnostic(message):
    """Best effort, even with closed stderr or filenames containing raw bytes."""
    try:
        write_all(2, (message + "\n").encode("ascii", "backslashreplace"))
    except (OSError, ValueError):
        pass


def parse_args(args):
    # Avoid argparse's import tree for this small, fixed CLI (not a pip module).
    directory = None
    number = False
    all_entries = False
    base64_names = False
    options = True
    for arg in args:
        if options and arg == "--":
            options = False
        elif options and arg in ("-h", "--help"):
            return None
        elif options and arg in ("-n", "--number"):
            number = True
        elif options and arg == "--all-entries":
            all_entries = True
        elif options and arg == "--base64":
            base64_names = True
        elif options and arg.startswith("-") and arg != "-":
            raise UsageError("unknown option: " + ascii(arg))
        elif directory is None:
            directory = arg
        else:
            raise UsageError("exactly one directory is required")
    if directory is None:
        raise UsageError("a directory argument is required")
    return directory, number, all_entries, base64_names


def open_scan(directory):
    """Return (iterator, owned_fd_or_None), keeping fd-relative lookups valid."""
    if not FD_SCANDIR:
        return os.scandir(directory), None

    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    noatime = getattr(os, "O_NOATIME", 0)
    try:
        fd = os.open(directory, flags | noatime)
    except OSError as exc:
        # Only retry failures plausibly caused by O_NOATIME. No permission or
        # filesystem pre-checks: an unsuccessful open is the check itself.
        if not noatime or exc.errno not in (
            errno.EPERM, errno.EINVAL, errno.EOPNOTSUPP, errno.ENOSYS
        ):
            raise
        fd = os.open(directory, flags)
    try:
        return os.scandir(fd), fd
    except BaseException:
        os.close(fd)
        raise


def count_entries(entries, all_entries=False):
    if all_entries:
        return sum(1 for entry in entries)
    return sum(1 for entry in entries if entry.is_file(follow_symlinks=False))


def write_listing(entries, all_entries=False, base64_names=False, fd=1):
    # Count mode never imports json, itertools, or base64.
    import itertools
    import json

    encoder = json.JSONEncoder(ensure_ascii=True, separators=(",", ":"))
    encode = encoder.encode
    if all_entries:
        names = (entry.name for entry in entries)
    else:
        names = (entry.name for entry in entries
                 if entry.is_file(follow_symlinks=False))
    if base64_names:
        import base64
        # fsencode reverses filesystem decoding, including surrogateescape.
        names = (base64.b64encode(os.fsencode(name)).decode("ascii")
                 for name in names)

    prefix = "["
    while True:
        batch = list(itertools.islice(names, BATCH_SIZE))
        if not batch:
            break
        # Remove only the batch's brackets; keep the standard JSON encoder
        # responsible for escaping every filename. One write per batch normally.
        payload = (prefix + encode(batch)[1:-1]).encode("ascii")
        write_all(fd, payload)
        prefix = ","
    # Do not write the final bracket on an enumeration or encoding failure.
    write_all(fd, b"[]\n" if prefix == "[" else b"]\n")


def run(directory, number=False, all_entries=False, base64_names=False):
    entries, directory_fd = open_scan(directory)
    try:
        if number:
            count = count_entries(entries, all_entries)
        else:
            write_listing(entries, all_entries, base64_names)
    finally:
        # close() was added in 3.6. On CPython 3.5 exhaustion/destruction closes
        # the iterator; this function does not retain it after returning.
        try:
            close = getattr(entries, "close", None)
            if close is not None:
                close()
        finally:
            if directory_fd is not None:
                os.close(directory_fd)
    if number:
        # No result is emitted before the complete count and cleanup succeed.
        write_all(1, (str(count) + "\n").encode("ascii"))


def main(argv=None):
    try:
        if not sys.platform.startswith("linux") or not hasattr(os, "scandir"):
            raise UsageError("Linux and Python 3.5 or newer are required")
        args = parse_args(sys.argv[1:] if argv is None else argv)
        if args is None:
            diagnostic(HELP.rstrip())
            return 0
        run(*args)
        return 0
    except UsageError as exc:
        diagnostic("error: " + str(exc) + "\nUse --help for usage.")
        return 2
    except BrokenPipeError:
        diagnostic("error: broken output pipe")
        return 141
    except KeyboardInterrupt:
        diagnostic("error: interrupted")
        return 130
    except MemoryError:
        diagnostic("error: insufficient memory")
        return 1
    except Exception as exc:
        # Escape control characters too: filenames must not inject terminal
        # control sequences into diagnostics. Do not put error objects on stdout.
        diagnostic("error: " + type(exc).__name__ + ": " + ascii(str(exc)))
        return 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
