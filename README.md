# Local Memory Assistant

A lightweight assistant that runs entirely locally and remembers things about you across conversations.

## What it does

- Chats using local LLMs (via LM Studio or any OpenAI-like endpoint)
- **Stores all memory in your Obsidian vault** (Obsidian is the single source of truth)
- **Hierarchical memory**: core working memory (~500 tokens), context files (flat and nested), timelines (goals), and monthly archive
- **Core memory is loaded at conversation start**; the model can read/update core, context, timelines, and archive
- **Memory consolidation on quit**: when you type `quit`, the model summarizes the conversation and updates core/context/timelines/archive
- **Searches your Obsidian vault** and maintains structured AI Memory notes (create/read/update notes in `AI Memory/`)
- **Adaptive Q&A**: first-time setup or `--refresh-memory` to build/update memory via conversational questions
- **Exploratory mode** (`--explore`): have a free-form conversation, then extract and organize memory into core, context subdirs, and timelines

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
4. Run the assistant:
   - **Normal chat:** `python src/chat.py`
   - **Refresh memory (Q&A):** `python src/chat.py --refresh-memory` — asks contextual questions and merges updates into existing memory; can skip if memory is already current
   - **Reset and start fresh:** `python src/chat.py --reset-memory` — deletes all AI Memory, then runs first-time setup
   - **Exploratory / deep-dive:** `python src/chat.py --explore` (or `--deep-dive`) — conversational interview, then extracts and writes organized memory (core, context subdirs, timelines) before starting chat

## Features

### Hierarchical Memory (core / context / timelines / archive)
- **Core memory** (`AI Memory/core-memory.md`): working memory, ~500 tokens max, always loaded at conversation start. The model can rewrite it to add new facts and compress.
- **Context files** (`AI Memory/context/`):
  - **Flat categories:** `personal.md`, `work.md`, `preferences.md`, `current-focus.md` — loaded on demand via `read_context` / `update_context`.
  - **Hierarchical (nested):** e.g. `context/work/current-role.md`, `context/work/projects.md`, `context/life/finances.md`, `context/interests/…`. Use `read_specific_context(category, subcategory)` and `update_specific_context(category, subcategory, content)` to read/update these. Created by exploratory extraction or by the model during consolidation.
- **Timelines** (`AI Memory/timelines/`): `current-goals.md` and `future-plans.md`. The model can add goals with timelines via the `add_goal` tool (goal description, timeline, and type: current vs future).
- **Archive** (`AI Memory/archive/YYYY-MM/conversations.md`): conversation summaries and older info, appended by month. Not loaded; searchable via vault search if needed.
- **On quit**: the model runs a consolidation step: summarize the conversation, update core (and optionally context/timelines), and optionally archive a short summary or outdated details.

### Memory refresh and exploration
- **First-time setup:** If no memory exists, the assistant runs an adaptive Q&A (LLM-generated or fallback questions) and writes initial core + context files.
- **Refresh (`--refresh-memory`):** Loads existing memory, asks the LLM for 3–5 clarifying questions (or skips if memory is already current), then merges your answers into core and context via the LLM.
- **Exploratory (`--explore`):** Multi-turn free-form conversation; you type `done` when finished. The LLM then extracts a structured memory layout (core, nested context e.g. work/projects, life/finances, timelines) and writes it with `write_organized_memory`. Supports wikilinks and rich context in context files.

### AI Memory Notes
- Creates structured notes in `AI Memory/` folder in your Obsidian vault
- Organizes information by topics, people, projects
- Automatic metadata tracking (created, updated, topics)
- Safe operations confined to AI Memory folder
- Six operations: create, read, update, append, list, delete

### Obsidian Vault Search
- Search vault by query (searches titles and content)
- Filter by tags (supports both `#tag` and frontmatter `tags: [tag]` formats)
- Filter by folder path
- Returns top 10 results sorted by relevance
- Shows preview snippets around matches
- Read-only access to your existing notes

## Current limitations

- Consolidation on quit depends on the model calling the memory tools; if it doesn’t, memory may not be updated.
- AI Memory notes still require the LLM to decide when to create/update (no automatic organization).

## Roadmap

- ✅ Hierarchical memory (core / context / archive)
- ✅ Nested context (e.g. context/work/, context/life/, context/interests/) and timelines (current-goals, future-plans)
- ✅ Consolidation on conversation end (core, context, specific context, goals, archive)
- ✅ Obsidian integration (vault search)
- ✅ Note creation/editing via tools (AI Memory system)
- ✅ Adaptive Q&A for first-time setup and memory refresh (`--refresh-memory`)
- ✅ Exploratory conversation and organized memory extraction (`--explore`)
- ✅ Memory reset and re-onboarding (`--reset-memory`)
- Semantic search using embeddings
- **Future**: cross-reference notes, auto-categorization, memory export/backup

## Tested
Testing with *qwen/qwen3-vl-8b*

I tried *openai/gpt-oss-20b* and it just refused to do anything but call tools.

Will test more models when i get further along, but Qwen is solid!