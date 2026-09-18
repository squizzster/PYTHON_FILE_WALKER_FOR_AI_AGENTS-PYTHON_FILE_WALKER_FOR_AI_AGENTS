# PYTHON_FILE_WALKER_FOR_AI_AGENTS

Python file traversal tooling for AI agents.

**Development mode: EXP** — rapid, evidence-led experimentation; make small
changes, run representative cases, and adapt to observed behavior.

**State:** initialized Python 3.12 project with the Modular Vertical Architecture
(MVA) v0.3.0 baseline. An imported Linux directory-tree implementation and its
native test suite, benchmarks, recorded results, and checksum manifest live under
[`experiments/dtree/`](experiments/dtree/README.md) for evaluation. The installed
command still prints a starter greeting; the candidate has not yet been promoted
into the package's public CLI.

## Run the scaffold

```bash
uv sync --locked
uv run --locked python-file-walker-for-ai-agents
```

The package lives in `src/python_file_walker_for_ai_agents/`.

## Candidate implementation

The `experiments/dtree/` bundle retains its imported layout so its `SHA256SUMS`
file and reproduction commands remain useful. It targets Linux, invokes no
external filesystem walker, uses only the Python standard library at runtime,
and emits a streamed directory-only JSON tree. Hidden directories are always
included, children are sorted, directory symlinks are leaves, and traversal
stays on the root filesystem. See the experiment's
[README](experiments/dtree/README.md) and
[benchmark report](experiments/dtree/BENCHMARK_REPORT.md).

## Architecture

Start with [ARCHITECTURE.md](ARCHITECTURE.md) and
[AGENTS.md](AGENTS.md). Validate the architecture baseline with:

```bash
uvx --from "git+https://github.com/squizzster/MODULAR_VERTICAL_ARCHITECTURE-MODULAR_VERTICAL_ARCHITECTURE.git@v0.3.0" mva validate .
```

The starter architecture catalogue has no application modules or features yet.
Validation checks the declared artifacts; it does not verify file traversal.

Keep temporary work in ignored `.tmp.*` directories within this project.
