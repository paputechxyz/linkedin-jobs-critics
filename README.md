# linkedin-jobs-critics

A langchain critic that checks whether the [`linkedin-jobs`](https://github.com/paputechxyz/linkedin-job-cli) Go CLI parsed a single job's fields correctly, by comparing stored parsed values against the job's full description. It writes an improvement-plan markdown of findings and — optionally — runs a human-gated judge→fix→re-judge loop that spawns an opencode coding agent in the sibling CLI repo to apply the fixes.

## What it does

Given a LinkedIn **job id**, critics:

1. **Looks it up** in the local DB via `linkedin-jobs show <id> --json`.
2. **Fetches if missing** — if the job isn't stored, critics runs `linkedin-jobs score-job <id>` to fetch + score it first, then reads it back.
3. **Critics judge** compares each parsed field (`salary`, `location`, `remote_type`, `title`, `company`) against the full description — the ground truth — using an LLM with provider-enforced structured output.
4. **Improvement-plan MD** lists each defect with the stored value, a verbatim quote from the description as evidence, and the source location to fix. If nothing is wrong, it says so and exits.
5. **Agent loop (optional)** — if defects are found, prompts `Proceed to spawn opencode agent? [y/N]`. On yes, hands the defects to an interactive [opencode](https://opencode.ai) session in the sibling `linkedin-job-cli` repo. When you exit opencode, critics re-scores + re-judges; clean ends the loop, still-defective writes a fresh plan and re-prompts. Each round carries prior-round history so the agent doesn't repeat dead ends.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or pip).

```bash
uv sync            # or: python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

For LangSmith tracing (optional), install the extra:

```bash
uv sync --extra tracing   # or: pip install -e ".[tracing]"
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

### For the agent loop (optional)

The loop hands parser defects to a coding agent in the sibling repo. It needs three extra things:

- **[opencode](https://opencode.ai)** on your `PATH` — the coding agent TUI.
- **[just](https://github.com/casey/just)** on your `PATH` — the sibling repo's `justfile` has a `just build` recipe that bumps the patch version when Go source changes. critics checks `linkedin-jobs version` before and after each agent round and rejects the round if it's unchanged or `dev`, so the agent MUST rebuild via `just build` (not plain `go build`, which leaves the version at `dev`).
- **The sibling repo** at `../linkedin-job-cli` (relative to where you run critics), or set `LJ_CLI_DIR`.

## Run

```bash
uv run critics 4259504707 -o improvement-plan.md
```

Pass one or more job ids, comma-separated; each runs its own judge→fix→re-judge
loop in turn:

```bash
uv run critics 4259504707,4259504708,4259504709 -o improvement-plan.md
```

If a job is already in the DB it is judged immediately; otherwise critics runs
`linkedin-jobs score-job <id>` to fetch + score it first, then judges it.

If the plan lists defects and you answer `y` at the prompt, an opencode TUI opens
in `../linkedin-job-cli` with the defects pre-loaded. Supervise the agent, then
**exit opencode with `/exit`** (or `/q`, or `Ctrl+x` then `q`) — do **not**
Ctrl+C, that kills critics too. On exit, critics:

1. Checks `linkedin-jobs version` is newer than before the round (and not `dev`) —
   if not, the agent skipped `just build`; critics stops without re-scoring.
2. Re-scores the job and re-judges it (all fields, so regressions surface).
3. Reports success if clean, or writes a fresh improvement plan and re-prompts.

critics never commits — you commit manually in `linkedin-job-cli`.

## Config

| Variable | Purpose | Default |
|---|---|---|
| `LJ_BIN_PATH` | path to the `linkedin-jobs` binary | `linkedin-jobs` on `PATH` |
| `LJ_CONFIG_DIR` | dir for the Go CLI's `config.json` | `~/.linkedin-jobs` |
| `LJ_CLI_DIR` | path to the sibling `linkedin-job-cli` repo (for the agent loop) | `../linkedin-job-cli` |
| `OPENAI_API_KEY` / `LJ_LLM_API_KEY` | LLM key (env fallback) | — |
| `OPENAI_BASE_URL` / `LJ_LLM_BASE_URL` | OpenAI-compatible base URL | `https://api.openai.com/v1` |
| `LJ_LLM_MODEL` | model name | `gpt-4o-mini` |

The provider config is reused from the Go CLI's `~/.linkedin-jobs/config.json` — one key store.

## Tracing with LangSmith

Critics lights up [LangSmith](https://smith.langchain.com) tracing automatically
as soon as a LangSmith API key is in the environment — no code changes needed.
Every LLM call, the LangGraph step transitions, and the `judge_job` span land
in your project so you can inspect prompts, responses, token usage, and errors.

```bash
export LANGSMITH_API_KEY=lsv2_sk_...
uv run critics 4259504707 -o improvement-plan.md
# -> "Tracing enabled (LangSmith project: linkedin-jobs-critics)."
```

Runs the trace to the `linkedin-jobs-critics` project by default. Override with
`LANGSMITH_PROJECT`. No key? Critics runs normally, just untraced.

| Variable | Purpose | Default |
|---|---|---|
| `LANGSMITH_API_KEY` (or `LANGCHAIN_API_KEY`) | LangSmith API key; enables tracing when set | unset = tracing off |
| `LANGSMITH_PROJECT` (or `LANGCHAIN_PROJECT`) | project name runs are logged under | `linkedin-jobs-critics` |
| `LANGSMITH_TRACING` | force tracing on/off | `true` once a key is present |

To view traces, open the project at
`https://smith.langchain.com/<your-org>/projects/p/<project>`.

## Test

```bash
pytest
```
