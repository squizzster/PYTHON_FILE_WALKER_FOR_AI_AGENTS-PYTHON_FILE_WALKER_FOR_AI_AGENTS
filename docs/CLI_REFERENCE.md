# CLI reference

This document describes the current public command-line behavior. Installed
command names come from [`pyproject.toml`](../pyproject.toml); executable help is
defined by `HELP_DOCUMENT` in the command modules; tests provide the strongest
repository evidence that the implementation matches those contracts.

## Requirements and setup

- Linux.
- Python 3.5 or newer at runtime.
- No third-party runtime dependencies.
- `uv` for the repository's locked development environment; the package build
  backend is `uv_build`.

Prepare the development environment:

```bash
uv sync --locked
```

Each root-level Python shim works from any current directory when it remains in,
or is symlinked to, this source checkout. A copied shim loads an installed
`python_file_walker_for_ai_agents` package from the interpreter selected by its
shebang; copying a shim alone is not an installation.

## Commands at a glance

| Installed command | Source-checkout shim | Implementation | Result |
| --- | --- | --- | --- |
| `python-file-walker-for-ai-agents` | [`python_file_walker_for_ai_agents.py`](../python_file_walker_for_ai_agents.py) | [`directory_tree.main` and `directory_tree.cli`](../src/python_file_walker_for_ai_agents/directory_tree.py) | Recursive, sorted directory-only tree |
| `list-files-in-a-directory-to-json` | [`list_files_in_a_directory_to_json.py`](../list_files_in_a_directory_to_json.py) | [`file_listing.main`](../src/python_file_walker_for_ai_agents/file_listing.py) | Files or entries from exactly one directory |
| `list-files-in-a-directory-tree-to-json` | [`list_files_in_a_directory_tree_to_json.py`](../list_files_in_a_directory_tree_to_json.py) | [`recursive_file_listing.main` and `recursive_file_listing.cli`](../src/python_file_walker_for_ai_agents/recursive_file_listing.py) | Recursive directory tree with a file object on each real directory |

All commands write successful data to stdout as one compact JSON document plus
a newline. Help and diagnostics go to stderr.

## Directory-only tree

Run from a source checkout:

```bash
./python_file_walker_for_ai_agents.py DIRECTORY
```

The command emits directory nodes and directory-symlink leaves. It omits regular
files, file symlinks, sockets, FIFOs, devices, and other non-directory entries.

```json
{"tree":{"type":"directory","name":"DIRECTORY","children":[]},"complete":true,"errors":0}
```

Directory children are sorted using `LC_COLLATE`. C and POSIX locales use byte
ordering. Hidden directories are included. An explicitly supplied root symlink
is followed, but a descendant directory symlink is emitted as a leaf and never
traversed.

Use `-h`, `--help`, or `-help` as the sole argument to receive the compact JSON
help contract on stderr.

## One-directory file listing

Run from a source checkout:

```bash
./list_files_in_a_directory_to_json.py [OPTIONS] DIRECTORY
```

The default mode enumerates regular-file basenames, including hidden files, in
the filesystem's iteration order. It does not recurse or sort, and it excludes
directories, symlinks, and special files.

```json
{"files":{"mode":"names","scope":"regular-files","name_encoding":"filesystem-text","entries":["example.txt"]},"complete":true,"errors":0}
```

The directory argument itself may be a symlink. Entry classification and
metadata never follow entry symlinks.

## Recursive directory-and-file listing

Run from a source checkout:

```bash
./list_files_in_a_directory_tree_to_json.py [OPTIONS] DIRECTORY
```

This command composes the directory tree with the same file-object contract as
the one-directory command. Each real directory is scanned once and receives a
`files` object; directory-symlink leaves do not receive one.

```json
{"tree":{"type":"directory","name":"DIRECTORY","files":{"mode":"names","scope":"regular-files","name_encoding":"filesystem-text","entries":["example.txt"]},"children":[]},"complete":true,"errors":0}
```

Directory nodes are sorted as described above. File entries retain filesystem
iteration order. By default, directory entries occur structurally in `children`
and regular files occur in `files.entries`. With `--all-entries`, directories,
symlinks, and special entries also appear in each directory's `files` object;
real directories and directory symlinks still retain their structural nodes.

## File options

The one-directory and recursive file commands share these options and schemas:

