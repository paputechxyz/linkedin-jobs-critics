# linkedin-jobs-critics

A one-shot langchain critic that checks whether the [`linkedin-jobs`](https://github.com/paputechxyz/linkedin-job-cli) Go CLI parsed a single job's fields correctly, by comparing stored parsed values against the job's full description. It writes an improvement-plan markdown file of findings for a human to fix by hand.

## What it does

Given a LinkedIn **job id**, critics:

1. **Looks it up** in the local DB via `linkedin-jobs show <id> --json`.
2. **Fetches if missing** — if the job isn't stored, critics runs `linkedin-jobs score-job <id>` to fetch + score it first, then reads it back.
3. **Critics judge** compares each parsed field (`salary`, `location`, `remote_type`, `title`, `company`) against the full description — the ground truth — using an LLM with provider-enforced structured output.
4. **Improvement-plan MD** lists each defect with the stored value, a verbatim quote from the description as evidence, and the source location to fix. If nothing is wrong, it says so.

No loop, no coding agent. You apply the fixes by hand.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or pip).

```bash
uv sync            # or: python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Build the Go CLI and put it on your `PATH` (or set `LJ_BIN_PATH`):

```bash
( cd ../linkedin-job-cli && go build -o linkedin-jobs . )
export PATH="$PWD/../linkedin-job-cli:$PATH"
```

Configure an OpenAI-compatible LLM provider once (shared with the Go CLI):

```bash
linkedin-jobs config llm        # or: export OPENAI_API_KEY=sk-...
```

## Run

```bash
uv run critics 4259504707 -o improvement-plan.md
```

If the job is already in the DB it is judged immediately; otherwise critics runs
`linkedin-jobs score-job <id>` to fetch + score it first, then judges it.

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
