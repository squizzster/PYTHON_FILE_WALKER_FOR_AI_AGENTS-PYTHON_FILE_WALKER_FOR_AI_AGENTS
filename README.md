# Python File Walker for AI Agents

Python File Walker for AI Agents turns Linux directory contents into compact,
machine-readable JSON. Its three command-line interfaces cover a sorted
directory-only tree, a one-directory file listing, and a recursive tree
that attaches files to every directory. This gives agents and automation a
predictable inventory without parsing human-oriented shell output.

The walkers never open or read file contents. Recursive traversal scans each
real directory once, includes hidden entries, treats descendant directory
symlinks as leaves, and stays on the root directory's filesystem. Streaming
encoders and bounded internal batches avoid building the complete JSON result in
walker memory, while explicit completion and error fields let consumers detect
partial results.

The runtime uses only the Python standard library. It requires **Linux and
Python 3.5 or newer**. The current package version is `0.1.0`, and development
mode is **EXP**: behavior is evidence-led and interfaces may still change.

## Documentation

### Use the tools

- [CLI reference](docs/CLI_REFERENCE.md) — commands, options, JSON contracts,
  ordering, filesystem boundaries, exit statuses, and safe consumption.
- [Version tracker](VERSION_TRACKER.md) — pending changes and dated `0.1.0`
  history.

### Develop and maintain

- [Development guide](docs/DEVELOPMENT.md) — authoritative source map,
  repository layout, verification workflow, experiments, and known gaps.
- [Agent instructions](AGENTS.md) — project-specific constraints and completion
  requirements for automated contributors.

### Verification evidence

- [Directory-tree verification assets](experiments/dtree/README.md) — focused
  tests, benchmarks, and optional Linux instrumentation.
- [Directory-tree verification snapshot](experiments/dtree/BENCHMARK_REPORT.md)
  — dated correctness and warm-cache benchmark results.
