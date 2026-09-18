# PYTHON_FILE_WALKER_FOR_AI_AGENTS

Linux directory-tree JSON streamer for AI-agent tooling.

```text
mode: EXP
python: >=3.12
runtime_dependencies: []
platform: Linux
implementation: src/python_file_walker_for_ai_agents/directory_tree.py
shim: python_file_walker_for_ai_agents.py
```

## Contract

- Input: exactly one directory location.
- Hidden directories: included.
- Ordering: sorted using `LC_COLLATE`; byte order in C/POSIX locales.
- Directory symlinks: emitted as leaf nodes; never traversed.
- Other symlinks and non-directories: omitted.
- Filesystem boundary: directories with a different `st_dev` are emitted as
  pruned leaves and not enumerated.
- Output: one compact JSON document plus newline on stdout.
- Runtime: Python standard library only; no external filesystem walker.

## Run

```bash
./python_file_walker_for_ai_agents.py LOCATION
uv run --locked python-file-walker-for-ai-agents LOCATION
```

`-h`, `--help`, `-help`, or no location emits the compact JSON contract to
stderr. Explicit help exits `0`; a missing or invalid argument count exits `2`.

The executable shim works from any current directory. A symlink resolves the
adjacent source package. A copied shim, including one placed in `/usr/local/bin`,
imports `python_file_walker_for_ai_agents` from the Python interpreter selected
by `/usr/bin/env python3`; install the package into that interpreter first.

## Output

```json
{"tree":{"type":"directory","name":"LOCATION","children":[{"type":"directory","name":"NAME","children":[]},{"type":"link","name":"NAME","target":"TARGET"}]},"complete":true,"errors":0}
```

Invalid filename bytes add authoritative `name_bytes_b64` or
`target_bytes_b64`. Failed directory nodes add `error`. Cross-filesystem nodes
add `"pruned":"different-filesystem"`.

| Exit | Meaning |
| ---: | --- |
| 0 | Complete selected traversal and successful output flush. |
| 1 | Partial traversal, root failure, output failure, or memory failure. |
| 2 | Invalid invocation or unsupported runtime. |
| 130 | Interrupted. |
| 141 | Broken pipe. |

## Verify

```bash
uv sync --locked
uv run --locked python -m unittest -q tests/test_relocatable_shim.py
(cd experiments/dtree && uv run --locked python -m unittest -q test_directory_tree.py)
```

Benchmark and low-level verification assets are in `experiments/dtree/`.