| Option | Effect |
| --- | --- |
| `--number`, `-n` | Replace `entries` with `count` and set `mode` to `count`. Cannot be combined with metadata options. |
| `--inode` | Emit `{name, inode}` records using the directory-entry inode. |
| `--permissions` | Emit name, numeric mode, octal permission bits, UID, and GID. |
| `--stats` | Include permissions, inode, device, type, link count, size, nanosecond timestamps, block counts, block size, and device ID where the platform exposes them. |
| `--all-entries` | Include every entry type without following symlinks; set `scope` to `all-entries`. |
| `--base64` | Encode raw filename bytes as base64 and set `name_encoding` to `base64`. |
| `--` | Stop option parsing so a following directory is treated literally. |

`--file-permissions-stats` and `--file_permissions_stats` are aliases for
`--stats`. `-h`, `--help`, and `-help` emit the applicable compact JSON help
document to stderr.

## Filesystem and data boundaries

### No content reads

The walkers open directories only. They never open or read regular-file
contents. Metadata modes call `stat` without following symlinks when the
requested fields require it. On supported descriptor-based paths, directory
opens attempt `O_NOATIME` and retry without it when permissions or the filesystem
do not allow that flag.

### One filesystem

Recursive commands establish the root directory's `st_dev` as their boundary.
A real child directory on another device is emitted as an empty directory node
with `"pruned":"different-filesystem"`; it is not enumerated. This is a device
boundary, not a mount-name or path-prefix check.

### Live results, not snapshots

Traversal is race-aware but represents a changing live filesystem. Descendant
directories are opened without following symlinks, and traversal is anchored to
open directory descriptors where the runtime supports descriptor-based
`scandir`. Entries can still be created, removed, renamed, or replaced during a
scan. `"complete":true` means no error was observed; it does not mean the tree
was unchanged or atomic.

### Filename bytes

Directory node and symlink fields use normal UTF-8 text when possible. If a
Linux name contains invalid UTF-8 bytes, the display field uses replacement
characters and an adjacent `name_bytes_b64` or `target_bytes_b64` field carries
the authoritative bytes.

File objects use Python filesystem text by default. Consumers that need an
unambiguous round trip for arbitrary filename bytes should request `--base64`.

### Output size

JSON is serialized through bounded internal buffers, but the complete output can
still be large. Consumers should read stdout continuously rather than waiting
with a small fixed pipe buffer. A downstream program that parses the entire JSON
document at once still needs memory proportional to the result.

## Completion, errors, and exit status

Tree commands report recoverable directory failures in the affected node and
set the envelope to `"complete":false` with a nonzero `errors` count. Such a
status-1 result can be valid partial JSON. Fatal output or memory failures can
also return status 1 with incomplete stdout, so consumers must successfully
parse the document before using a partial tree.

The one-directory file command emits only a success envelope. If it returns
nonzero, discard stdout because streaming may have stopped mid-document.

| Exit | Meaning |
| ---: | --- |
| 0 | Successful data output, or explicit help. |
| 1 | Observed traversal error, root failure, output failure, memory failure, or another operational failure. |
| 2 | Invalid invocation, unsupported platform/runtime, or a copied shim whose package is unavailable. |
| 130 | Interrupted. Output may be incomplete. |
| 141 | Broken output pipe. Output is incomplete. |

Treat stderr as diagnostics rather than data. With no directory or an invalid
option, the file commands emit a JSON error/help document to stderr; the
directory-only command emits its help document.

## Public contract ownership

When behavior changes, keep these locations aligned:

- Console script registration and minimum Python:
  [`pyproject.toml`](../pyproject.toml).
- Directory-only help and behavior: `HELP_DOCUMENT`, `DirectoryTree`, `main`,
  and `cli` in
  [`directory_tree.py`](../src/python_file_walker_for_ai_agents/directory_tree.py).
- Shared file schema: `entry_value`, `files_context`, and `FileObjectWriter` in
  [`file_entries.py`](../src/python_file_walker_for_ai_agents/file_entries.py).
- One-directory argument and help contract: `HELP_DOCUMENT`, `parse_args`,
  `run`, and `main` in
  [`file_listing.py`](../src/python_file_walker_for_ai_agents/file_listing.py).
- Recursive composition and help contract: `HELP_DOCUMENT`, `main`, and `cli`
  in
  [`recursive_file_listing.py`](../src/python_file_walker_for_ai_agents/recursive_file_listing.py).
- Observable evidence: the tests listed in the
  [development guide](DEVELOPMENT.md#test-ownership).
