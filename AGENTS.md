# lmbench

Local LLM benchmark CLI (LM Studio). Design: `docs/design.md`.

## Commands

- `uv sync --all-groups`
- `uv run pytest`
- `uv run lmbench run --prompts prompts/sample.jsonl`

## Conventions

- Python 3.11+; code in `src/lmbench/`
- Small diffs; match existing style
- No git commits unless asked
- **No tests** — do not add or write tests unless explicitly requested
- **No new `.md` files** — do not create markdown docs unless explicitly requested
- **Existing `.md` files** — ask before editing or updating any markdown file
