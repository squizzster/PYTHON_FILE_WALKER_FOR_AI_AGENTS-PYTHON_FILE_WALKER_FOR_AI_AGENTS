# Directory tree to JSON — Linux, Python standard library

## Run

```sh
python3 create_directory_tree_to_json.py . > /tmp/dtree.json
# Or make the file executable, then use its shebang:
chmod +x create_directory_tree_to_json.py
./create_directory_tree_to_json.py ./location > /tmp/dtree.json
```

Exactly one location is required. Use `--` before a location beginning with `-`.
No Python package installation, C compiler, or helper binary is needed to run
this script. The optional C files are test instruments only.

For the lowest-I/O selection, omitting symlinks and avoiding sorting:

```sh
python3 create_directory_tree_to_json.py --no-symlinks -U ./location > /tmp/dtree.json
```

This deliberately differs from default `tree -d`: symbolic links to directories
are omitted. `-U` changes order, not membership. It saves sorting work but is
not a guarantee of better physical disk ordering or fewer directory reads.

Other optional switches: `-a` includes dot directories; `-x` avoids enumerating
directories whose `st_dev` differs from the root. Use `--help` for usage.
Default traversal crosses mount points, as `tree -d` does. `-x` is NOT an
all-mount-boundaries or no-automount guarantee, and symlink target probes in the
default mode can still reach another filesystem. Combine `-x --no-symlinks` when
that is appropriate. Choose the starting directory carefully.

## Default semantics

Hidden entries are skipped before type checks. Ordinary directories are visited
once. Directory symlinks are reported as leaves with their link text, never
recursed into. Symlinks to files and broken/cyclic symlinks are omitted.
The explicitly supplied root may itself be a symlink to a directory, including
when `--no-symlinks` is used; that option concerns entries below the root.

Sorting uses `LC_COLLATE`, with fast byte sorting for C/POSIX/C.UTF-8 locales.
If names cannot be collated in another locale, that directory falls back to byte
ordering. Locale-equivalent names need not have the same tie order as `tree`.
This implements the directory selection and traversal intent of `tree -d`, not
its text layout, numeric footer, or the precise schema of `tree -J`. A live
filesystem's race/error output is not promised to match every `tree` version.

## JSON schema

The stream is one compact JSON document followed by a newline:

```json
{"tree":{"type":"directory","name":".","children":[{"type":"directory","name":"photos","children":[]},{"type":"link","name":"shortcut","target":"photos"}]},"complete":true,"errors":0}
```

The root name preserves the supplied location. Descendant names are basenames.
Every real directory node has `children`; directory-link leaves instead have
`type: "link"` and `target`. The schema intentionally does not collect sizes,
owners, permissions, timestamps, checksums, or file-content data.

An unreadable/unopenable directory has `children: []` and an `error` object
containing `operation`, numeric `errno`, and `message`; it is not silently
presented as an ordinary empty directory. A directory whose enumeration or
entry classification partly failed has its own numeric `errors` field.
Errors are also described on STDERR. The top-level `errors` count covers all
observed traversal errors, and `complete` is false when that count is nonzero.
A node pruned by `-x` has `pruned: "different-filesystem"`; intentional pruning
is not an error, and `complete` refers to the selected traversal scope.

Names are Linux bytes, not necessarily UTF-8. Valid UTF-8 is represented in
`name`/`target`. Otherwise a replacement-character display value is accompanied
by an authoritative `name_bytes_b64`/`target_bytes_b64`. Recover bytes with:

```python
import base64

def filename_bytes(node, key="name"):
    encoded = node.get(key + "_bytes_b64")
    return base64.b64decode(encoded) if encoded is not None else node[key].encode("utf-8")
```

JSON is ASCII-escaped, and consequently valid UTF-8 regardless of terminal
encoding. Unpaired surrogate code points are not emitted. Children are an
array, so byte-distinct names that share replacement-character display text
do not overwrite each other.

## Exit status and incomplete output

| Status | Meaning |
| --- | --- |
| 0 | Finished with no observed traversal errors; stdout flushed successfully. |
| 1 | Partial traversal, root failure, output failure, or out of memory. |
| 2 | Invalid invocation or unsupported environment. |
| 130 | Keyboard interrupt during the handled execution path. |
| 141 | Broken pipe during the handled execution path. |

Recoverable traversal errors still produce a complete JSON document with
`complete: false`. Output failure, interruption, process termination, or memory
exhaustion can leave truncated JSON: discard it. SIGTERM/SIGKILL follow the
operating system's normal signal termination behavior. No JSON producer can
finish a document after SIGKILL, or make a failed output sink accept its tail.

Do not replace an earlier successful inventory unless the exit code is zero.
For example, using a temporary file on the same output filesystem:

```sh
#!/bin/sh
set -u
out=/tmp/dtree.json
tmp=$(mktemp "${out}.XXXXXX") || exit 1
trap 'rm -f -- "$tmp"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if python3 create_directory_tree_to_json.py ./location > "$tmp"; then
    mv -f -- "$tmp" "$out" || exit 1
else
    status=$?
    exit "$status"
fi
```

This is an output-publication pattern, not crash-durability assurance. The
scanner does not call `fsync` or `sync`. Pick an output filesystem appropriate
to the equipment; `/tmp` is not necessarily RAM-backed. Keeping output away
from the source device avoids competing output writes on that device.

## I/O and resource design

