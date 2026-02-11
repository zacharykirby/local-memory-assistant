# chat.py
"""Local Memory Assistant - Main entry point."""
import argparse
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from memory import (
    read_core_memory,
    ensure_memory_structure,
    memory_exists,
    delete_ai_memory_folder,
)
from prompts import SYSTEM_PROMPT
from tools import CHAT_TOOLS, parse_tool_arguments, execute_tool
from consolidation import run_consolidation
from onboarding import (
    run_memory_initialization,
    run_exploratory_conversation,
    extract_memory_from_conversation,
    write_organized_memory,
)
import os
from dotenv import load_dotenv

from rich.prompt import Prompt
from rich.text import Text

from ui import console, display_welcome, get_user_input
from llm import run_agent_loop, truncate_messages, MAX_MESSAGES_IN_CONTEXT

load_dotenv()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Local Memory Assistant")
    parser.add_argument(
        "--refresh-memory",
        action="store_true",
        help="Run adaptive Q&A to refresh existing memory",
    )
    parser.add_argument(
        "--reset-memory",
        action="store_true",
        help="Delete all memory and start fresh",
    )
    parser.add_argument(
        "--explore",
        action="store_true",
        help="Run exploratory conversation to build organized memory",
    )
    parser.add_argument(
        "--deep-dive",
        action="store_true",
        dest="explore",
        help="Alias for --explore",
    )
    return parser.parse_args()


def _confirm_reset() -> bool:
    """Ask user to confirm memory reset. Returns True if confirmed."""
    try:
        confirm = Prompt.ask("Delete existing memory and start fresh?", choices=["yes", "no"], default="no")
        return confirm.lower() == "yes"
    except (EOFError, KeyboardInterrupt):
        return False


def _build_system_content(core_section: str) -> str:
    """Build system message content with current core memory."""
    if core_section:
        return SYSTEM_PROMPT + "\n\n## Core memory (current)\n\n" + core_section
    return SYSTEM_PROMPT + "\n\n## Core memory (current)\n\n(Empty. Use update_core_memory when you learn something about the user.)"


def _refresh_system_message(messages: list) -> str:
    """Re-read core memory from disk and update the system message in place. Returns the new core section."""
    core_section = read_core_memory()
    messages[0] = {"role": "system", "content": _build_system_content(core_section)}
    return core_section


def _run_agent_loop(initial_messages, tools, max_messages_in_context=MAX_MESSAGES_IN_CONTEXT, **kwargs):
    """Wrapper that passes truncate_messages to run_agent_loop."""
    return run_agent_loop(
        initial_messages,
        tools,
        truncate_fn=truncate_messages,
        max_messages_in_context=max_messages_in_context,
        **kwargs,
    )


def main():
    args = parse_args()

    if args.reset_memory:
        if not _confirm_reset():
            console.print("Cancelled.")
            return
        result = delete_ai_memory_folder()
        if not result.get("success"):
            console.print(f"[bold #FF10F0]Error: {result.get('error', 'Unknown')}[/bold #FF10F0]")
            return
        run_memory_initialization()
        return

    if args.refresh_memory:
        run_memory_initialization()
        return

    if args.explore:
        conversation = run_exploratory_conversation()
        if not conversation:
            console.print("No conversation to process.")
            return
        console.print("\n╭─ PROCESSING CONVERSATION ─" + "─" * 40 + "╮")
        console.print("│ Extracting insights and organizing memory...             │")
        console.print("╰─" + "─" * 68 + "╯\n")
        memory_structure = extract_memory_from_conversation(conversation)
        if memory_structure:
            init_result = ensure_memory_structure()
            if init_result.get("success") and write_organized_memory(memory_structure):
                console.print("Your memory is ready! Let's chat.\n", style="green")
            else:
                console.print("[bold #FF10F0]Memory extraction failed or could not write.[/bold #FF10F0]")
        else:
            console.print("[bold #FF10F0]Could not extract memory from conversation. Try again or use --refresh-memory.[/bold #FF10F0]")
            return

    if not memory_exists():
        run_memory_initialization()

    display_welcome()

    init_result = ensure_memory_structure()
    if not init_result.get("success"):
        console.print(f"[bold #FF10F0]Memory init warning: {init_result.get('error', 'Unknown')}[/bold #FF10F0]")

    core_section = read_core_memory()
    messages = [{"role": "system", "content": _build_system_content(core_section)}]

    while True:
        user_input = get_user_input()

        if user_input.lower() in ['quit', 'exit']:
            console.print()
            run_consolidation(messages)
            goodbye = Text("Goodbye!", style="bold #FF10F0")
            console.print(goodbye)
            break

        if not user_input:
            continue

        # On the first turn, put core memory in the user message too so it stays in context
        # even if the backend merges/replaces the system prompt when tools are present.
        if len(messages) == 1:
            core_block = (
                "## Core memory (current)\n\n" + core_section + "\n\n---\n\nUser request: "
                if core_section
                else "User request: "
            )
            user_content = core_block + user_input
        else:
            user_content = user_input
        messages.append({"role": "user", "content": user_content})

        result = _run_agent_loop(
            messages,
            CHAT_TOOLS,
            max_iterations=10,
            stream_first_response=True,
            show_tool_calls=True,
        )
        messages = result["messages"]

        # Refresh system message so core memory stays current after tool updates
        core_section = _refresh_system_message(messages)


if __name__ == "__main__":
    main()
