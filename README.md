# PYTHON_FILE_WALKER_FOR_AI_AGENTS

Python file traversal tooling for AI agents.

**Development mode: EXP** — rapid, evidence-led experimentation; make small
changes, run representative cases, and adapt to observed behavior.

**State:** initialized Python 3.12 project with the Modular Vertical Architecture
(MVA) v0.3.0 baseline. The installed command currently prints a starter greeting.
File-walking behavior and its first experiment are still to be defined.

## Run the scaffold

```bash
uv sync --locked
uv run --locked python-file-walker-for-ai-agents
```

The package lives in `src/python_file_walker_for_ai_agents/`.

## Architecture

Start with [ARCHITECTURE.md](ARCHITECTURE.md) and
[AGENTS.md](AGENTS.md). Validate the architecture baseline with:

```bash
uvx --from "git+https://github.com/squizzster/MODULAR_VERTICAL_ARCHITECTURE-MODULAR_VERTICAL_ARCHITECTURE.git@v0.3.0" mva validate .
```

The starter architecture catalogue has no application modules or features yet.
Validation checks the declared artifacts; it does not verify file traversal.

Keep temporary work in ignored `.tmp.*` directories within this project.