`os.scandir` obtains names and available entry types from directory enumeration.
For ordinary files on a filesystem that supplies usable `d_type`, no separate
file `stat` is necessary. On `DT_UNKNOWN`, Python performs the required
metadata fallback. The script does not assume that a filesystem's name alone
proves `d_type` support; this matters for old filesystem formats and drivers.

A directory must still be opened and read, and all directory entries—including
file names—must be examined to discover its subdirectories. There is no
portable Linux directory operation here that returns only subdirectory names
without examining the directory. Library/kernel calls can perform readahead
and additional filesystem work. Syscall counts are not counts of disk reads.

Traversal is serial, descriptor-relative, and iterative. Child directory opens
use `O_DIRECTORY | O_NOFOLLOW`; the scanner never opens regular files, FIFOs,
sockets, or device contents. The supplied root's pathname is resolved normally.
Child basenames are resolved against pinned parent descriptors, not repeated
long paths. This resists directory-to-symlink swaps and ancestor renames but
is not a general filesystem sandbox or a defense against mount manipulation.

One explicit `fstat` of each opened directory provides `(st_dev, st_ino)` for
ancestor-cycle detection and optional device restriction. `fdopendir` can also
perform a metadata check. These are deliberate per-directory safety costs;
this is not a claim of the fewest possible syscalls. Aliases outside the active
ancestor chain are not globally deduplicated, which preserves distinct tree
locations instead of silently dropping them.

On the modern backend, directory opens attempt `O_NOATIME`. If permission or
support prevents that, they retry once without it. This is best effort, not a
zero-write promise; filesystem implementation and mount policy matter, and
link-text reads are not covered by directory `O_NOATIME`. The script does not
rewrite timestamps, change mount options, force synchronization, drop caches,
create threads, or automatically retry media/read errors.

The output buffer is approximately 64 KiB plus the largest token. Only pending
directory/link siblings and traversal frames are retained, not regular-file
lists or a complete Python representation of the tree. This is not constant
memory: extremely wide directories can still require substantial RAM.

Parent descriptors are released early when the last child is opened. A simple
chain therefore needs a small constant number of descriptors, even at great
depth. Deeply branching paths can still require one descriptor per ancestor
with pending siblings. Descriptor exhaustion is reported as an incomplete
result, rather than hidden or retried in a loop. JSON is emitted iteratively,
but a consumer may impose its own nesting limit.

## Compatibility and scope

Target: Linux and CPython 3.5+, standard library only. No Python 2 support.
Native `scandir(fd)` is used where supported (Python 3.7+ on Unix). Python
3.5/3.6 use a legacy backend that temporarily changes cwd to the pinned
directory for `scandir(".")`, restoring the original cwd on exit. It is for
single-threaded use and cannot preserve the modern backend's `O_NOATIME`
behavior. CPython 3.5 closes its iterator by destruction because it has no
public iterator close method. Older kernels still need to support the open
flags and descriptor operations used; very old kernels are not certified.

Actual runtime tests here used CPython 3.13.5. Python 3.5 grammar was checked,
and the legacy backend was exercised under the installed interpreter. These
are not substitutes for execution under real Python 3.5/3.6 installations.

Only tmpfs and a container overlay filesystem were available for measurement.
The script is filesystem-agnostic at the Linux API level, but ext4, XFS, Btrfs,
ZFS, F2FS, NTFS drivers, old USB hardware, network/FUSE filesystems, and tape
hardware were not individually tested. A tape must expose a mounted directory
namespace for this tool; a raw tape/archive device is not a directory tree.
Metadata operations on special/remote/tape-backed mounts can still cause
mounts, media access, or unbounded kernel waits. No Python-level traversal can
promise that a device will never be touched or that an I/O call cannot block.

`complete: true` means no traversal errors were observed. It does NOT prove a
point-in-time snapshot: concurrent creates/deletes/renames may escape detection.
No-follow handling, error reporting, and cycle detection do not change that.

## Tests and benchmark reproduction

Read `BENCHMARK_REPORT.md` for the measurements and explicit limitations.
The tests create and remove temporary fixtures; the performance benchmark
creates over 150,000 empty files/directories across its fixtures. Run them only
on disposable scratch storage, not on fragile production media.

```sh
python3 -m unittest -v test_directory_tree
python3 benchmark_directory_tree.py --scratch-parent /dev/shm --repeats 9 --python-no-site
```

`--python-no-site` uses `python -S` in benchmark workers to avoid environment-
specific site hooks; it is not required for the production script. All four
engines pay the same worker import overhead. The benchmark compares concrete
JSON-producing implementations, not theoretical lower bounds for each API.
A modern `os.walk` already uses `scandir`; it is not a per-file-stat baseline.

Optional Linux x86-64 syscall tracing and real `DT_UNKNOWN` fallback testing:

```sh
gcc -O2 -Wall -Wextra -o syscall_count syscall_count.c
gcc -O2 -Wall -Wextra -shared -fPIC -o force_dtype_unknown.so force_dtype_unknown.c -ldl
LD_PRELOAD="$PWD/force_dtype_unknown.so" python3 -m unittest -v test_directory_tree

# --keep retains disposable fixtures and reports their paths in the JSON result:
python3 benchmark_directory_tree.py --scratch-parent /dev/shm --repeats 9 --keep --python-no-site > benchmark.json
python3 profile_directory_tree.py --helper ./syscall_count \
    --unknown-library ./force_dtype_unknown.so /path/to/kept/file-heavy > syscalls.json
```

The helper traces only its direct child and requires ptrace permission. It
counts syscalls, not physical I/O; it is NOT used for the timing measurements.
Never set the test LD_PRELOAD library globally or use it for production runs.
