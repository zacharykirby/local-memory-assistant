# chat.py
import json
import requests
from memory import save_fact, retrieve_facts
import os
from dotenv import load_dotenv

load_dotenv()
URL = os.getenv("LMSTUDIO_URL", "http://localhost:1234")

LM_STUDIO_URL = f"{URL}/v1/chat/completions"

SYSTEM_PROMPT = """You're a helpful assistant with persistent memory across conversations.

You have access to two tools:
- retrieve_facts: Search your memory for information about the user. Use with no query (or empty string) to get ALL facts.
- store_fact: Save new information about the user for future conversations. Store facts as single, atomic statements (one fact per call).

When to use retrieve_facts:
- ALWAYS use it when the user asks what you know/remember about them
- Use it when personal context would improve your answer
- Use it before storing facts to check for similar information and avoid duplicates
- Don't use it for simple greetings or general questions unrelated to the user

When to use store_fact:
- Only store NEW information that isn't already in memory
- Store facts as single statements - one fact per call
- Retrieve first if you're unsure whether you already know something

Keep responses natural:
- Don't announce when you're checking memory or explain the memory system
- Don't be overly eager or use excessive formatting
- Just answer naturally using the information you find

Tone guidelines:
- Keep responses concise and natural
- Don't use emojis in conversational responses 
- Don't make assumptions or offer unsolicited advice
- Avoid corporate-assistant phrases like "How can I assist you today?"
- Just respond naturally to what the user actually asks"""

STORE_FACT_TOOL = {
    "type": "function",
    "function": {
        "name": "store_fact",
        "description": "Store a new fact about the user for future conversations",
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact to remember about the user"
                }
            },
            "required": ["fact"]
        }
    }
}

RETRIEVE_FACTS_TOOL = {
    "type": "function",
    "function": {
        "name": "retrieve_facts",
        "description": "Retrieve facts about the user from memory. Can optionally filter by a search query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional search query to filter facts (e.g., 'hobbies', 'job', 'family')"
                }
            },
            "required": []
        }
    }
}

def call_llm(messages, tools=None, stream=False):
    """Call LM Studio API, optionally with streaming"""
    payload = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 500,
        "stream": stream
    }

    if tools:
        payload["tools"] = tools

    try:
        if not stream:
            response = requests.post(LM_STUDIO_URL, json=payload)
            response.raise_for_status()
            return response.json()

        # Streaming mode
        response = requests.post(LM_STUDIO_URL, json=payload, stream=True)
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

            # Stream content tokens to stdout
            content = delta.get("content")
            if content:
                print(content, end='', flush=True)
                full_content += content

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
        print(f"Error calling LLM: {e}")
        return None

def execute_tool(func_name, args):
    """Execute a tool call and return the result"""
    if func_name == "store_fact":
        fact = args.get("fact")
        if fact:
            if save_fact(fact):
                return f"Successfully stored: {fact}"
            else:
                return f"Already knew: {fact}"
        return "Error: No fact provided"

    elif func_name == "retrieve_facts":
        query = args.get("query")
        facts = retrieve_facts(query)
        if facts:
            facts_list = "\n".join(f"- {fact}" for fact in facts)
            if query and query.strip():
                return f"Found {len(facts)} fact(s) matching '{query}':\n{facts_list}"
            else:
                return f"Found {len(facts)} fact(s) total:\n{facts_list}"
        else:
            if query and query.strip():
                return f"No facts found matching '{query}'"
            else:
                return "No facts stored yet"

    return f"Unknown tool: {func_name}"

def main():
    print("Local Memory Assistant - Type 'quit' to exit\n")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    tools = [STORE_FACT_TOOL, RETRIEVE_FACTS_TOOL]

    while True:
        user_input = input("\nYou: ").strip()

        if user_input.lower() in ['quit', 'exit']:
            print("Goodbye!")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        # Agentic loop - continue until model stops calling tools
        iteration = 0
        while True:
            iteration += 1

            # Only stream on the first iteration (to show thinking in real-time)
            # For tool iterations, use non-streaming to avoid confusion
            use_streaming = (iteration == 1)

            if iteration == 1:
                print("\nAssistant: ", end='', flush=True)

            response = call_llm(messages, tools=tools, stream=use_streaming)

            if not response:
                print("\nFailed to get response from LLM")
                break

            message = response["choices"][0]["message"]
            tool_calls_raw = message.get("tool_calls")

            # If there are tool calls, execute them and loop
            if tool_calls_raw:
                # Add newline if this is first iteration (after streaming)
                if iteration == 1 and message.get("content"):
                    print()

                # Add assistant message with tool calls to history
                messages.append({
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls_raw
                })

                # Execute each tool and add results to history
                for i, tool_call in enumerate(tool_calls_raw):
                    func_name = tool_call["function"]["name"]
                    args_raw = tool_call["function"]["arguments"]
                    tool_call_id = tool_call.get("id", f"call_{i}")

                    # Parse arguments
                    try:
                        args = json.loads(args_raw)
                    except json.JSONDecodeError:
                        args = {}

                    # Log tool call
                    if args:
                        args_display = ", ".join(f"{k}=\"{v}\"" for k, v in args.items() if v)
                        if args_display:
                            print(f"\n[🔧 Tool Call] {func_name}({args_display})")
                        else:
                            print(f"\n[🔧 Tool Call] {func_name}()")
                    else:
                        print(f"\n[🔧 Tool Call] {func_name}()")

                    # Execute tool
                    result = execute_tool(func_name, args)

                    # Log result
                    result_preview = result[:100] + "..." if len(result) > 100 else result
                    print(f"[📋 Tool Result] {result_preview}")

                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": func_name,
                        "content": result
                    })

                # Model will think again with the tool results
                print("\n[🤔 Thinking...]")

            else:
                # No tool calls - this is the final response
                if iteration > 1:
                    # Stream the final response
                    print("\n[💬 Response] ", end='', flush=True)
                    response = call_llm(messages, tools=tools, stream=True)
                    if response:
                        message = response["choices"][0]["message"]
                    print()
                else:
                    # Already streamed in iteration 1
                    print()

                # Add final assistant response to message history
                assistant_text = message.get("content", "")
                if assistant_text:
                    messages.append({"role": "assistant", "content": assistant_text})

                break  # Exit agentic loop

if __name__ == "__main__":
    main()