# Version tracker

This file records pending and historical project changes. The package version is
declared in [`pyproject.toml`](pyproject.toml). Git history currently contains no
version tag, so the `0.1.0` section is tied to the manifest and commit dates
rather than a release tag.

## Unreleased

**Status:** pending documentation changes

### Added

- A consolidated CLI reference for all three commands, their JSON contracts,
  options, filesystem boundaries, and failure behavior.
- A development guide mapping public behavior to source, tests, experiments,
  compatibility constraints, and known verification gaps.
- This version tracker.

### Modified

- Reframed the README as a compact product overview and complete documentation
  index.
- Replaced generic agent guidance with instructions specific to the walker.
- Clarified the scope and historical status of directory-tree verification
  documents.

### Removed

- Unused generic architecture documentation, templates, and validator
  configuration that had no runtime, package, or test integration.

## 0.1.0 — 2026-09-18

**Status:** current manifest version; no matching Git tag

### Added

- A Linux directory-only JSON walker with sorted hidden-directory traversal,
  directory-symlink leaves, same-filesystem pruning, streamed output, and
  explicit partial-result reporting.
- A relocatable source shim and installed `python-file-walker-for-ai-agents`
  console command.
- A non-recursive regular-file listing command with count, inode, permissions,
  full-stat, all-entry, and base64 filename modes.
- A recursive command that combines the directory tree and file listings in one
  process and one scan per real directory.
- Focused unit, relocation, race, failure, deep-tree, and benchmark assets.

### Modified

- Restored and documented Python 3.5 runtime compatibility while retaining
  Python 3.12 as the development version.
