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

# Limits the number of names retained, not the directory size. JSON encoding
# works on whole batches (using CPython's accelerator when available).
BATCH_SIZE = 4096
# Metadata objects are larger than names: keep a smaller bounded batch.
METADATA_BATCH_SIZE = 512
MINIMUM_PYTHON = (3, 5)
# Internal bit flags; --stats includes permissions and inode automatically.
INODE = 1
PERMISSIONS = 2
STATS = 4
FD_SCANDIR = os.scandir in getattr(os, "supports_fd", ()) if hasattr(os, "scandir") else False
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
    write_all(fd, b"[]" if prefix == "[" else b"]")


def metadata_records(entries, metadata, all_entries=False, base64_names=False):
    """Yield small dictionaries; no content reads or ownership-name lookups.

    inode-only uses dirent.d_ino. When stat is requested, inode comes from the
    same stat_result as all other metadata, never a potentially stale d_ino.
    """
    if base64_names:
        import base64
        def encode_name(name):
            return base64.b64encode(os.fsencode(name)).decode("ascii")
    else:
        encode_name = None

    # Inode-only: no stat() calls here. Regular-file filtering can still need
    # a fallback lookup on DT_UNKNOWN; --all-entries avoids that too.
    if not metadata & (PERMISSIONS | STATS):
        for entry in entries:
            if not all_entries and not entry.is_file(follow_symlinks=False):
                continue
            name = entry.name
            if encode_name is not None:
                name = encode_name(name)
            yield {"name": name, "inode": entry.inode()}
        return

    import stat
    is_regular = stat.S_ISREG
    include_inode = bool(metadata & (INODE | STATS))
    full_stats = bool(metadata & STATS)
    if full_stats:
        file_type = stat.S_IFMT
        type_names = {
            stat.S_IFREG: "file", stat.S_IFDIR: "directory",
            stat.S_IFLNK: "symlink", stat.S_IFIFO: "fifo",
            stat.S_IFSOCK: "socket", stat.S_IFCHR: "character",
            stat.S_IFBLK: "block",
        }

    for entry in entries:
        # This skips known non-files without statting them. If DT_UNKNOWN
        # caused is_file() to stat already, the next call reuses its cache.
        if not all_entries and not entry.is_file(follow_symlinks=False):
            continue
        info = entry.stat(follow_symlinks=False)
        mode = info.st_mode
        # is_file() can reflect an older directory entry. A replacement must
        # not make a symlink/directory record leak into regular-file mode.
        if not all_entries and not is_regular(mode):
            continue
        name = entry.name
        if encode_name is not None:
            name = encode_name(name)
        record = {"name": name, "mode": mode, "permissions": "%04o" % (mode & 0o7777),
                  "uid": info.st_uid, "gid": info.st_gid}
        if include_inode:
            record["inode"] = info.st_ino
        if full_stats:
            record.update(
                device=info.st_dev, type=type_names.get(file_type(mode), "unknown"),
                nlink=info.st_nlink, size=info.st_size,
                atime_ns=info.st_atime_ns, mtime_ns=info.st_mtime_ns,
                ctime_ns=info.st_ctime_ns,
                # Linux normally exposes all three. A Python build missing an
                # optional member yields null, never an invented zero.
                blocks_512=getattr(info, "st_blocks", None),
                blksize=getattr(info, "st_blksize", None),
                rdev=getattr(info, "st_rdev", None))
        yield record


def write_metadata(entries, metadata, all_entries=False, base64_names=False, fd=1):
    """Separate bounded serializer: the original name-only path stays unchanged."""
    import itertools
    import json

    encode = json.JSONEncoder(ensure_ascii=True, separators=(",", ":")).encode
    records = metadata_records(entries, metadata, all_entries, base64_names)
    prefix = "["
    while True:
        batch = list(itertools.islice(records, METADATA_BATCH_SIZE))
        if not batch:
            break
        write_all(fd, (prefix + encode(batch)[1:-1]).encode("ascii"))
        prefix = ","
    write_all(fd, b"[]" if prefix == "[" else b"]")


def files_context(metadata, all_entries, base64_names):
    if metadata & STATS:
        mode = "stats"
    elif metadata & PERMISSIONS:
        mode = "permissions+inode" if metadata & INODE else "permissions"
    elif metadata & INODE:
        mode = "inode"
    else:
        mode = "names"
    return {
        "mode": mode,
        "scope": "all-entries" if all_entries else "regular-files",
        "name_encoding": "base64" if base64_names else "filesystem-text",
    }


def write_entries_prefix(metadata, all_entries, base64_names, fd=1):
    import json
    context = files_context(metadata, all_entries, base64_names)
    encoded = json.dumps(context, ensure_ascii=True,
                         separators=(",", ":")).encode("ascii")
    write_all(fd, b'{"files":' + encoded[:-1] + b',"entries":')


def write_count(count, all_entries, fd=1):
    import json
    document = {
        "files": {
            "mode": "count",
            "scope": "all-entries" if all_entries else "regular-files",
            "count": count,
        },
        "complete": True,
        "errors": 0,
    }
    write_all(fd, (json.dumps(document, ensure_ascii=True,
                              separators=(",", ":")) + "\n").encode("ascii"))


def run(directory, number=False, all_entries=False, base64_names=False, metadata=0):
    if metadata < 0 or metadata & ~(INODE | PERMISSIONS | STATS):
        raise UsageError("invalid metadata flags")
    if number and metadata:
        raise UsageError("--number cannot be combined with metadata options")
    entries, directory_fd = open_scan(directory)
    try:
        if number:
            count = count_entries(entries, all_entries)
        else:
            write_entries_prefix(metadata, all_entries, base64_names)
            if metadata:
                write_metadata(entries, metadata, all_entries, base64_names)
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
        write_count(count, all_entries)
    else:
        # The success envelope is completed only after enumeration and cleanup.
        write_all(1, b'},"complete":true,"errors":0}\n')


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
