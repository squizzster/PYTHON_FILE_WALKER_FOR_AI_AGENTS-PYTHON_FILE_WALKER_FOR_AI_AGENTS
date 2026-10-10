# Development guide

This project is in **EXP** mode: make small, evidence-led changes, run a
representative case, and strengthen only the behavior that real results show is
needed. The manifest version is `0.1.0`. Runtime compatibility is Linux with
Python 3.5 or newer; the checked-in development selector is Python 3.12.

Start with the project-specific [`AGENTS.md`](../AGENTS.md). For a CLI change,
also read the relevant section of the [CLI reference](CLI_REFERENCE.md), then
inspect the implementation, shim, tests, and `pyproject.toml` entry point that
jointly own the contract.

## Authority map

| Subject | Authoritative evidence |
| --- | --- |
| Package name, version, Python minimum, build backend, installed commands | [`pyproject.toml`](../pyproject.toml) and [`uv.lock`](../uv.lock) |
| Selected development Python | [`.python-version`](../.python-version) |
| Accepted arguments and machine-readable help | `HELP_DOCUMENT` and argument parsing in the applicable CLI module |
| Implemented filesystem and JSON behavior | Source under [`src/python_file_walker_for_ai_agents/`](../src/python_file_walker_for_ai_agents/) |
| Supported observable behavior | Focused tests under [`tests/`](../tests/) and [`experiments/dtree/test_directory_tree.py`](../experiments/dtree/test_directory_tree.py) |
| Current human-facing command contract | [`docs/CLI_REFERENCE.md`](CLI_REFERENCE.md) |
| Pending and historical changes | [`VERSION_TRACKER.md`](../VERSION_TRACKER.md) |
| Agent workflow and repository constraints | [`AGENTS.md`](../AGENTS.md) |

If these disagree, report the mismatch explicitly. Tests and code reveal
implemented behavior; they do not silently redefine a deliberately documented
public contract.

## Repository layout

### Public entry points

- [`python_file_walker_for_ai_agents.py`](../python_file_walker_for_ai_agents.py)
  is the relocatable shim for the directory-only command.
- [`list_files_in_a_directory_to_json.py`](../list_files_in_a_directory_to_json.py)
  is the relocatable shim for one-directory file listing.
- [`list_files_in_a_directory_tree_to_json.py`](../list_files_in_a_directory_tree_to_json.py)
  is the relocatable shim for recursive directory-and-file listing.
- [`pyproject.toml`](../pyproject.toml) maps the corresponding installed console
  scripts to package functions.

The shims deliberately solve source-adjacent, symlinked, copied, and installed
execution. Keep import-path behavior covered when changing them.

### Runtime package

- [`directory_tree.py`](../src/python_file_walker_for_ai_agents/directory_tree.py)
  owns recursive directory traversal, directory and link nodes, sorting,
  filesystem pruning, recoverable error nodes, and streaming the tree envelope.
  Its central symbols are `DirectoryTree`, `BufferedJSON`, `main`, and `cli`.
- [`file_entries.py`](../src/python_file_walker_for_ai_agents/file_entries.py)
  owns file selection, metadata records, filename encoding, and bounded file
  batches through `entry_value`, `files_context`, and `FileObjectWriter`.
- [`file_listing.py`](../src/python_file_walker_for_ai_agents/file_listing.py)
  owns options, validation, help, and the one-directory command through
  `parse_args`, `run`, and `main`.
- [`recursive_file_listing.py`](../src/python_file_walker_for_ai_agents/recursive_file_listing.py)
  composes `DirectoryTree` with `FileObjectWriter` without a second directory
  scan. Its command boundary is `main` and `cli`.
- [`filesystem.py`](../src/python_file_walker_for_ai_agents/filesystem.py) owns
  the Python minimum and low-impact directory opening, `scandir`, descriptor,
  `O_NOATIME`, and `O_NOFOLLOW` behavior.
- [`__init__.py`](../src/python_file_walker_for_ai_agents/__init__.py) exposes the
  current import surface.

The shared flow is:

```text
shim or installed console script
  -> command module
  -> DirectoryTree and/or FileObjectWriter
  -> filesystem directory primitives
  -> compact JSON on stdout
```

There is no file-content reader, persistence layer, network service, or runtime
configuration file.

## Compatibility constraints

Runtime modules and shims intentionally use Python 3.5-compatible syntax. Avoid
f-strings, variable annotations, dataclasses, assignment expressions, modern
type-parameter syntax, and standard-library APIs introduced after 3.5 unless the
minimum version is deliberately changed across code, tests, metadata, and docs.

