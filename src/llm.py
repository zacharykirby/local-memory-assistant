"""
LLM client for interacting with local models via LM Studio.

Handles API calls, streaming, JSON extraction, and error handling.
"""

import json
import os
import re
import requests
from typing import Optional

from dotenv import load_dotenv
from rich.markdown import Markdown

load_dotenv()

URL = os.getenv("LMSTUDIO_URL", "http://localhost:1234")
LM_STUDIO_URL = f"{URL}/v1/chat/completions"

MAX_MESSAGES_IN_CONTEXT = 50
CONSOLIDATION_MAX_MESSAGES = 60
SYSTEM_MESSAGE_ROLES = {"system"}

# Request timeout: (connect_timeout, read_timeout) in seconds
REQUEST_TIMEOUT = (5, 120)


def truncate_messages(messages: list, max_messages: int = MAX_MESSAGES_IN_CONTEXT) -> list:
    """Truncate conversation to most recent messages while preserving system messages.

    Truncates at turn boundaries so that assistant messages with tool_calls are
    never separated from their corresponding tool result messages.
    """
    if not messages:
        return messages
    from ui import console
    system_msgs = [m for m in messages if m.get("role") in SYSTEM_MESSAGE_ROLES]
    conversation_msgs = [m for m in messages if m.get("role") not in SYSTEM_MESSAGE_ROLES]
    if len(conversation_msgs) <= max_messages:
        return messages

    # Find safe cut points: indices where a new turn starts.
    # A turn starts at each "user" message, or at an "assistant" message that
    # is NOT immediately preceded by a tool result (i.e., it's a final response
    # rather than a continuation after tool calls).
    # We never cut between an assistant tool_calls message and its tool results.
    cut_points = []
    for i, msg in enumerate(conversation_msgs):
        role = msg.get("role", "")
        if role == "user":
            cut_points.append(i)
        elif role == "assistant" and i > 0 and conversation_msgs[i - 1].get("role") != "tool":
            cut_points.append(i)

    # Find the earliest cut point that keeps <= max_messages from the end
    best_cut = len(conversation_msgs) - max_messages
    chosen_cut = 0
    for cp in cut_points:
        if cp >= best_cut:
            chosen_cut = cp
            break
    else:
        # All cut points are before best_cut; use the last one to keep as much as possible
        chosen_cut = cut_points[-1] if cut_points else best_cut

    kept_conversation = conversation_msgs[chosen_cut:]
    dropped_count = len(conversation_msgs) - len(kept_conversation)
    if dropped_count > 0:
        console.print(f"[dim]Truncated {dropped_count} old messages to stay within context limit[/dim]")
    return system_msgs + kept_conversation


