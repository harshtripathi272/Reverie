"""Reference agent for testing Reverie instrumentation.

Run it via the CLI:

    reverie run python examples/basic_agent.py

Or, if you don't want a real model call, run the synthetic version:

    reverie run python examples/basic_agent.py --synthetic

The synthetic mode drives the SDK's tracing surface directly so no API key
or network call to OpenAI is needed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def run_synthetic() -> int:
    """Drive the OpenAI Agents SDK's tracing surface without any LLM calls.

    Useful for verifying the instrumentation pipeline end-to-end.
    """

    from agents.tracing import agent_span, function_span, trace

    with trace("research-workflow", group_id="example-session") as t:
        with agent_span(name="planner"):
            for q in (
                "AI agent observability tools",
                "OpenTelemetry tracing patterns",
                "LangSmith vs Langfuse comparison",
            ):
                with function_span(name="search_web", input=f'{{"query":"{q}"}}') as fn:
                    fn.span_data.output = f"results for {q}"
            with function_span(name="write_summary", input='{"title":"AI Observability 2025"}') as fn:
                fn.span_data.output = "summary written"

    print(f"\n--- Synthetic run complete ---")
    print(f"trace_id: {t.trace_id}")
    return 0


async def run_real() -> int:
    """Drive a real OpenAI Agents SDK run. Requires OPENAI_API_KEY."""

    from agents import Agent, Runner, function_tool

    @function_tool
    def search_web(query: str) -> str:
        """Search the web for information (simulated)."""
        return f"Search results for {query!r}: 3 relevant articles about {query}."

    @function_tool
    def read_file(filename: str) -> str:
        """Read a file from the filesystem (simulated)."""
        return f"Contents of {filename}: [simulated]"

    @function_tool
    def write_summary(title: str, content: str) -> str:
        """Write a summary document (simulated)."""
        return f"Summary {title!r} written successfully."

    agent = Agent(
        name="research-agent",
        instructions=(
            "You are a research assistant. When given a topic, search for "
            "information, read relevant files, and write a summary. Be "
            "thorough and use multiple tool calls."
        ),
        tools=[search_web, read_file, write_summary],
        model="gpt-4o-mini",
    )

    result = await Runner.run(
        agent,
        "Research the current state of AI agent observability tools and "
        "write a summary.",
    )
    print("\n--- Agent Output ---")
    print(result.final_output)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reverie reference agent")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        default=True,
        help="Drive only the SDK tracing surface — no model calls. Default.",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Run a real OpenAI Agents SDK call (requires OPENAI_API_KEY).",
    )
    args = parser.parse_args()

    if args.real:
        return asyncio.run(run_real())
    return run_synthetic()


if __name__ == "__main__":
    sys.exit(main())
