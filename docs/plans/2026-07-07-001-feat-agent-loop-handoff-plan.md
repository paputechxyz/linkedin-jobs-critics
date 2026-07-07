---
title: "critics Agent Loop Handoff - Plan"
type: feat
date: 2026-07-07
topic: agent-loop-handoff
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# critics Agent Loop Handoff - Plan

## Goal Capsule

- **Objective:** Add an optional, human-gated judge→fix→re-judge loop to critics that hands parser defects to an interactive opencode agent in the sibling `linkedin-job-cli` repo, re-judges after each round, and loops until clean or the user stops.
- **Product authority:** this brainstorm, requirements-only.
- **Open blockers:** none blocking planning.

---

## Product Contract

### Summary

critics gains a loop. After writing the improvement plan it prompts yes/no; on yes it launches an interactive opencode session in `linkedin-job-cli` with the current defects pre-loaded and the agent instructed to rebuild after fixing. When the session ends, critics re-scores and re-judges — clean ends the loop, still-defective writes a fresh plan and prompts again. Each agent round carries prior-round history. critics never commits.

### Problem Frame

Today critics writes `improvement-plan.md` and stops; fixes are applied by hand. That works, but the round-trip — read the plan, open the sibling repo, locate the parser code, fix, rebuild, re-score, re-judge — is manual and repeated for each defect. The loop collapses that round-trip into critics while keeping a human gate on every agent run, so nothing fixes code without explicit approval.

### Requirements

**Trigger & gating**

- R1. After writing the improvement plan, critics prompts the user at the terminal with a yes/no to decide whether to spawn the opencode agent. Default is no (stop).
- R2. If the plan reports no defects, critics skips the prompt and exits.
- R3. The user is re-prompted before every agent round, not just the first.

**Agent handoff**

- R4. On yes, critics launches an interactive opencode session with its working directory set to the `linkedin-job-cli` sibling repo.
- R5. The opening prompt given to opencode contains the current defects (field, stored value, evidence, suggested fix) from the improvement plan.
- R6. The handoff prompt instructs the agent to rebuild via `just build` after applying fixes.
- R7. The sibling repo path defaults to a sibling `linkedin-job-cli` directory and is overridable by an environment variable, consistent with the existing `LJ_BIN_PATH` pattern.

**Round context**

- R8. Each agent round after the first receives the history of prior rounds: what defects were attempted and what the previous re-judge still flagged as failing.

**Re-judge loop**

- R9. After each opencode session ends, critics re-scores the job (`linkedin-jobs score-job`) and re-judges it against the description.
- R10. If re-judge finds no defects, critics reports success and exits the loop.
- R11. If re-judge finds defects, critics writes a fresh improvement plan and re-prompts per R1/R3.
- R12. Re-judge assesses all parsed fields each round, not just previously-failing ones, so regressions surface.
- R15. Before each round's re-score, critics reads `linkedin-jobs version` before and after the agent session; if unchanged or `"dev"`, it refuses to re-score, surfaces the reason, and stops the loop.

**Commits & termination**

- R13. critics never commits, stages, or pushes changes in `linkedin-job-cli`; commits are the user's manual responsibility.
- R14. The loop terminates when re-judge passes clean, or the user declines the prompt.

### Key Decisions

- **Interactive opencode session, not `opencode run`.** You supervise the agent live and can redirect mid-task; the trade is critics' process blocks until you exit the session.
- **Agent owns the Go rebuild; critics owns re-score + re-judge.** Keeps the opencode session self-contained; critics trusts the binary on `PATH` is fresh when re-scoring.
- **Whole-plan handoff per round.** Every current defect goes to the agent each round; no per-finding selection UI.
- **User-gated termination, no hard iteration cap.** You decide before every round; no surprise auto-stop.

### Actors

- A1. The user — reviews each plan, answers the yes/no gate, supervises the opencode session live, commits manually.
- A2. critics (Python CLI) — writes plans, prompts the gate, launches the agent, re-scores and re-judges, carries round context.
- A3. The opencode agent — runs inside an interactive opencode session in `linkedin-job-cli`, applies parser fixes, rebuilds the binary.

### Key Flows

- F1. First-round handoff.
  - **Trigger:** critics has written an improvement plan containing at least one defect; user answers yes.
  - **Actors:** A2, A1, A3.
  - **Steps:** critics builds the opening prompt from the current findings; launches opencode in the sibling repo; user supervises as A3 fixes and rebuilds; user exits the session; A2 re-scores and re-judges.
  - **Covered by:** R1, R4, R5, R6, R9.