The standard library is the runtime boundary. `uv_build` is needed to build the
package but is not imported by the commands. Discuss any proposed runtime
dependency before adding it.

The implementation depends on Linux directory descriptors, flags, entry types,
and filename behavior. Supporting another operating system is a contract change,
not a documentation correction.

## Development environment

Create or update the locked environment from the project root:

```bash
uv sync --locked
```

Run a source shim directly or use an installed console entry point through the
environment:

```bash
./list_files_in_a_directory_tree_to_json.py --number tests
uv run --locked list-files-in-a-directory-tree-to-json --number tests
```

Help is compact JSON on stderr, so redirect it when piping into a formatter:

```bash
./list_files_in_a_directory_tree_to_json.py --help 2>&1 \
  | uv run --locked python -m json.tool
```

## Test ownership

| Test file | Primary evidence |
| --- | --- |
| [`test_file_listing.py`](../tests/test_file_listing.py) | Default file selection, metadata modes, all-entry symlink handling, raw filename bytes, counts, and incompatible options |
| [`test_recursive_file_listing.py`](../tests/test_recursive_file_listing.py) | Combined tree/file schema, shared file modes, one scan per real directory, no file opens, and recoverable missing-root output |
| [`test_relocatable_shim.py`](../tests/test_relocatable_shim.py) | Directory-only shim relocation, installed fallback, missing-package diagnostics, and declared Python minimum |
| [`test_relocatable_file_listing_shim.py`](../tests/test_relocatable_file_listing_shim.py) | One-directory shim relocation, help, installed fallback, and Python 3.5 grammar |
| [`test_relocatable_recursive_file_listing_shim.py`](../tests/test_relocatable_recursive_file_listing_shim.py) | Recursive shim relocation, option errors, installed fallback, and Python 3.5 grammar |
| [`experiments/dtree/test_directory_tree.py`](../experiments/dtree/test_directory_tree.py) | Directory core behavior under races, invalid bytes, deep trees, descriptor limits, permissions, filesystem boundaries, output failures, signals, and randomized fixtures |

Run the normal package suite:

```bash
uv run --locked python -m unittest discover -s tests -q
```

Run the deeper directory-core suite:

```bash
(cd experiments/dtree && uv run --locked python -m unittest -q test_directory_tree.py)
```

For a contract change, run the focused test first, both complete suites, and the
affected shim's help and a small safe traversal. Do not infer benchmark results
from correctness tests.

## Experiments and operational hazards

[`experiments/dtree/`](../experiments/dtree/) contains focused verification and
performance tooling for the directory-only traversal core. Its benchmark creates
and removes more than 150,000 empty entries. Read its
[`README.md`](../experiments/dtree/README.md) and provide a disposable
`--scratch-parent`; never point it at valuable storage. Optional C helpers are
Linux x86-64 instrumentation, not runtime dependencies.

[`experiments/traversal_pipeline/traverse.py`](../experiments/traversal_pipeline/traverse.py)
times recursive file-tree traversals and emits five-second heartbeats. Its
hard-coded defaults point outside this repository. In project-scoped work, pass
explicit authorized roots rather than invoking it with no arguments. The
experiment buffers each complete JSON result before parsing it, so its memory
use is proportional to output even though the underlying walker streams.

Generated distributions, virtual environments, caches, coverage output, and
`.tmp.*` work areas are ignored by Git. Keep generated evidence out of commits
unless the user explicitly asks to preserve it.

## Verification gaps

- No CI configuration is tracked. All checks are currently local and manual.
- The current locked development run uses Python 3.12. Tests parse runtime files
  with Python 3.5 grammar, but that is not a substitute for executing the current
  checkout on a Python 3.5 interpreter.
- The dated directory-tree report records earlier Python 3.5 and optional native
  instrumentation runs; it is historical evidence, not proof for later commits.
- No documentation-link checker or Markdown linter is configured. Validate
  repository-relative links when documentation changes.
- Benchmarks cover warm-cache `tmpfs`; they do not characterize cold disks,
  physical I/O, network filesystems, or every mount topology.

Record newly verified coverage or remaining gaps without overstating what a
tool, test, or historical report proves.

## Documentation and versions

Keep the root README short and link every maintained documentation file from its
grouped documentation index. Put command behavior in the CLI reference, source
and verification guidance here, agent-only process in `AGENTS.md`, and dated
change history in `VERSION_TRACKER.md`.

Use `Unreleased` for pending work. The project version is owned by
`pyproject.toml`; update the version tracker when that identifier changes. Keep
dated reports scoped to the exact command, environment, and commit they actually
measure.
