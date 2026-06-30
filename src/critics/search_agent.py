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
    "You populate the jobs database. Given the user's keywords and location, "
    "call the linkedin_jobs_search tool exactly once with those values, then "
    "report the count returned. Do not call any other tool."
)


def build_search_agent(llm: ChatOpenAI):
    return create_agent(model=llm, tools=[linkedin_jobs_search], system_prompt=SYSTEM_PROMPT)


def run_search(llm: ChatOpenAI, keywords: str, location: str) -> str:
    agent = build_search_agent(llm)
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"Search '{keywords}' in '{location}'."}]}
    )
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        return getattr(last, "content", str(last))
    return ""