- F2. Convergence (clean re-judge).
  - **Trigger:** re-judge after an agent round finds no defects.
  - **Actors:** A2, A1.
  - **Steps:** A2 reports success; loop exits; A1 inspects the diff and commits manually.
  - **Covered by:** R10, R13, R14.
- F3. Repeat round (still defective).
  - **Trigger:** re-judge still finds defects.
  - **Actors:** A2, A1, A3.
  - **Steps:** A2 writes a fresh improvement plan; A2 re-prompts; on yes, A2 launches a new session with prior-round history in the opening prompt; loop continues.
  - **Covered by:** R3, R8, R11.
- F4. Stop.
  - **Trigger:** user answers no at the gate (any round).
  - **Actors:** A2, A1.
  - **Steps:** A2 exits the loop without launching an agent; A1 may still commit whatever the last session changed.
  - **Covered by:** R1, R14.

### Acceptance Examples

- AE1. Single-defect job, fixed first try.
  - **Covers R1, R5, R9, R10, R13.**
  - **Given** critics judges a job and finds one salary defect, writes the plan, and prompts yes/no.
  - **When** the user answers yes, the agent fixes the parser and rebuilds, and the user exits the session.
  - **Then** critics re-scores and re-judges; re-judge finds no defects; critics reports success and exits without committing.
- AE2. Defect persists after round one.
  - **Covers R3, R8, R11.**
  - **Given** round one's re-judge still flags the salary defect.
  - **When** critics writes a fresh plan and re-prompts.
  - **Then** on yes, the round-two agent session receives round-one history (what was attempted, what still fails) in its opening prompt.
- AE3. Regression on a previously-clean field.
  - **Covers R12.**
  - **Given** a round's parser fix corrects salary but breaks a previously-clean `location` field.
  - **When** critics re-judges.
  - **Then** the fresh improvement plan lists `location` as a new defect, not just the original salary issue.
- AE4. Agent skipped the rebuild or bypassed `just build`.
  - **Covers R6, R9, R15.**
  - **Given** the agent applied a fix but did not rebuild, or rebuilt with plain `go build` (producing a `dev` binary).
  - **When** critics reads `linkedin-jobs version` after the session.
  - **Then** the version is unchanged or `dev`; critics surfaces that the binary was not rebuilt via `just build`, skips re-score, and stops the loop. The failure is detected, not silent.
- AE5. No defects from the start.
  - **Covers R2.**
  - **Given** the initial judge finds every field consistent.
  - **When** critics writes the plan.
  - **Then** critics exits without prompting, since there is nothing to fix.

### Scope Boundaries

**Deferred for later**

- Per-finding selection (pick a subset of defects to send per round) — whole-plan handoff covers the need today.
- Cross-job batch loops — critics remains single-job.

**Outside this product's identity**

- critics authoring or committing Go code itself — the opencode agent does the code work; critics orchestrates.
- critics pushing to a remote or opening PRs — manual commit is the stated workflow.

### Dependencies / Assumptions

- The `opencode` binary is available on `PATH` (verified at `/Users/patrickpu/.opencode/bin/opencode`, v1.17.15).
- The `linkedin-job-cli` sibling repo exists at `../linkedin-job-cli` relative to critics' working directory (verified).
- The existing `score-job` and `show` subprocess wrappers in `src/critics/tools.py` are reused for re-score; the existing judge in `src/critics/judge.py` is reused for re-judge.
- `Finding.suggested_fix` (`src/critics/judge.py:49`) already points at source locations, so the handoff prompt's "where to fix" comes from existing data — no schema change required for v1.
- The sibling repo's `just build` recipe (`../linkedin-job-cli/justfile:3-36`) bumps the patch version when Go source changes and stamps it via ldflags; the version check (R15) depends on the agent using `just build`, which requires `just` on PATH.
- critics verifies a version diff (R15) rather than trusting the binary on `PATH`/`LJ_BIN_PATH` is fresh; the old silent-re-confirm failure mode is now a detected fail-stop (AE4).

### Outstanding Questions

**Resolved in planning**

- Round-context shape: in-memory list of round summaries, inlined into each subsequent round's prompt. No session file for v1. See KTD-2.
- Handoff prompt construction: findings inlined into `--prompt` rather than referencing the plan file by path, to avoid the two-repo working-directory split. See KTD-3.

**Deferred to implementation**

- Exact wording of the rebuild instruction in the handoff prompt — implementer picks phrasing that makes "rebuild after fixing" unambiguous (R6, AE4 depend on it being legible to the agent).

### Sources / Research

