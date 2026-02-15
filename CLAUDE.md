# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CLI chatbot that runs on OpenAI-compatible LLM endpoints (OpenRouter, LM Studio, etc.) and persists memory across conversations using an Obsidian vault as the storage backend. The model has tools to read/write a hierarchical memory system and search the user's vault.

## Commands

```bash
# Run the app
python src/chat.py
python src/chat.py --reset-memory      # Wipe user memory (preserves soul), start fresh
python src/chat.py --reset-soul        # Reset Memoria's soul/ directory to defaults
python src/chat.py --reset-memory --reset-soul  # Full wipe: memory + soul

# Tests (101 tests, all tool-layer; no LLM integration tests)
./venv/bin/python -m pytest tests/ -v
./venv/bin/python -m pytest tests/test_llm_tools.py::test_read_core_memory_empty -v

# Dependencies
pip install -r requirements.txt        # dotenv, rich, requests, pytest
```

The project uses a venv at `./venv/`. There is no pyproject.toml or setup.py — modules use `sys.path.insert(0, ...)` for imports.

## Environment

Requires a `.env` file (see `.env.example`):
- `LLM_API_URL` — OpenAI-compatible endpoint base (default `https://openrouter.ai/api/v1`). Fallback: `LMSTUDIO_URL`.
- `LLM_MODEL` — Model name (default `openai/gpt-oss-120b`).
- `LLM_API_KEY` — API key (required for OpenRouter; optional for local endpoints). Fallback: `LMSTUDIO_API_KEY`.
- `OBSIDIAN_PATH` — absolute path to Obsidian vault (required)

## Architecture

### Data flow

```
User input → chat.py → llm.py:run_agent_loop → call_llm (OpenAI-compatible API)
                                ↓ (if tool calls)
                        tools.py:execute_tool → memory.py / obsidian.py → vault filesystem
                                ↓ (tool results fed back)
                        call_llm again → ... → final text response
```

### Module responsibilities

- **chat.py** — Entry point, arg parsing, main loop. Builds system message from `build_system_prompt()` + core memory. On first run, opens with a natural greeting; memory builds organically through conversation. Triggers consolidation on quit.
- **llm.py** — `call_llm()` (raw HTTP to OpenAI-compatible endpoint), `run_agent_loop()` (the agentic tool loop), `truncate_messages()` (turn-boundary-aware context trimming), JSON extraction/repair for truncated LLM output.
- **memory.py** — All vault read/write operations for hierarchical memory (core, context, timelines, archive) and soul directory. Unified `read_memory_file(path)` / `write_memory_file(path, content)` for structured files. `build_memory_map()` walks context, timelines, and archive to produce a live directory listing (with file sizes) injected into the system prompt. Soul directory is excluded from the memory map.
- **tools.py** — OpenAI-format tool definitions (15 tools), argument parsing, dispatch table mapping tool names to handler functions. Two tool lists: `CHAT_TOOLS` (all 15) and `CONSOLIDATION_TOOLS` (subset: core + read/write memory + archive + update_soul).
- **prompts.py** — All prompt templates. `SYSTEM_PROMPT` (static string), `build_system_prompt()` (appends soul files + live memory map), first-conversation guidance, consolidation prompts.
- **consolidation.py** — Runs an agentic loop on quit so the model can read-then-write memory updates. After the main loop, automatically consolidates observations (summarizes old entries, archives full content) when above threshold.
- **obsidian.py** — Vault search (title + content, relevance scoring) and AI Memory note CRUD with path traversal protection. Imports `_get_vault_path` from memory.py (single source of truth for vault path).
- **ui.py** — Rich console with cyberpunk theme, tool call/result panels, welcome display.

### Memory hierarchy (stored in `{OBSIDIAN_PATH}/AI Memory/`)

```
soul/                       Memoria's private internal world (not in memory map, persists through resets)
  soul.md                   core identity, sense of self, relationship with user
  observations.md           append-only timestamped log of patterns noticed about the user
  observations_archive.md   full pre-compression content, preserved during consolidation
  opinions.md               views Memoria is developing
  unresolved.md             open questions about the user
core-memory.md              ~500 token working memory, loaded every conversation
context/
  personal.md, work.md, ... flat categories
  work/projects.md, ...     nested categories      ← all via read_memory / write_memory
timelines/
  current-goals.md          active goals            ← read/rewrite via read_memory / write_memory
  future-plans.md
archive/
  YYYY-MM/conversations.md  monthly summaries       ← append via archive_memory, read via read_archive
```

The soul/ directory is Memoria's private space — its evolving self-concept, observations, opinions, and unresolved questions. All soul files are injected into the system prompt together under "## Who I Am". Most soul files are modifiable via `update_soul(content, file)` tool (file accepts: soul, opinions, unresolved). Observations use dedicated tools: `update_observations` (append-only timestamped log) and `resolve_observation` (mark entries inactive). Protected from write_memory, create/update/delete_memory_note, excluded from list_memory_notes and the memory map. Soul persists through `--reset-memory`; use `--reset-soul` to reset to defaults.

Observations follow an append-only pattern: each call to `update_observations` adds a timestamped entry. Resolved entries are excluded from context injection but remain in the file. When observations exceed 800 tokens or 20 entries, end-of-session consolidation summarizes old entries (keeping 10 most recent), archives the full file to `observations_archive.md`, and writes a compressed summary block. Context loading stays under ~400 tokens.

Core memory is injected into the system message at startup and refreshed after every agent loop turn. Context and timeline files are loaded on demand by the model via `read_memory(path)` tool calls. The memory map in the system prompt shows all available files with sizes.

### Key patterns

- **Agentic loop**: `run_agent_loop()` in llm.py handles both chat and consolidation. It calls the LLM, executes any tool calls, feeds results back, and repeats until the model responds without tools or hits max iterations (10). Tool results are truncated at 6000 chars (~1500 tokens) to limit context growth.
- **Retry with backoff**: `call_llm()` retries failed requests up to 2 times with exponential backoff (2s, 4s). Handles transient network errors and 429/500 responses.
- **System prompt assembly**: `build_system_prompt()` (prompts.py) reads all soul files via `read_soul()` and appends them as "## Who I Am", then appends the live memory map from `build_memory_map()` (memory.py). Then `_build_system_content()` (chat.py) appends core memory content (and first-conversation guidance on first run). This happens at init and after every turn.
- **No structured onboarding**: First run opens with a natural greeting. Memory builds organically through conversation via normal tool use. No questionnaire, no explore mode.
- **No `tool_choice: "auto"`**: Explicitly omitted because some backends replace the system message when it's set, which would drop core memory from context.
- **Streaming**: Only the first LLM response per user turn is streamed (for UX). Subsequent responses after tool calls are not streamed.
- **`max_tokens` default**: `None` in `call_llm()` signature. Resolved to 4096 when tools are present, 500 otherwise.

### Test structure

Tests in `tests/test_llm_tools.py` use a `vault_path` fixture that points `OBSIDIAN_PATH` to a temp directory. The `execute_tool` fixture imports after env is set. All tests are tool-layer only — no LLM calls, no mocking of `call_llm`. The consolidation agentic loop test uses `unittest.mock.patch` on `llm.call_llm`.
