# Local Memory Assistant

A lightweight assistant that runs entirely locally and remembers things about you across conversations.

## What it does

- Chats using local LLMs (via LM Studio or any OpenAI-like endpoint)
- Stores facts about you that persist between sessions
- Loads previous context automatically when you restart

## Why this exists

Most local LLM setups forget everything when you close them. This one doesn't.

Currently stores everything in a simple JSON file. Future versions will integrate with Obsidian (markdown!) and support smarter memory retrieval.

## Requirements

- Python 3.8+
- LM Studio running locally with a tool-capable model (tested with Qwen 3)

## Usage

1. Start LM Studio and load a model
2. `pip install -r requirements.txt`
3. `python src/chat.py`

## Current limitations

- All facts get loaded into every conversation (fine for <100 facts, will need retrieval later)
- No categorization or organization yet
- Memory is append-only (no editing/deleting)

## Roadmap

- Memory retrieval tool (search instead of dump-all)
- Obsidian integration
- Memory categories (personal, projects, preferences, etc.)
- Conversation summaries

## Tested
Testing with *qwen/qwen3-vl-8b*

I tried *openai/gpt-oss-20b* and it just refused to do anything but call tools.

Will test more models when i get further along, but Qwen is solid!