- `src/critics/cli.py:31` — current `main()` flow: judge → `write_report` → exit. The loop inserts between `write_report` and exit.
- `src/critics/report.py:10` — `write_report()` returns the path; the loop re-invokes it after each re-judge.
- `src/critics/judge.py:17,38,49` — `PARSED_FIELDS`, `Finding`, `CritiqueReport` schemas; reused as-is.
- `src/critics/tools.py:16,44,51` — `binary()`, `show_job()`, `score_job()`; `score_job` is the re-score path, `_run` (line 20) is the subprocess wrapper pattern a new opencode-launch helper would mirror.
- `improvement-plan.md` — sample output showing the defect/evidence/suggested-fix shape the handoff prompt carries.
- Sibling repo `../linkedin-job-cli/` — Go CLI target; `internal/` holds parser source the agent edits.

---

## Planning Contract

### Product Contract Preservation

Product Contract unchanged. All R/A/F/AE IDs preserved as-is; planning adds the HOW around them.

### Key Technical Decisions

- **KTD-1. opencode invocation shape.** Launch the interactive TUI via `opencode <repo-path> --prompt "<handoff prompt>"`. The `<repo-path>` positional sets the working directory; `--prompt` loads the opening message. This requires a subprocess that inherits the TTY, so it must NOT reuse `src/critics/tools.py:20` `_run` (which sets `capture_output=True` and would starve the TUI). A new non-capturing subprocess helper lives alongside it. Chosen over `opencode run` per the brainstorm decision (live supervision).
- **KTD-2. Round context is in-memory, passed inline.** Each critics invocation accumulates a list of round summaries in memory; `build_handoff_prompt` inlines the relevant history into the prompt for rounds > 1. No session file is written for v1 — the loop is short and user-gated, so on-device persistence is unnecessary carrying cost. If critics is re-run, history starts fresh.
- **KTD-3. Handoff prompt inlines findings rather than referencing the plan file.** The plan file lives in critics' working directory while the agent runs in the sibling repo; a relative path would not resolve and an absolute path is non-portable. Inlining the defects (field, stored value, evidence, suggested fix) into `--prompt` avoids the cross-directory problem entirely. The agent does not need to read `improvement-plan.md`.
- **KTD-4. Sibling repo path resolution mirrors the existing env pattern.** Default to `<cwd>/../linkedin-job-cli`, overridable via a new `LJ_CLI_DIR` environment variable, consistent with `LJ_BIN_PATH` (`src/critics/tools.py:16`) and `LJ_CONFIG_DIR` (`src/critics/config.py:23`). If the resolved path is not an existing directory, fail fast with a clear message rather than letting opencode fail opaquely.
- **KTD-5. Loop wiring extracts the judge step in `cli.py`.** `src/critics/cli.py:31` `main()` currently inlines judge → write_report → exit. The loop inserts between write_report and exit. To avoid duplicating the judge call, extract a `judge_and_report(job, llm, out_path)` helper (or similar) that both the first pass and each re-judge round call. The yes/no gate, agent launch, re-score, and re-judge form the loop body.
- **KTD-6. critics never builds the Go binary; the agent rebuilds via `just build`.** Per the brainstorm decision, the agent owns the rebuild. critics verifies a version diff (R15) rather than trusting the binary on `PATH`/`LJ_BIN_PATH`. critics only calls `score_job` (`src/critics/tools.py:51`) which re-fetches + re-scores. The old "trust the binary is fresh" risk is now mitigated by the version check.
- **KTD-7. Version check rides on the sibling repo's `just build` recipe.** `../linkedin-job-cli/justfile:3-36` hashes every Go source file and bumps the patch version when source changes, then builds with `-ldflags -X linkedin-jobs/cmd.Version=$VERSION`. So `linkedin-jobs version` differs across source-changing rebuilds. The `dev` rejection enforces `just build` discipline: a plain `go build` leaves `Version = "dev"` (`cmd/version.go:12`), which critics rejects. Requires `just` on PATH (the agent invokes `just build`).

### Alternatives Considered

- **`opencode run` (non-interactive) for the agent.** Rejected in brainstorm — user wants to supervise the agent live and redirect mid-task. `opencode run` would return a finished result with no in-session intervention.
- **Session file for round context.** Rejected for v1 (KTD-2). Would add a file-format and lifecycle to maintain; the in-loop memory is sufficient for a user-gated short loop.
- **critics owns the Go rebuild.** Rejected in brainstorm — keeps the opencode session self-contained and avoids critics learning the build command for a repo it does not own.
- **Per-finding selection UI at the prompt.** Rejected in brainstorm scope boundaries — whole-plan handoff each round.

