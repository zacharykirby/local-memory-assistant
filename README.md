# Memoria

A lightweight assistant that runs entirely locally and remembers things about you across conversations.

## What it does

- Chats using OpenAI-compatible LLMs (OpenRouter, LM Studio, or any compatible endpoint)
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
- An OpenAI-compatible LLM endpoint (OpenRouter by default, or LM Studio with a tool-capable model)

## Usage

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and configure:
   - `LLM_API_URL`: OpenAI-compatible endpoint base (default: `https://openrouter.ai/api/v1`)
   - `LLM_MODEL`: Model name (default: `openai/gpt-oss-120b`)
   - `LLM_API_KEY`: API key (required for OpenRouter; get one at [openrouter.ai](https://openrouter.ai))
   - `OBSIDIAN_PATH`: Path to your Obsidian vault (e.g., `/home/user/Documents/Notes`)
4. Run the assistant:
   - **Normal chat:** `python src/chat.py`
   - **Refresh memory (Q&A):** `python src/chat.py --refresh-memory` — asks contextual questions and merges updates into existing memory; can skip if memory is already current
   - **Reset and start fresh:** `python src/chat.py --reset-memory` — deletes all AI Memory, then runs first-time setup
   - **Exploratory / deep-dive:** `python src/chat.py --explore` (or `--deep-dive`) — conversational interview, then extracts and writes organized memory (core, context subdirs, timelines) before starting chat

## Launcher setup (one keypress or click)

The same Obsidian vault path is configured in a single place: **`.env`** (`OBSIDIAN_PATH`). Launchers use that; no hardcoded paths.

### Arch Linux (rofi, wofi, etc.)

1. From the repo root, run the install script:
   ```bash
   ./install.sh
   ```
2. Install copies a `.desktop` file to `~/.local/share/applications/` and makes the launcher script executable. First-run checks: vault path exists and (optionally) that the folder looks like an Obsidian vault (`.obsidian` present); you’ll get a warning if not.
3. Launch Memoria from rofi/wofi (search for “Memoria”) or bind a key in your WM to run:
   ```bash
   /path/to/repo/launcher/memoria.sh
   ```
   The script activates the venv and runs `python src/chat.py`; no need to touch the core codebase.

### Windows 11

1. Install **AutoHotkey** ([autohotkey.com](https://www.autohotkey.com/)) and **Windows Terminal** (Microsoft Store or `winget install Microsoft.WindowsTerminal`).
2. From the repo root in PowerShell, run:
   ```powershell
   .\install.ps1
   ```
3. Install creates a Desktop and Start Menu shortcut that runs the AutoHotkey script. First-run checks the same vault path from `.env` and warns if the path is missing or doesn’t look like an Obsidian vault.
4. Double-click the shortcut (or run `launcher\memoria.ahk`) so the hotkey is active. Then press **Ctrl+Alt+M** anywhere to open a Memoria session in Windows Terminal (venv is activated and `python src/chat.py` runs automatically). Optional: add the shortcut to Startup for hotkey at login.

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
