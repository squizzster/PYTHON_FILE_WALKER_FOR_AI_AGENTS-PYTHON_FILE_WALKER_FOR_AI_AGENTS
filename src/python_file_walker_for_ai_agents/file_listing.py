#!/usr/bin/env python3
"""List names or optional metadata in one Linux directory as JSON. Python >= 3.5.

No recursion, sorting, content reads, or temporary files. Symlinks are not
followed when classifying entries. The directory argument itself may be a
symlink. Output order is the filesystem's order, not a snapshot.

Successful data output is one ASCII JSON object with files, complete and errors.
On failure, discard stdout: a streamed object may be incomplete.
"""

import errno
import os
import sys

from .file_entries import FileObjectWriter, INODE, PERMISSIONS, STATS
from .filesystem import FD_SCANDIR, MINIMUM_PYTHON, close_scan, open_scan


HELP_FLAGS = frozenset(("-h", "--help", "-help"))
HELP_DOCUMENT = {
    "usage": "list_files_in_a_directory_to_json.py [OPTIONS] DIRECTORY",
    "does": "Emits entries from one Linux directory without recursion or sorting; default emits regular-file basenames including hidden files and excludes directories, symlinks, and special files.",
    "envelope": {"files": "object", "complete": "boolean", "errors": "integer"},
    "returns": {
        "default": {"field": "files.entries", "type": "array", "items": "string"},
        "--number": {"field": "files.count", "type": "integer"},
        "--inode": {"field": "files.entries", "type": "array", "items": {"name": "string", "inode": "integer"}},
        "--permissions": {"field": "files.entries", "type": "array", "items": {"name": "string", "mode": "integer", "permissions": "octal string", "uid": "integer", "gid": "integer"}},
        "--stats": {"field": "files.entries", "type": "array", "items": {"name": "string", "mode": "integer", "permissions": "octal string", "uid": "integer", "gid": "integer", "inode": "integer", "device": "integer", "type": "string", "nlink": "integer", "size": "integer", "atime_ns": "integer", "mtime_ns": "integer", "ctime_ns": "integer", "blocks_512": "integer|null", "blksize": "integer|null", "rdev": "integer|null"}},
    },
    "options": {
        "--all-entries": "include all entry types; never follow symlinks",
        "--base64": "encode raw filename bytes as base64 in name fields",
        "--inode": "add directory-entry inode; no stat with --all-entries",
        "--permissions": "add mode, permission bits, uid, and gid",
        "--stats": "include permissions, inode, and full stat fields",
        "--number": "return a count; incompatible with metadata options",
    },
    "aliases": {"-n": "--number", "--file-permissions-stats": "--stats", "--file_permissions_stats": "--stats"},
    "help": ["-h", "--help", "-help"],
    "option_terminator": "--",
}


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


def help_json(error=None):
    import json
    document = HELP_DOCUMENT if error is None else {
        "error": error, "help": HELP_DOCUMENT}
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"))


def parse_args(args):
    # Avoid argparse's import tree for this small, fixed CLI (not a pip module).
    directory = None
    number = False
    all_entries = False
    base64_names = False
    metadata = 0
    options = True
    for arg in args:
        if options and arg == "--":
            options = False
        elif options and arg in HELP_FLAGS:
            return None
        elif options and arg in ("-n", "--number"):
            number = True
        elif options and arg == "--all-entries":
            all_entries = True
        elif options and arg == "--inode":
            metadata |= INODE
        elif options and arg == "--permissions":
            metadata |= PERMISSIONS
        elif options and arg in ("--stats", "--file-permissions-stats",
                                 "--file_permissions_stats"):
            metadata |= INODE | PERMISSIONS | STATS
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
    if number and metadata:
        raise UsageError("--number cannot be combined with metadata options")
    return directory, number, all_entries, base64_names, metadata


def run(directory, number=False, all_entries=False, base64_names=False, metadata=0):
    if metadata < 0 or metadata & ~(INODE | PERMISSIONS | STATS):
        raise UsageError("invalid metadata flags")
    if number and metadata:
        raise UsageError("--number cannot be combined with metadata options")
    entries, directory_fd = open_scan(directory)
    if not number:
        write_all(1, b'{"files":')
    writer = FileObjectWriter(
        lambda data: write_all(1, data), number, all_entries,
        base64_names, metadata)
    try:
        for entry in entries:
            writer.add(entry)
    finally:
        close_scan(entries, directory_fd)
    if number:
        # No result is emitted before the complete count and cleanup succeed.
        write_all(1, b'{"files":')
    writer.finish()
    # The success envelope is completed only after enumeration and cleanup.
    write_all(1, b',"complete":true,"errors":0}\n')


def main(argv=None):
    try:
        if (not sys.platform.startswith("linux") or
                sys.version_info < MINIMUM_PYTHON or not hasattr(os, "scandir")):
            raise UsageError("Linux and Python 3.5 or newer are required")
        raw_args = sys.argv[1:] if argv is None else argv
        if not raw_args:
            diagnostic(help_json())
            return 2
        args = parse_args(raw_args)
        if args is None:
            diagnostic(help_json())
            return 0
        run(*args)
        return 0
    except UsageError as exc:
        diagnostic(help_json(str(exc)))
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