### Risks

- **`--prompt` runtime semantics unverified.** The `--prompt` flag appears in `opencode --help` but its exact behavior (loaded as the opening user message vs. a system instruction) was not runtime-verified during planning. Implementer should smoke-test `opencode <dir> --prompt "hello"` once before wiring the loop; if it does not behave as an opening message, fall back to `opencode <dir>` with the prompt printed to the terminal for the user to paste, and note the regression. Assumption, not a blocker.
- **Non-TTY environments.** The interactive TUI requires a terminal. If critics is run in a pipeline or non-interactive shell, `opencode` will fail to draw its UI. Mitigation: detect `sys.stdin.isatty()` before launching and error with a clear message ("interactive agent requires a TTY") rather than spawning a broken session.
- **Re-score re-fetches over the network.** `score-job` always re-fetches from LinkedIn (`cmd/score_job.go:34`), so each loop round is a network call subject to the existing rate-limit / cookie-auth behavior of the Go CLI. This is inherited behavior, not new risk, but means a loop round is not free.
- **Round-context growth.** Over many rounds the inlined history grows the prompt. Low risk for v1 because termination is user-gated each round; if it ever becomes a problem, summarize older rounds rather than dumping them verbatim.
- **`just` missing or wrong build target.** The version check (R15) depends on the agent running `just build` (not `just serve` or plain `go build`). If `just` is missing, the agent's build step fails and the version won't bump — critics then fail-stops on the unchanged version, which is the correct safe behavior, but the user sees a version-check message rather than the root cause. Mitigation: the handoff prompt names `just build` explicitly and notes that `just` must be on PATH.

---

## Implementation Units

### U1. `src/critics/agent.py` + `tools.py` — handoff + version-check primitives

**Goal:** Encapsulate sibling-repo path resolution, handoff-prompt construction, opencode session launch, and the linkedin-jobs version probe as pure, testable functions isolated from the loop orchestration.

**Files:**
- `src/critics/agent.py` (new)
- `src/critics/tools.py` (add `cli_version`)
- `tests/test_agent.py` (new)
- `tests/test_tools.py` (add `cli_version` scenarios)

**Patterns:**
- Env-first path resolution mirroring `src/critics/tools.py:16` `binary()` and `src/critics/config.py:23` `config_dir()`.
- Subprocess wrapper mirroring `src/critics/tools.py:20` `_run`, but without `capture_output` / `text` / `timeout` so the opencode TUI inherits stdin/stdout/stderr.
- `cli_version` mirrors `show_job`/`score_job` — same `_run` seam, returns stdout stripped.
- Pydantic model consumption mirroring how `src/critics/report.py:10` `write_report` iterates `CritiqueReport.findings`.

**Surface (directional, not specification):**
- `sibling_cli_dir() -> Path` (agent.py) — resolve per KTD-4; raise a clear error if the path is not an existing directory.
- `build_handoff_prompt(report: CritiqueReport, history: list) -> str` (agent.py) — assemble job context + each inconsistent finding (field, stored_value, evidence_quote, suggested_fix) + the rebuild instruction naming `just build` (R6) + prior-round history block when `history` is non-empty (R8). Omit the history block entirely when empty.
- `launch_agent_session(repo_path: Path, prompt: str) -> int` (agent.py) — `subprocess.run(["opencode", str(repo_path), "--prompt", prompt])`, returning the exit code. No capture.
- `cli_version() -> str` (tools.py) — run `linkedin-jobs version`, return stdout stripped. Used by the loop's version-before/after check (R15).

**Test scenarios** (`tests/test_agent.py`, `monkeypatch` on `subprocess.run` and env):
- `sibling_cli_dir` honors `LJ_CLI_DIR` override.
- `sibling_cli_dir` defaults to `../linkedin-job-cli` when env unset.
- `sibling_cli_dir` raises when the resolved path does not exist.
- `build_handoff_prompt` includes each defect's field, stored_value, evidence_quote, and suggested_fix.
- `build_handoff_prompt` always includes the rebuild instruction naming `just build`.
- `build_handoff_prompt` includes a history block when history is non-empty; omits it when empty.
- `launch_agent_session` invokes `subprocess.run` with `["opencode", <path>, "--prompt", <prompt>]` and no `capture_output` in kwargs.

**Test scenarios** (`tests/test_tools.py`, `monkeypatch` on `tools._run`):
- `cli_version` returns the version subcommand's stdout verbatim (stripped).
- `cli_version` invokes `_run` with `["version"]`.

