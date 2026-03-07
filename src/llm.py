"""
LLM client for OpenAI-compatible chat completion APIs.

Supports OpenRouter, LM Studio, and any endpoint that follows the OpenAI chat API.
"""

import json
import os
import re
import time
import requests
from typing import Optional

from dotenv import load_dotenv
from rich.markdown import Markdown

load_dotenv()

# Generic OpenAI-compatible endpoint (default: OpenRouter)
# Fallback: LMSTUDIO_URL for backward compatibility
_base = os.getenv("LLM_API_URL") or os.getenv("LMSTUDIO_URL", "https://openrouter.ai/api/v1")
_base = _base.rstrip("/")
if _base.endswith("chat/completions"):
    CHAT_COMPLETIONS_URL = _base
elif _base.endswith("/v1"):
    CHAT_COMPLETIONS_URL = f"{_base}/chat/completions"
else:
    CHAT_COMPLETIONS_URL = f"{_base}/v1/chat/completions"
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("LMSTUDIO_API_KEY")

MAX_MESSAGES_IN_CONTEXT = 50
CONSOLIDATION_MAX_MESSAGES = 60
SYSTEM_MESSAGE_ROLES = {"system"}

# Request timeout: (connect_timeout, read_timeout) in seconds
REQUEST_TIMEOUT = (5, 120)

# Retry configuration
MAX_RETRIES = 2
RETRY_BASE_DELAY = 2  # seconds, doubles each retry

# Tool result truncation (prevents a single large result from bloating context)
MAX_TOOL_RESULT_CHARS = 6000  # ~1500 tokens


def truncate_messages(messages: list, max_messages: int = MAX_MESSAGES_IN_CONTEXT) -> list:
    """Truncate conversation to most recent messages while preserving system messages.

    Truncates at turn boundaries so that assistant messages with tool_calls are
    never separated from their corresponding tool result messages.
    """
    if not messages:
        return messages
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
    return system_msgs + kept_conversation


def call_llm(messages, tools=None, stream=False, live_display=None, max_tokens=None):
    """Call OpenAI-compatible chat completions API, optionally with streaming."""
    if tools and max_tokens is None:
        effective_max_tokens = 4096
    elif max_tokens is None:
        effective_max_tokens = 500
    else:
        effective_max_tokens = max_tokens

    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": effective_max_tokens,
        "stream": stream
    }

    if tools:
        payload["tools"] = tools
        # Do not set tool_choice: "auto" — some backends then omit or alter the system
        # message (e.g. replace with tool-only prompt), which drops core memory from context.

    headers = {}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    for attempt in range(MAX_RETRIES + 1):
        try:
            if not stream:
                response = requests.post(CHAT_COMPLETIONS_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                return response.json()

            # Streaming mode
            response = requests.post(CHAT_COMPLETIONS_URL, json=payload, headers=headers, stream=True, timeout=REQUEST_TIMEOUT)
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

                if not chunk.get("choices"):
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
                            if "name" in func and func["name"] is not None:
                                tool_calls_accumulated[idx]["function"]["name"] += func["name"]
                            if "arguments" in func and func["arguments"] is not None:
                                tool_calls_accumulated[idx]["function"]["arguments"] += func["arguments"]

            # Return in format compatible with existing code
            message = {"content": full_content if full_content else None}
            if tool_calls_accumulated:
                message["tool_calls"] = tool_calls_accumulated

            return {"choices": [{"message": message}]}

        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                if attempt == 0:
                    from ui import console
                    console.print("[dim]  ·[/dim]")
                time.sleep(delay)
                continue
            from ui import console
            console.print("[dim #FF10F0]  connection failed[/dim #FF10F0]")
            return None

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
    from ui import (
        console, StreamingDisplay, start_spinner,
        TOOL_SPINNER_TEXT, display_tool_done, display_error, display_response,
    )
    from tools import parse_tool_arguments, execute_tool

    messages = list(initial_messages)
    iteration = 0
    done = False
    message = {}

    while not done and iteration < max_iterations:
        iteration += 1

        if truncate_fn:
            messages = truncate_fn(messages, max_messages=max_messages_in_context)

        # Stream every iteration when enabled — not just the first.
        # StreamingDisplay shows ◆ thinking... then transitions to live
        # Markdown when the first token arrives, regardless of iteration.
        should_stream = stream_first_response

        if should_stream:
            display = StreamingDisplay()
            display.start()
            try:
                response = call_llm(messages, tools=tools, stream=True, live_display=display)
            finally:
                display.stop()
        else:
            spinner = start_spinner("thinking...")
            try:
                response = call_llm(messages, tools=tools, stream=False)
            finally:
                spinner.stop()

        if not response:
            display_error("Failed to get response from LLM")
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

                tool_spinner = None
                if show_tool_calls:
                    desc = TOOL_SPINNER_TEXT.get(func_name, "thinking...")
                    tool_spinner = start_spinner(desc)

                result = execute_tool(func_name, args)
                result_str = result if isinstance(result, str) else str(result)

                # Truncate oversized tool results to limit context growth
                if len(result_str) > MAX_TOOL_RESULT_CHARS:
                    result_str = (
                        result_str[:MAX_TOOL_RESULT_CHARS]
                        + f"\n\n[truncated — {len(result_str)} chars total, showing first {MAX_TOOL_RESULT_CHARS}]"
                    )

                if show_tool_calls and tool_spinner:
                    tool_spinner.stop()
                    display_tool_done(func_name, args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": func_name,
                    "content": result_str,
                })

            continue
        else:
            done = True
            content = message.get("content", "") or ""

            # Non-streaming callers (e.g. consolidation) still need explicit display
            if not should_stream and content:
                display_response(content)

            if messages and messages[-1].get("role") == "assistant":
                messages[-1] = {"role": "assistant", "content": content}

    return {
        "messages": messages,
        "final_response": message.get("content", "") if message else "",
        "iterations": iteration,
    }
