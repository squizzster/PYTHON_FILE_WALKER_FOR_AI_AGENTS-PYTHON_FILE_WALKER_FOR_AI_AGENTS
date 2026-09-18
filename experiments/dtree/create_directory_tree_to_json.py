#!/usr/bin/env python3
"""Low-I/O, directory-only JSON tree for Linux, CPython 3.5+.

Usage: create_directory_tree_to_json.py [options] LOCATION

Default selection: tree -d (hidden entries omitted; directory symlinks are
leaves; mount points traversed). Sorting follows LC_COLLATE where possible.
Use --no-symlinks -U to avoid symlink-target lookups and sorting.

Exit: 0 = no observed traversal errors; 1 = incomplete/output failure;
      2 = invocation/environment error; 130 = interrupted; 141 = broken pipe.
A successful scan is a best-effort live listing, NOT a filesystem snapshot.
"""
import argparse
import base64
import errno
import json
import locale
import os
import sys
from json.encoder import encode_basestring_ascii as quote


BUFFER_SIZE = 65536
_FD_SCANDIR = os.scandir in getattr(os, "supports_fd", ()) if hasattr(os, "scandir") else False
_NOATIME_RETRY = frozenset((errno.EPERM, errno.EINVAL,
                            getattr(errno, "EOPNOTSUPP", errno.EINVAL)))
_BROKEN_LINK = frozenset((errno.ENOENT, errno.ENOTDIR, errno.ELOOP))


def text_fields(key, value):
    """ASCII JSON fields, preserving arbitrary Linux filename bytes.

    Valid UTF-8 is represented normally. Otherwise the display text uses
    replacement characters and KEY_bytes_b64 is the authoritative byte name.
    No unpaired surrogate escapes are placed in JSON.
    """
    raw = os.fsencode(value)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", "replace")
        encoded = base64.b64encode(raw).decode("ascii")
        return quote(key) + ":" + quote(text) + "," + quote(key + "_bytes_b64") + ":" + quote(encoded)
    return quote(key) + ":" + quote(text)


class BufferedJSON(object):
    """Small bounded output buffer. Sink must implement blocking write(bytes)."""
    def __init__(self, sink, limit=BUFFER_SIZE):
        self.sink = sink
        self.limit = limit
        self.parts = []
        self.size = 0

    def write(self, text):
        self.parts.append(text)
        self.size += len(text)
        if self.size >= self.limit:
            self.flush()

    def flush(self):
        if not self.parts:
            return
        data = "".join(self.parts).encode("ascii")
        self.parts = []
        self.size = 0
        # Normal buffered stdout writes the whole block. Handle a short-writing
        # blocking sink too; do not silently accept a nonblocking write(None).
        offset = 0
        while offset < len(data):
            written = self.sink.write(data if not offset else data[offset:])
            if written is None or written <= 0:
                raise OSError(errno.EIO, "stdout made no write progress")
            offset += written


class Frame(object):
    __slots__ = ("fd", "name", "identity", "pending", "first", "errors")

    def __init__(self, fd, name, identity, pending, errors):
        self.fd = fd
        self.name = name
        self.identity = identity
        self.pending = pending
        self.first = True
        self.errors = errors