**Covers:** R4, R5, R6, R7, R8 (prompt/history portions), R15 (version probe).

### U2. `src/critics/cli.py` — judge→fix→re-judge loop

**Goal:** Wire the human-gated loop into `main()`, reusing the existing judge/report/score primitives and the new U1 handoff helpers.

**Files:**
- `src/critics/cli.py` (modify — restructure `main` per KTD-5)
- `tests/test_cli.py` (new — no cli tests exist today)

**Patterns:**
- Reuse `judge_job` (`src/critics/judge.py:100`), `write_report` (`src/critics/report.py:10`), `score_job` (`src/critics/tools.py:51`), and the new `cli_version` (U1) unchanged.
- New `input()` call for the yes/no gate; default no (R1).

**Behavior:**
- First pass unchanged through `write_report`.
- After `write_report`: count inconsistent findings; if zero, exit 0 without prompting (R2, AE5).
- Prompt `Proceed to spawn opencode agent? [y/N]`. On no, exit (R1, R14, F4).
- On yes: record `version_before = cli_version()`; append current defects to the in-memory history; call `launch_agent_session(sibling_cli_dir(), build_handoff_prompt(report, history))` (R4, R5). The session blocks until the user exits opencode.
- After the session returns: record `version_after = cli_version()`. If `version_after == version_before or version_after == "dev"` (R15, AE4), print that the binary was not rebuilt via `just build` and stop the loop without re-scoring.
- Otherwise: call `score_job(job_id)` to re-score against the rebuilt binary (R9), then `judge_job` again for a full re-judge (R9, R12).
- If the new report has zero inconsistent findings: print success, exit 0 (R10, F2, AE1).
- Else: call `write_report` again with the new report (R11, F3), and loop back to the prompt with history carried (R3, R8).
- Never invoke git, stage, or push (R13).

**Test scenarios** (`tests/test_cli.py`, `monkeypatch` on `judge_job`, `write_report`, `score_job`, `cli_version`, `launch_agent_session`, and builtin `input`):
- No defects in first report → no `input` call, exits 0 (R2, AE5).
- User types `n`/empty → `launch_agent_session` not called, exits (R1, R14, F4).
- User types `y` → `launch_agent_session` called once; `cli_version` called before and after (R15).
- Version unchanged after session → loop stops, `score_job` not called, clear message printed (R15, AE4).
- Version is `dev` after session → same fail-stop (R15, AE4).
- Version bumped after session → `score_job` and `judge_job` each called a second time (R9, F1).
- Second judge returns zero defects → success message printed, exits (R10, F2, AE1).
- Second judge returns defects, user then types `n` → `write_report` called twice total, `launch_agent_session` called once, exits (R11, F3, AE2).
- On round 2 the `build_handoff_prompt` call receives non-empty history (R8) — verify via the launch mock capturing the prompt and asserting history content.
- Regression case: second judge flags a field that was clean in round 1 → that field appears in the round-2 report (R12, AE3).

**Covers:** R1, R2, R3, R9, R10, R11, R12, R13, R14, R15.

---

## Verification Contract

| Command | Applies to | Done signal |
|---|---|---|
| `uv run pytest` (or `pytest`) | U1, U2 | All tests green; new scenarios in `tests/test_agent.py` and `tests/test_cli.py` pass alongside existing `tests/test_{tools,config,report,judge}.py`. |

Manual smoke (not automated — requires a TTY and a live LLM): run `uv run critics <known-defective-job-id> -o /tmp/plan.md`, answer `y` at the prompt, confirm an opencode TUI opens in `../linkedin-job-cli` with the defects pre-loaded, apply or simulate a parser fix, rebuild via the agent, exit the session, and observe critics re-score + re-judge. Verify both convergence (clean re-judge ends the loop) and a defective re-judge (fresh plan written, re-prompted).

---

## Definition of Done

- R1–R15 each satisfied by a U1 or U2 scenario (traceability above).
- `uv run pytest` green, including the new `tests/test_agent.py` and `tests/test_cli.py` and the `cli_version` scenarios in `tests/test_tools.py`.
- The `--prompt` flag assumption (KTD-risks) is verified or has a documented fallback before the loop is considered done.
- Version-check path covered: the two fail-stop scenarios (unchanged, `dev`) plus the bumped-version proceed scenario pass.
- Manual smoke pass: one full convergence loop and one defective-then-stop loop, on a real job id; verify the version-check fail-stop fires when the agent skips `just build`.
- No git/commit/push calls introduced anywhere in `src/critics/` (R13).
