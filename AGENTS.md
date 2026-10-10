# Repository instructions for AI agents

## Project scope

This repository is an experimental Linux command-line package that emits
filesystem listings as compact JSON. Work only within this repository unless
the user explicitly expands the scope.

Read `README.md`, `docs/CLI_REFERENCE.md`, and `docs/DEVELOPMENT.md` before a
non-trivial change. Then inspect the affected implementation, executable shim,
tests, and package entry point. Keep unrelated files out of context and out of
the change.

## Runtime contracts

Preserve these constraints unless the user explicitly changes the contract:

- Linux and Python 3.5 or newer.
- Python standard-library-only runtime; build tooling is not a runtime dependency.
- Three distinct CLIs: directory tree, one-directory file listing, and recursive
  directory-and-file listing.
- File contents are never opened or read.
- Descendant directory symlinks are leaves and are never traversed.
- Recursive traversal remains on the root directory's filesystem.
- Hidden directories and files follow the contract of the selected CLI.
- JSON is streamed with bounded internal buffers; traversal is a live listing,
  not a filesystem snapshot.
- Exit status, stdout, and stderr behavior are part of each CLI contract.
- Runtime source and shims must retain Python 3.5-compatible syntax.

Treat help documents in the CLI modules, console scripts in `pyproject.toml`,
and tested JSON shapes as public interfaces. Keep them aligned when an interface
changes.

## Change approach

State the intended outcome and affected contract before implementation. Prefer
the smallest coherent change supported by observed behavior. Keep shared
filesystem opening in `filesystem.py`, shared file-entry encoding in
`file_entries.py`, directory traversal in `directory_tree.py`, and command
composition in the command-specific modules unless evidence warrants a new
boundary.

Do not weaken error, race, symlink, filename-byte, descriptor, or output-failure
coverage to make a change pass. Do not describe a best-effort live traversal as
an atomic snapshot.

## Verification

Run the narrowest affected tests first, then the complete relevant suites:

```bash
uv run --locked python -m unittest discover -s tests -q
(cd experiments/dtree && uv run --locked python -m unittest -q test_directory_tree.py)
```

Run CLI help or a safe fixture traversal when a command contract or example
changes. Benchmarking is optional and potentially expensive; read
`experiments/dtree/README.md` before running it.

Never claim an unexecuted check passed. Report unavailable Python versions,
platforms, CI, or optional instrumentation as verification gaps.

## Completion report

Report the outcome, files changed, public-contract impact, commands actually
executed and their results, unverified assumptions, and any remaining hazards.
