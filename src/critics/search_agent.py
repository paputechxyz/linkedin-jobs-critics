"""Search agent — a langchain create_agent with one CLI tool.

Built on LangGraph internally but used as plain langchain (no graph API). The
agent's only job is to formulate the CLI call from the user's keywords/location
and invoke the search tool once.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from .tools import linkedin_jobs_search

SYSTEM_PROMPT = (
    "You populate the jobs database. Given the user's keywords, location, and "
    "any optional extra_search_args, call the linkedin_jobs_search tool exactly "
    "once with those values, then report the count returned. Do not call any "
    "other tool. Pass extra_search_args through verbatim; never invent flags."
)


def build_search_agent(llm: ChatOpenAI):
    return create_agent(model=llm, tools=[linkedin_jobs_search], system_prompt=SYSTEM_PROMPT)


def run_search(
    llm: ChatOpenAI,
    keywords: str,
    location: str,
    extra_search_args: list[str] | None = None,
) -> str:
    agent = build_search_agent(llm)
    content = f"Search '{keywords}' in '{location}'."
    if extra_search_args:
        flags = " ".join(extra_search_args)
        content += f" Also pass these extra flags to the tool verbatim: {flags}"
    result = agent.invoke({"messages": [{"role": "user", "content": content}]})
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        return getattr(last, "content", str(last))
    return ""