class DirectoryTree(object):
    """Single-threaded scanner. On 3.5/3.6 it temporarily changes process cwd.

    Do not call the legacy backend concurrently with other filesystem work in
    the same process. The command-line program never creates threads.
    """
    def __init__(self, output, errors, all_names=False, include_symlinks=True,
                 unsorted=False, one_file_system=False, native_scandir=None):
        self.out = BufferedJSON(output)
        self.stderr = errors
        self.all_names = all_names
        self.include_symlinks = include_symlinks
        self.unsorted = unsorted
        self.one_file_system = one_file_system
        self.native = _FD_SCANDIR if native_scandir is None else native_scandir
        self.error_count = 0
        self.stack = []
        self.active = set()
        self.root_device = None
        self.saved_cwd = None
        self.root_name = None
        self.flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
        # scandir(fd) uses the same open file description, preserving NOATIME.
        # The legacy path backend opens another description, so cannot do this.
        self.noatime = getattr(os, "O_NOATIME", 0) if self.native else 0
        collation = locale.setlocale(locale.LC_COLLATE)
        self.byte_sort = collation in ("C", "POSIX", "C.UTF-8", "C.utf8")

    def diagnostic_path(self, extra=None):
        names = [os.fsencode(f.name) for f in self.stack]
        if not names:
            names = [os.fsencode(self.root_name)]
        if extra is not None:
            names.append(os.fsencode(extra))
        # For diagnostics only: never pass this reconstructed path to the OS.
        return b"/".join(names)

    def report(self, operation, exc, extra=None):
        self.error_count += 1
        raw = self.diagnostic_path(extra)
        message = "%s: %s: %s: %s\n" % (
            "dtree", operation, ascii(os.fsdecode(raw)), ascii(str(exc)))
        self.stderr.write(message)
        return {"operation": operation, "errno": getattr(exc, "errno", None),
                "message": str(exc).encode("utf-8", "backslashreplace").decode("utf-8")}

    def open_dir(self, name, parent_fd=None):
        flags = self.flags
        if parent_fd is not None:
            flags |= os.O_NOFOLLOW
        if self.noatime:
            try:
                return os.open(name, flags | self.noatime, dir_fd=parent_fd)
            except OSError as exc:
                if exc.errno not in _NOATIME_RETRY:
                    raise
                # Ownership/FS support varies by directory: don't disable the
                # attempt globally. Failed opens do not enumerate anything.
        return os.open(name, flags, dir_fd=parent_fd)

    def scan(self, fd, name):
        pending = []
        local_errors = 0
        iterator = None
        try:
            if self.native:
                iterator = os.scandir(fd)
            else:
                os.fchdir(fd)
                iterator = os.scandir(".")
            for entry in iterator:
                if not self.all_names and entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append((entry.name, None))
                    elif self.include_symlinks and entry.is_symlink():
                        try:
                            if entry.is_dir(follow_symlinks=True):
                                target = os.readlink(entry.name, dir_fd=fd)
                                pending.append((entry.name, target))
                        except OSError as exc:
                            # Broken/cyclic links aren't directory leaves.
                            if exc.errno not in _BROKEN_LINK:
                                local_errors += 1
                                self.report("symlink metadata", exc, entry.name)
                except OSError as exc:
                    local_errors += 1
                    self.report("entry type", exc, entry.name)
        except OSError as exc:
            local_errors += 1
            self.report("readdir", exc)
        finally:
            if iterator is not None:
                close = getattr(iterator, "close", None)
                if close is not None:
                    close()
                # CPython 3.5 has no public close(); destruction closes it.
                del iterator
        if not self.unsorted:
            if self.byte_sort:
                pending.sort(key=lambda item: os.fsencode(item[0]), reverse=True)
            else:
                try:
                    pending.sort(key=lambda item: locale.strxfrm(item[0]), reverse=True)
                except (UnicodeError, ValueError):
                    # Invalid bytes may have no locale collation. Preserve all
                    # names; deterministic byte order for this directory.
                    pending.sort(key=lambda item: os.fsencode(item[0]), reverse=True)
        else:
            pending.reverse()
        return pending, local_errors

    def close_frame_fd(self, frame):
        if frame.fd is not None:
            fd, frame.fd = frame.fd, None
            os.close(fd)

    def emit_failed(self, name, detail):
        self.out.write('{"type":"directory",' + text_fields("name", name) +
                       ',"children":[],"error":' +
                       json.dumps(detail, ensure_ascii=True, separators=(",", ":")) + '}')

    def enter(self, name, parent=None):
        """Open and list one directory; transfer fd ownership to a new frame."""
        fd = None
        try:
            try:
                fd = self.open_dir(name, None if parent is None else parent.fd)
                info = os.fstat(fd)
                identity = (info.st_dev, info.st_ino)
                if identity in self.active:
                    raise OSError(errno.ELOOP, "directory refers to an active ancestor")
                if self.root_device is None:
                    self.root_device = info.st_dev
                elif self.one_file_system and info.st_dev != self.root_device:
                    self.out.write('{"type":"directory",' + text_fields("name", name) +
                                   ',"children":[],"pruned":"different-filesystem"}')
                    return
            except OSError as exc:
                detail = self.report("open directory", exc, None if parent is None else name)
                self.emit_failed(name, detail)
                return
            # No more child names need this parent fd. Release it early so a
            # chain of any depth needs O(1) fds rather than one fd per level.
            if parent is not None and not parent.pending:
                self.close_frame_fd(parent)
            frame = Frame(fd, name, identity, [], 0)
            self.stack.append(frame)
            fd = None
            self.active.add(identity)
            frame.pending, frame.errors = self.scan(frame.fd, name)
            if not frame.pending:
                self.close_frame_fd(frame)
            self.out.write('{"type":"directory",' + text_fields("name", name) + ',"children":[')
        finally:
            if fd is not None:
                os.close(fd)

    def run(self, location):
        self.root_name = location
        try:
            if not self.native:
                # O_PATH avoids requiring read access to the original cwd.
                self.saved_cwd = os.open(".", getattr(os, "O_PATH", os.O_RDONLY) |
                                         os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0))
            self.out.write('{"tree":')
            self.enter(location)
            while self.stack:
                frame = self.stack[-1]
                if not frame.pending:
                    self.close_frame_fd(frame)
                    self.out.write("]")
                    if frame.errors:
                        self.out.write(',"errors":' + str(frame.errors))
                    self.out.write("}")
                    self.stack.pop()
                    self.active.remove(frame.identity)
                    continue
                name, target = frame.pending.pop()
                if frame.first:
                    frame.first = False
                else:
                    self.out.write(",")
                if target is not None:
                    self.out.write('{"type":"link",' + text_fields("name", name) + ',' +
                                   text_fields("target", target) + '}')
                else:
                    self.enter(name, frame)
            self.out.write(',"complete":' + ("false" if self.error_count else "true") +
                           ',"errors":' + str(self.error_count) + '}\n')
            self.out.flush()
            return 1 if self.error_count else 0
        finally:
            for frame in reversed(self.stack):
                if frame.fd is not None:
                    try:
                        self.close_frame_fd(frame)
                    except OSError:
                        pass
            self.stack = []
            self.active.clear()
            if self.saved_cwd is not None:
                fd, self.saved_cwd = self.saved_cwd, None
                try:
                    os.fchdir(fd)
                finally:
                    os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("location", help="mandatory directory to inspect")
    parser.add_argument("-a", "--all", action="store_true", help="include dot directories")
    parser.add_argument("-U", "--unsorted", action="store_true", help="directory enumeration order")
    parser.add_argument("--no-symlinks", action="store_true",
                        help="omit all symlinks; avoid target stat/readlink calls")
    parser.add_argument("-x", "--one-file-system", action="store_true",
                        help="do not enumerate directories on a different st_dev")
    args = parser.parse_args(argv)
    if not sys.platform.startswith("linux") or sys.version_info < (3, 5):
        parser.error("requires Linux and CPython/Python 3.5 or newer")
    if not args.location or "\x00" in args.location:
        parser.error("location must be nonempty and cannot contain NUL")
    try:
        locale.setlocale(locale.LC_COLLATE, "")
    except locale.Error:
        # No filesystem operation: invalid environment locale falls back to C.
        locale.setlocale(locale.LC_COLLATE, "C")
    output = sys.stdout.buffer
    scanner = DirectoryTree(output, sys.stderr, all_names=args.all,
                            include_symlinks=not args.no_symlinks,
                            unsorted=args.unsorted, one_file_system=args.one_file_system)
    status = scanner.run(args.location)
    output.flush()  # Catch delayed ENOSPC/EPIPE before claiming success.
    return status


def fatal(message, status):
    # Do not let an unavailable stderr hide the original failure or trigger
    # another traceback. _exit prevents shutdown from retrying broken stdout.
    try:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass
    os._exit(status)


def cli():
    try:
        return main()
    except KeyboardInterrupt:
        fatal("dtree: interrupted; discard incomplete stdout", 130)
    except OSError as exc:
        if exc.errno == errno.EPIPE:
            os._exit(141)
        fatal("dtree: fatal I/O failure: %s; discard stdout" % ascii(str(exc)), 1)
    except MemoryError:
        fatal("dtree: out of memory; discard incomplete stdout", 1)


if __name__ == "__main__":
    sys.exit(cli())
