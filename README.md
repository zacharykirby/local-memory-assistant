# Local Memory Assistant

A lightweight assistant that runs entirely locally and remembers things about you across conversations.

## What it does

- Chats using local LLMs (via LM Studio or any OpenAI-like endpoint)
- **Stores all memory in your Obsidian vault** - facts, notes, and structured information
- **Searches your Obsidian vault** for notes with intelligent filtering
- **Maintains structured AI memory notes** in dedicated `AI Memory/` folder
- Loads previous context automatically when you restart

## Why this exists

Most local LLM setups forget everything when you close them. This one doesn't.

Everything is stored in your Obsidian vault, so you can view, edit, and organize the AI's memory using Obsidian.

## Requirements

- Python 3.8+
- LM Studio running locally with a tool-capable model (tested with Qwen 3)

## Usage

1. Start LM Studio and load a model
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and configure:
   - `LMSTUDIO_URL`: Your LM Studio endpoint (default: `http://localhost:1234`)
   - `OBSIDIAN_PATH`: Path to your Obsidian vault (e.g., `/home/user/Documents/Notes`)
4. `python src/chat.py`

## Features

### Basic Memory Storage
- Stores simple facts in `AI Memory/facts.md` (markdown format)
- Automatically retrieves relevant context for conversations
- Avoids duplicate information
- Facts are stored as bullet points with automatic timestamps

### AI Memory Notes (NEW!)
- Creates structured notes in `AI Memory/` folder in your Obsidian vault
- Organizes information by topics, people, projects
- Automatic metadata tracking (created, updated, topics)
- Safe operations confined to AI Memory folder
- Six operations: create, read, update, append, list, delete
- See [AI_MEMORY_GUIDE.md](AI_MEMORY_GUIDE.md) for detailed usage

### Obsidian Vault Search
- Search vault by query (searches titles and content)
- Filter by tags (supports both `#tag` and frontmatter `tags: [tag]` formats)
- Filter by folder path
- Returns top 10 results sorted by relevance
- Shows preview snippets around matches
- Read-only access to your existing notes

## Current limitations

- Basic facts get loaded into every conversation (fine for <100 facts, will need retrieval later)
- AI Memory notes require manual management by the LLM (no automatic organization yet)

## Roadmap

- ✅ Memory retrieval tool (search instead of dump-all)
- ✅ Obsidian integration (vault search)
- ✅ Note creation/editing via tools (AI Memory system)
- ✅ Memory categories (personal, projects, preferences, etc.)
- Conversation summaries
- Semantic search using embeddings
- Enhanced memory: cross-reference notes, auto-categorization

## Tested
Testing with *qwen/qwen3-vl-8b*

I tried *openai/gpt-oss-20b* and it just refused to do anything but call tools.

Will test more models when i get further along, but Qwen is solid!