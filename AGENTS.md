# elenchos

Local LLM benchmark CLI. Design: `docs/design.md`.

## Commands

- `uv sync --all-groups`
- `uv run pytest`
- `uv run elenchos run --prompts prompts/sample.jsonl`

## Conventions

- Python 3.11+; code in `src/elenchos/`
- Small diffs; match existing style
- No git commits unless asked
- **Terminal UI**: use `rich` for all CLI output — import shared `Console` from `elenchos.console`. Tables/panels/metrics on stdout; no bare `print()`.
- **Logging**: configure `logging` with `RichHandler` (via `elenchos.console`); colored stderr by level (INFO cyan, WARNING yellow, ERROR red). Library code logs; commands render user-facing results with `Console`.

## Communication

Terse caveman mode. Baseline always on via user rule. Full levels/examples/boundaries: read `~/.cursor/skills/caveman/SKILL.md` when switching intensity or edge cases — do not duplicate here.

**Answer first.** Lead with clear direct answer. Explanation after — only if user asked, or answer unclear without it. No TMI. No preamble, no recap, no "here's what I did" unless requested.