def call_llm(messages, tools=None, stream=False, live_display=None, max_tokens=500):
    """Call LM Studio API, optionally with streaming."""
    # When tools are provided, allow enough tokens for tool calls (e.g. update_core_memory
    # can send ~500 tokens of content in one call). Default 500 would truncate and break parsing.
    effective_max_tokens = max_tokens
    if tools and max_tokens == 500:
        effective_max_tokens = 4096

    payload = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": effective_max_tokens,
        "stream": stream
    }

    if tools:
        payload["tools"] = tools
        # Do not set tool_choice: "auto" — some backends then omit or alter the system
        # message (e.g. replace with tool-only prompt), which drops core memory from context.

    try:
        if not stream:
            response = requests.post(LM_STUDIO_URL, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()

        # Streaming mode
        response = requests.post(LM_STUDIO_URL, json=payload, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        full_content = ""
        tool_calls_accumulated = []

        for line in response.iter_lines():
            if not line:
                continue

            line_text = line.decode('utf-8')
            if not line_text.startswith("data: "):
                continue

            data = line_text[6:]  # Remove "data: " prefix

            if data == "[DONE]":
                break

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            delta = chunk["choices"][0].get("delta", {})

            # Stream content tokens
            content = delta.get("content")
            if content:
                full_content += content
                if live_display:
                    live_display.update(Markdown(full_content))

            # Accumulate tool calls (they come in pieces)
            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    idx = tc.get("index", 0)
                    while len(tool_calls_accumulated) <= idx:
                        tool_calls_accumulated.append({
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""}
                        })
                    if "id" in tc:
                        tool_calls_accumulated[idx]["id"] = tc["id"]
                    if "function" in tc:
                        func = tc["function"]
                        if "name" in func:
                            tool_calls_accumulated[idx]["function"]["name"] += func["name"]
                        if "arguments" in func:
                            tool_calls_accumulated[idx]["function"]["arguments"] += func["arguments"]

        # Return in format compatible with existing code
        message = {"content": full_content if full_content else None}
        if tool_calls_accumulated:
            message["tool_calls"] = tool_calls_accumulated

        return {"choices": [{"message": message}]}

    except requests.exceptions.RequestException as e:
        from ui import console
        console.print(f"[bold magenta]Error calling LLM:[/bold magenta] {e}")
        return None


def extract_json_from_response(content: str) -> Optional[dict]:
    """Try to extract a JSON object from LLM response (handle markdown code blocks and truncation)."""
    content = (content or "").strip()
    if not content:
        return None

    def try_parse(s: str) -> Optional[dict]:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    # Strip markdown code fence (optional language tag)
    for pattern in (r"^```(?:json)?\s*\n?", r"\n?```\s*$"):
        content = re.sub(pattern, "", content)
    content = content.strip()

    parsed = try_parse(content)
    if parsed:
        return parsed

    # Try to find ```json ... ``` or ``` ... ``` block (non-greedy to first closing)
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        parsed = try_parse(match.group(1).strip())
        if parsed:
            return parsed

    # Try first { ... } (may be truncated)
    match = re.search(r"\{[\s\S]*", content)
    if match:
        candidate = match.group(0)
        parsed = try_parse(candidate)
        if parsed:
            return parsed
        # Repair truncated JSON: close open strings and brackets
        repaired = _repair_truncated_json(candidate)
        if repaired:
            parsed = try_parse(repaired)
            if parsed:
                return parsed

    return None


def _repair_truncated_json(s: str) -> Optional[str]:
    """Attempt to close truncated JSON by balancing brackets (and close open string if needed)."""
    if not s or not s.strip().startswith("{"):
        return None
    in_double = False
    escape = False
    stack = []
    i = 0
    while i < len(s):
        c = s[i]
        if escape:
            escape = False
            i += 1
            continue
        if in_double:
            if c == "\\":
                escape = True
            elif c == '"':
                in_double = False
            i += 1
            continue
        if c == '"':
            in_double = True
            i += 1
            continue
        if c == "{":
            stack.append("}")
            i += 1
            continue
        if c == "[":
            stack.append("]")
            i += 1
            continue
        if c in "}]" and stack and stack[-1] == c:
            stack.pop()
        i += 1
    suffix = ""
    if in_double:
        suffix += '"'
    suffix += "".join(reversed(stack))
    return s + suffix if suffix else None


def run_agent_loop(
    initial_messages: list,
    tools: list,
    max_iterations: int = 10,
    stream_first_response: bool = True,
    show_tool_calls: bool = True,
    max_messages_in_context: int = 50,
    truncate_fn=None,
):
    """
    Run the agentic loop: LLM → tools → LLM → tools → ... → final response.
    Tool results are fed back to the LLM so it can read-then-write and multi-step.
    """
    from ui import console, display_tool_call, display_tool_result, display_thinking
    from tools import parse_tool_arguments, execute_tool

    messages = list(initial_messages)
    iteration = 0
    done = False
    message = {}

    while not done and iteration < max_iterations:
        iteration += 1

        if truncate_fn:
            messages = truncate_fn(messages, max_messages=max_messages_in_context)

        should_stream = stream_first_response and (iteration == 1)

        if should_stream:
            from rich.live import Live
            from rich.markdown import Markdown
            console.print()
            with Live(Markdown(""), console=console, refresh_per_second=15, transient=False) as live:
                response = call_llm(messages, tools=tools, stream=True, live_display=live)
        else:
            response = call_llm(messages, tools=tools, stream=False)

        if not response:
            console.print("[bold #FF10F0]Failed to get response from LLM[/bold #FF10F0]")
            break

        message = response["choices"][0]["message"]
        tool_calls_raw = message.get("tool_calls") or []
        assistant_msg = {"role": "assistant", "content": message.get("content")}
        if tool_calls_raw:
            assistant_msg["tool_calls"] = tool_calls_raw
        messages.append(assistant_msg)

        if tool_calls_raw:
            for i, tool_call in enumerate(tool_calls_raw):
                func_name = tool_call["function"]["name"]
                args = parse_tool_arguments(tool_call)
                tool_call_id = tool_call.get("id", f"call_{i}")

                if show_tool_calls:
                    console.print()
                    display_tool_call(func_name, args)

                result = execute_tool(func_name, args)
                result_str = result if isinstance(result, str) else str(result)

                if show_tool_calls:
                    display_tool_result(result_str)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": func_name,
                    "content": result_str,
                })

            if show_tool_calls:
                console.print()
                display_thinking()
            continue
        else:
            done = True
            content = message.get("content", "") or ""

            if iteration > 1 and content and not should_stream:
                console.print()
                console.print(content)

            if messages and messages[-1].get("role") == "assistant":
                messages[-1] = {"role": "assistant", "content": content}

    return {
        "messages": messages,
        "final_response": message.get("content", "") if message else "",
        "iterations": iteration,
    }
