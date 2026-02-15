"""
Memory consolidation on conversation end.

Handles reviewing conversation history and updating memory intelligently
using an agentic loop, followed by automatic observation consolidation.
"""

from rich.text import Text

from ui import console
from llm import run_agent_loop, call_llm, truncate_messages, CONSOLIDATION_MAX_MESSAGES
from prompts import CONSOLIDATION_SYSTEM_PROMPT, build_consolidation_user_message
from tools import CONSOLIDATION_TOOLS
from memory import (
    read_core_memory,
    check_observations_need_consolidation,
    prepare_observations_for_consolidation,
    write_consolidated_observations,
)

OBSERVATION_SUMMARIZATION_PROMPT = (
    "You are Memoria, summarizing your own observations about a user. "
    "Condense the following observation entries into 3-5 distilled patterns. "
    "Be concise. Preserve anything that still feels unresolved or contradictory. "
    "Write in first person. Output only the summary text — no headers, timestamps, "
    "or formatting markers."
)


def _consolidate_observations() -> None:
    """Check and consolidate observations if over threshold.

    Called after the main consolidation agentic loop.
    Archives the full pre-compression content, then replaces old entries
    with an LLM-generated summary while keeping recent entries intact.
    """
    if not check_observations_need_consolidation():
        return

    prep = prepare_observations_for_consolidation()
    if not prep:
        return

    console.print(Text("  consolidating observations...", style="dim"))

    context = ""
    if prep['current_summary']:
        context = f"Previous summary to incorporate:\n{prep['current_summary']}\n\n"

    messages = [
        {"role": "system", "content": OBSERVATION_SUMMARIZATION_PROMPT},
        {"role": "user", "content": f"{context}Observations to summarize:\n\n{prep['old_entries_text']}"},
    ]

    response = call_llm(messages, tools=None, stream=False, max_tokens=500)
    if not response:
        console.print(Text("  observation consolidation failed (LLM error)", style="dim #FF10F0"))
        return

    summary = (
        response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "") or ""
    ).strip()
    if not summary:
        console.print(Text("  observation consolidation failed (empty summary)", style="dim #FF10F0"))
        return

    result = write_consolidated_observations(
        summary, prep['recent_entries'], prep['full_content']
    )
    if result.get("success"):
        kept = result.get('entries_kept', 0)
        console.print(Text(f"  ◆ observations consolidated ({kept} entries kept)", style="dim #555555"))
    else:
        console.print(
            Text(f"  observation consolidation error: {result.get('error', 'unknown')}", style="dim #FF10F0")
        )


def run_consolidation(messages: list) -> None:
    """Run memory consolidation using an agentic loop: LLM can read memory, then update based on results."""
    console.print(Text("  consolidating...", style="dim"))

    core_content = read_core_memory()
    user_consolidation_msg = build_consolidation_user_message(messages, core_content)

    consolidation_messages = [
        {"role": "system", "content": CONSOLIDATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_consolidation_msg},
    ]

    result = run_agent_loop(
        consolidation_messages,
        CONSOLIDATION_TOOLS,
        truncate_fn=truncate_messages,
        max_messages_in_context=CONSOLIDATION_MAX_MESSAGES,
        max_iterations=25,
        stream_first_response=False,
        show_tool_calls=True,
    )

    if result["iterations"] >= 25:
        console.print(Text("  consolidation hit max iterations", style="dim #FF10F0"))
    if not result["final_response"]:
        console.print(
            Text(
                "  consolidation ended without final summary — memory files may be partially updated",
                style="dim #FF10F0",
            )
        )

    # Consolidate observations after the main agentic loop
    _consolidate_observations()

    console.print(Text("  ◆ memory consolidated", style="dim #555555"))
    console.print()
