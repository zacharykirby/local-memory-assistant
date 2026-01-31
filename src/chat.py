# chat.py
import json
import requests
from memory import load_facts, save_fact

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"

SYSTEM_PROMPT = """You are a helpful assistant with memory.

What you know about the user:
{facts}

You can store new facts about the user by calling the store_fact function.
Only store NEW facts that aren't already in your knowledge base.
Store facts as single, atomic statements (one fact per call).
Don't combine multiple facts into one statement."""

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

def call_llm(messages, tools=None):
    """Call LM Studio API"""
    payload = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 500
    }
    
    if tools:
        payload["tools"] = tools
    
    try:
        response = requests.post(LM_STUDIO_URL, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling LLM: {e}")
        return None

def parse_tool_calls(response):
    """Extract tool calls from LLM response"""
    if not response or "choices" not in response:
        return []
    
    message = response["choices"][0]["message"]
    
    # Check if there are tool calls
    if "tool_calls" in message and message["tool_calls"]:
        tool_calls = []
        for tool_call in message["tool_calls"]:
            func_name = tool_call["function"]["name"]
            # Parse arguments (they come as JSON string)
            args = json.loads(tool_call["function"]["arguments"])
            tool_calls.append((func_name, args))
        return tool_calls
    
    return []

def main():
    print("Local Memory Assistant - Type 'quit' to exit\n")
    
    # Load existing facts
    facts = load_facts()
    
    # Build system message with facts
    facts_text = "\n".join(f"- {fact}" for fact in facts) if facts else "None yet"
    system_msg = SYSTEM_PROMPT.format(facts=facts_text)
    
    messages = [{"role": "system", "content": system_msg}]
    
    while True:
        user_input = input("\nYou: ").strip()
        
        if user_input.lower() in ['quit', 'exit']:
            print("Goodbye!")
            break
        
        if not user_input:
            continue
        
        messages.append({"role": "user", "content": user_input})
        
        # Call LLM with tool available
        response = call_llm(messages, tools=[STORE_FACT_TOOL])
        
        if not response:
            print("Failed to get response from LLM")
            continue
        
        # Handle tool calls first
        tool_calls = parse_tool_calls(response)
        for func_name, args in tool_calls:
            if func_name == "store_fact":
                fact = args.get("fact")
                if fact:
                    if save_fact(fact):
                        print(f"\n[📝 Stored: {fact}]")
                    else:
                        print(f"\n[Already know: {fact}]")
        
        # Get and display assistant response
        message = response["choices"][0]["message"]
        assistant_text = message.get("content", "")
        
        if assistant_text:
            print(f"\nAssistant: {assistant_text}")
            messages.append({"role": "assistant", "content": assistant_text})

if __name__ == "__main__":
    main()