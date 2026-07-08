"""LangGraph implementation of the judge→fix→re-judge loop.

The graph orchestrates the same control flow the hand-rolled while-loop in
`cli.py` used to: load job → judge (with header-tag merge) → user-gated agent
round → re-score → re-judge → loop until clean or the user stops.

Each node is a thin function that reads what it needs from `LoopState` and
returns a partial-update dict. Helpers that already lived on `cli.py`
(`_judge_and_write`, `_check_header_tag`, `_print_plan`, `_inconsistent`) are
re-implemented here so tests can monkeypatch the underlying primitives
(`judge_job`, `header_tags`, `header_tag_finding`, `write_report`, ...) on
this module directly.

The user gate is a langgraph `interrupt()`: when the graph pauses, `cli.main`
asks `[y/N]`, then resumes with `Command(resume=<bool>)`. The interrupt value
carries the round number so the caller can print context if it ever needs to.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .agent import (
    build_handoff_prompt,
    launch_agent_session,
    latest_session_id,
    sibling_cli_dir,
)
from .judge import CritiqueReport, header_tag_finding, judge_job
from .report import write_report
from .tools import cli_version, header_tags, score_job, show_job

# LangGraph 1.x msgpack-serializes checkpoint state and warns when state holds
# types outside its built-in safe allowlist. We pull the LLM out of state (it
# flows via RunnableConfig instead — it's a resource, not loop data), so the
# only custom type left in state is CritiqueReport. Whitelist it explicitly to
# silence the "Deserializing unregistered type" warning and to be ready for
# the announced future strict mode.
_SERDE = JsonPlusSerializer(
    allowed_msgpack_modules=[("critics.judge", "CritiqueReport")]
)


class LoopState(TypedDict, total=False):
    job_id: str
    out_path: str
    job: dict
    report: CritiqueReport
    round_num: int
    session_id: str | None
    repo_path: str
    prompt: str
    version_before: str
    version_after: str
    rc: int


def _llm_from_config(config: RunnableConfig) -> Any:
    return config["configurable"]["llm"]


def _inconsistent(report: CritiqueReport) -> list:
    return [f for f in report.findings if not f.is_consistent]


def _print_plan(out_path: str) -> None:
    try:
        content = pathlib.Path(out_path).read_text()
    except OSError:
        return
    print("\n----- improvement plan -----", file=sys.stderr)
    print(content, file=sys.stderr)
    print("------------------------------\n", file=sys.stderr)


def _check_header_tag(job: dict) -> object | None:
    job_id = job.get("id", "")
    if not job_id:
        return None
    print("Critics: checking header tag via Voyager API...", file=sys.stderr)
    ht = header_tags(job_id)
    if ht is None:
        print(
            "  ! header-tags unavailable (no session or CLI error); skipping.",
            file=sys.stderr,
        )
        return None
    finding = header_tag_finding(job, ht)
    if finding is None and ht.get("source") == "voyager_api":
        print(
            f"  header tag OK: stored remote_type matches LinkedIn's "
            f"'{ht.get('remote_type', '')}'.",
            file=sys.stderr,
        )
    elif finding is not None:
        print(
            f"  ! header-tag mismatch: stored "
            f"'{job.get('remote_type') or '(none)'}' vs LinkedIn "
            f"'{ht.get('remote_type', '')}'.",
            file=sys.stderr,
        )
    return finding


def _judge_and_write(job: dict, llm: Any, out_path: str) -> CritiqueReport | None:
    print(f"Critics: judging job {job.get('id', '?')}...", file=sys.stderr)
    try:
        report = judge_job(job, llm)
    except Exception as e:
        print(f"  ! judge failed: {e}", file=sys.stderr)
        return None
    ht_finding = _check_header_tag(job)
    if ht_finding is not None:
        report.findings.append(ht_finding)
    write_report([report], out_path)
    _print_plan(out_path)
    return report


def load_job(state: LoopState) -> dict:
    job_id = state["job_id"]
    print(f"Critics: looking up job {job_id} in DB...", file=sys.stderr)
    job = show_job(job_id)
    if job is None:
        print(
            f"  not stored; fetching via `linkedin-jobs score-job {job_id}`...",
            file=sys.stderr,
        )
        try:
            job = score_job(job_id)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return {"rc": 1}
    else:
        print("  found in DB.", file=sys.stderr)
    return {"job": job}


def judge(state: LoopState, config: RunnableConfig) -> dict:
    report = _judge_and_write(state["job"], _llm_from_config(config), state["out_path"])
    if report is None:
        return {"rc": 1}
    print(f"Wrote {state['out_path']}", file=sys.stderr)
    if not _inconsistent(report):
        print("No defects found; nothing to fix.", file=sys.stderr)
        return {"report": report, "rc": 0}
    return {"report": report}


def gate(state: LoopState) -> dict:
    """Pause for the user's [y/N] decision.

    `interrupt()` returns the value `cli.main` passes via `Command(resume=...)`.
    On decline, set rc=0 so the conditional edge routes to END.
    """
    round_num = state.get("round_num", 0) + 1
    decision = interrupt({"round_num": round_num})
    if not decision:
        print("Stopping; no agent spawned.", file=sys.stderr)
        return {"rc": 0}
    return {}


def pre_check(state: LoopState) -> dict:
    round_num = state.get("round_num", 0) + 1
    try:
        repo_path = sibling_cli_dir()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return {"rc": 1, "round_num": round_num}

    prompt = build_handoff_prompt(state["report"], round_num=round_num)
    session_id = state.get("session_id")
    print(
        f"\n----- opencode prompt (round {round_num}"
        f"{', resuming session ' + session_id if session_id else ', new session'})"
        f" -----",
        file=sys.stderr,
    )
    print(prompt, file=sys.stderr)
    print("-" * 60 + "\n", file=sys.stderr)
    print(
        f"Critics: launching opencode agent in {repo_path} "
        f"(round {round_num})...",
        file=sys.stderr,
    )
    print(
        "  When the agent is done, EXIT opencode with /exit (or /q, or "
        "Ctrl+x then q) to return to critics, which will re-score + "
        "re-judge. Do NOT Ctrl+C — that kills critics too.",
        file=sys.stderr,
    )
    version_before = cli_version()
    return {
        "round_num": round_num,
        "repo_path": str(repo_path),
        "prompt": prompt,
        "version_before": version_before,
        "session_id": session_id,
    }


def run_agent(state: LoopState) -> dict:
    try:
        launch_agent_session(
            pathlib.Path(state["repo_path"]),
            state["prompt"],
            session_id=state.get("session_id"),
        )
    except KeyboardInterrupt:
        print(
            "\nCritics: agent session interrupted (Ctrl+C). "
            "Stopping without re-score.",
            file=sys.stderr,
        )
        return {"rc": 1}

    session_id = state.get("session_id")
    if session_id is None:
        session_id = latest_session_id(pathlib.Path(state["repo_path"]))
        if session_id is None:
            print(
                "Critics: could not capture opencode session id; the next "
                "round will start a fresh session (no cross-round memory).",
                file=sys.stderr,
            )
    return {"session_id": session_id}


def post_check(state: LoopState) -> dict:
    version_after = cli_version()
    version_before = state["version_before"]
    if version_after == version_before or version_after == "dev":
        print(
            f"Critics: linkedin-jobs version unchanged after agent session "
            f"('{version_before}' -> '{version_after}'). The agent did not "
            f"rebuild via `just build`; skipping re-score. Stopping.",
            file=sys.stderr,
        )
        return {"version_after": version_after, "rc": 1}
    return {"version_after": version_after}


def rescore(state: LoopState, config: RunnableConfig) -> dict:
    print(
        f"Critics: re-scoring + re-judging job {state['job_id']} "
        f"(version {state['version_before']} -> {state.get('version_after', '?')})...",
        file=sys.stderr,
    )
    try:
        job = score_job(state["job_id"])
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return {"rc": 1}

    report = _judge_and_write(job, _llm_from_config(config), state["out_path"])
    if report is None:
        return {"rc": 1}
    if not _inconsistent(report):
        print(
            "Critics: re-judge clean — all defects resolved. Stopping.",
            file=sys.stderr,
        )
        return {"job": job, "report": report, "rc": 0}
    return {"job": job, "report": report}


def _route_by_rc(state: LoopState, default: str) -> str:
    return END if state.get("rc") is not None else default


def build_graph():
    """Compile the judge→fix→re-judge loop with a MemorySaver checkpointer
    (required for `interrupt()`)."""
    g = StateGraph(LoopState)
    g.add_node("load_job", load_job)
    g.add_node("judge", judge)
    g.add_node("gate", gate)
    g.add_node("pre_check", pre_check)
    g.add_node("run_agent", run_agent)
    g.add_node("post_check", post_check)
    g.add_node("rescore", rescore)

    g.add_edge(START, "load_job")
    g.add_conditional_edges("load_job", lambda s: _route_by_rc(s, "judge"))
    g.add_conditional_edges("judge", lambda s: _route_by_rc(s, "gate"))
    g.add_conditional_edges("gate", lambda s: _route_by_rc(s, "pre_check"))
    g.add_conditional_edges("pre_check", lambda s: _route_by_rc(s, "run_agent"))
    g.add_conditional_edges(
        "run_agent", lambda s: _route_by_rc(s, "post_check")
    )
    g.add_conditional_edges("post_check", lambda s: _route_by_rc(s, "rescore"))
    g.add_conditional_edges("rescore", lambda s: _route_by_rc(s, "gate"))
    return g.compile(checkpointer=MemorySaver(serde=_SERDE))
