# linkedin-jobs-critics

A one-shot langchain critic that checks whether the [`linkedin-jobs`](https://github.com/paputechxyz/linkedin-job-cli) Go CLI parsed each job's fields correctly, by comparing stored parsed values against the job's full description. It writes an improvement-plan markdown file of findings for a human to fix by hand.

## What it does

1. **Search agent** runs `linkedin-jobs search <keywords> <location> --force-overwrite --json` to populate/refresh the DB. The `--force-overwrite` flag (added by this feature) bypasses dedup so already-stored jobs are re-parsed + re-scored + overwritten.
2. **Critics judge** reads every stored job (`list --json`) and, for each parsed field (`salary`, `location`, `remote_type`, `title`, `company`), decides whether the stored value agrees with the full description — the ground truth — using an LLM with provider-enforced structured output.
3. **Improvement-plan MD** lists each defect with the stored value, a verbatim quote from the description as evidence, and the source location to fix. If nothing is wrong, it says so.

No loop, no coding agent. You apply the fixes by hand.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or pip).

```bash
uv sync            # or: python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Build the Go CLI and put it on your `PATH` (or set `LJ_BIN_PATH`):

```bash
( cd ../critics && go build -o linkedin-jobs . )
export PATH="$PWD/../critics:$PATH"
```

Configure an OpenAI-compatible LLM provider once (shared with the Go CLI):

```bash
linkedin-jobs config llm        # or: export OPENAI_API_KEY=sk-...
```

## Run

```bash
critics "Senior Engineer" Toronto -o improvement-plan.md
```

To judge jobs already in the DB without running a fresh search:

```bash
critics "Senior Engineer" Toronto --skip-search
```

## Config

| Variable | Purpose | Default |
|---|---|---|
| `LJ_BIN_PATH` | path to the `linkedin-jobs` binary | `linkedin-jobs` on `PATH` |
| `LJ_CONFIG_DIR` | dir for the Go CLI's `config.json` | `~/.linkedin-jobs` |
| `OPENAI_API_KEY` / `LJ_LLM_API_KEY` | LLM key (env fallback) | — |
| `OPENAI_BASE_URL` / `LJ_LLM_BASE_URL` | OpenAI-compatible base URL | `https://api.openai.com/v1` |
| `LJ_LLM_MODEL` | model name | `gpt-4o-mini` |

The provider config is reused from the Go CLI's `~/.linkedin-jobs/config.json` — one key store.

## Test

```bash
pytest
```
