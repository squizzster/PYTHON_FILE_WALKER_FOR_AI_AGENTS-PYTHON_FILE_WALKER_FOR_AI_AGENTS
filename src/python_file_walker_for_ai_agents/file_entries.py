"""Shared selection and bounded JSON encoding for directory entries."""

import os


# Limits retained names, not directory size. CPython's JSON accelerator
# encodes each bounded batch without one allocation per output byte.
BATCH_SIZE = 4096
METADATA_BATCH_SIZE = 512

# Internal option bits; --stats includes permissions and inode.
INODE = 1
PERMISSIONS = 2
STATS = 4
_SKIP_ENTRY = object()


def entry_value(entry, metadata=0, all_entries=False, base64_names=False):
    """Return one file-schema value, or _SKIP_ENTRY; never read content."""
    if not metadata:
        if not all_entries and not entry.is_file(follow_symlinks=False):
            return _SKIP_ENTRY
        return encoded_name(entry.name, base64_names)

    # Inode-only uses d_ino and adds no stat call. Filtering may need libc's
    # DT_UNKNOWN fallback, which is unavoidable when the filesystem omits type.
    if not metadata & (PERMISSIONS | STATS):
        if not all_entries and not entry.is_file(follow_symlinks=False):
            return _SKIP_ENTRY
        return {"name": encoded_name(entry.name, base64_names),
                "inode": entry.inode()}

    import stat
    if not all_entries and not entry.is_file(follow_symlinks=False):
        return _SKIP_ENTRY
    info = entry.stat(follow_symlinks=False)
    mode = info.st_mode
    # Do not leak a replacement symlink/directory if the cached d_type raced.
    if not all_entries and not stat.S_ISREG(mode):
        return _SKIP_ENTRY
    record = {
        "name": encoded_name(entry.name, base64_names),
        "mode": mode,
        "permissions": "%04o" % (mode & 0o7777),
        "uid": info.st_uid,
        "gid": info.st_gid,
    }
    if metadata & (INODE | STATS):
        record["inode"] = info.st_ino
    if metadata & STATS:
        type_names = {
            stat.S_IFREG: "file", stat.S_IFDIR: "directory",
            stat.S_IFLNK: "symlink", stat.S_IFIFO: "fifo",
            stat.S_IFSOCK: "socket", stat.S_IFCHR: "character",
            stat.S_IFBLK: "block",
        }
        record.update(
            device=info.st_dev,
            type=type_names.get(stat.S_IFMT(mode), "unknown"),
            nlink=info.st_nlink,
            size=info.st_size,
            atime_ns=info.st_atime_ns,
            mtime_ns=info.st_mtime_ns,
            ctime_ns=info.st_ctime_ns,
            blocks_512=getattr(info, "st_blocks", None),
            blksize=getattr(info, "st_blksize", None),
            rdev=getattr(info, "st_rdev", None),
        )
    return record


def encoded_name(name, base64_names):
    if not base64_names:
        return name
    import base64
    return base64.b64encode(os.fsencode(name)).decode("ascii")


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


class FileObjectWriter(object):
    """Bounded streaming serializer for the shared ``files`` object."""
    def __init__(self, write, number=False, all_entries=False,
                 base64_names=False, metadata=0):
        import json
        self.write = write
        self.number = number
        self.all_entries = all_entries
        self.base64_names = base64_names
        self.metadata = metadata
        self.count = 0
        self.batch = []
        self.prefix = "["
        self.limit = METADATA_BATCH_SIZE if metadata else BATCH_SIZE
        self.encode = json.JSONEncoder(
            ensure_ascii=True, separators=(",", ":")).encode
        if not number:
            context = files_context(metadata, all_entries, base64_names)
            encoded = self.encode(context).encode("ascii")
            self.write(encoded[:-1] + b',"entries":')

    def add(self, entry):
        value = entry_value(entry, self.metadata, self.all_entries,
                            self.base64_names)
        if value is _SKIP_ENTRY:
            return False
        self.count += 1
        if not self.number:
            self.batch.append(value)
            if len(self.batch) >= self.limit:
                self.flush()
        return True

    def flush(self):
        if not self.batch:
            return
        encoded = self.encode(self.batch)
        self.write((self.prefix + encoded[1:-1]).encode("ascii"))
        self.batch = []
        self.prefix = ","

    def finish(self):
        if self.number:
            document = {
                "mode": "count",
                "scope": ("all-entries" if self.all_entries
                          else "regular-files"),
                "count": self.count,
            }
            self.write(self.encode(document).encode("ascii"))
            return
        self.flush()
        self.write(b"[]}" if self.prefix == "[" else b"]}")
