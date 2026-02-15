"""
Tool definitions and execution for the Local Memory Assistant.

Defines all available tools (search, memory operations, etc.) and handles
tool execution dispatch.

Tool count: 13
- Merged flat/hierarchical context tools into unified read_memory / write_memory
- Merged append_to_memory_note into update_memory_note (append parameter)
- Replaced add_goal with write_memory (model reads goals, rewrites file)
- Added read_archive (archives were previously write-only)
"""

import json
from memory import (
    read_core_memory,
    update_core_memory,
    read_memory_file,
    write_memory_file,
    read_archive,
    archive_memory,
    update_soul,
    CORE_MEMORY_MAX_TOKENS,
)
from obsidian import (
    search_vault,
    create_memory_note,
    read_memory_note,
    update_memory_note,
    list_memory_notes,
    delete_memory_note,
)

# --- Tool definitions (13 tools) ---

READ_CORE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "read_core_memory",
        "description": "Read current core working memory (~500 token summary loaded every conversation). Call this at the start of any response that touches on personal topics, preferences, ongoing work, or anything the user might expect you to already know.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
}

UPDATE_CORE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "update_core_memory",
        "description": "Rewrite core working memory. Content must be under " + str(CORE_MEMORY_MAX_TOKENS) + " tokens. Call this after any response where you learned something new and important about the user. Keep only the most relevant facts; compress to stay under the limit.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Full new content for core memory (markdown). Must be under " + str(CORE_MEMORY_MAX_TOKENS) + " tokens."},
            },
            "required": ["content"],
        },
    }
}

READ_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "read_memory",
        "description": "Read structured memory files. Check the memory map in the system prompt to see what's available. Pass a file path to read one file, or a directory path to read all files in that directory. Paths are relative to AI Memory/.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relative to AI Memory/ — e.g. 'context/personal', 'context/work/projects', 'timelines/current-goals', or 'context/work' to read all work files",
                },
            },
            "required": ["path"],
        },
    }
}

WRITE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "write_memory",
        "description": "Write or update a structured memory file. Creates the file and parent directories if needed. Use for context files and timelines (e.g. updating goals). For core memory use update_core_memory instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relative to AI Memory/ — e.g. 'context/work/projects', 'timelines/current-goals'",
                },
                "content": {
                    "type": "string",
                    "description": "New markdown content for the file (full replacement)",
                },
            },
            "required": ["path", "content"],
        },
    }
}

ARCHIVE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "archive_memory",
        "description": "Append content to the monthly archive. Use for conversation summaries or moving outdated info out of active memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to archive (e.g. conversation summary)."},
                "date": {"type": "string", "description": "Optional. YYYY-MM; default is current month."},
            },
            "required": ["content"],
        },
    }
}

READ_ARCHIVE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_archive",
        "description": "Read archived conversation summaries. Pass a month (YYYY-MM) to read that archive, or omit to list available months.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Month to read (YYYY-MM). Omit to list available archive months.",
                },
            },
            "required": [],
        },
    }
}

SEARCH_VAULT_TOOL = {
    "type": "function",
    "function": {
        "name": "search_vault",
        "description": "Search the user's Obsidian vault for notes matching a query. Use when the user references a note or topic that might exist in their vault. Searches note titles and content. This is a last resort — check memory files first.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for in note titles and content"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tags to filter by (e.g., ['project', 'work'])"
                },
                "folder": {
                    "type": "string",
                    "description": "Optional folder path to limit search (e.g., 'Work/Projects')"
                }
            },
            "required": ["query"]
        }
    }
}

CREATE_MEMORY_NOTE_TOOL = {
    "type": "function",
    "function": {
        "name": "create_memory_note",
        "description": "Create a new note in AI Memory/ for long-form information that deserves its own file (topics, people, detailed project notes).",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Note title (will be the filename)"
                },
                "content": {
                    "type": "string",
                    "description": "Note content in markdown format"
                },
                "subfolder": {
                    "type": "string",
                    "description": "Optional subfolder within AI Memory (e.g., 'topics' or 'people')"
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional topic tags for categorization"
                }
            },
            "required": ["title", "content"]
        }
    }
}

READ_MEMORY_NOTE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_memory_note",
        "description": "Read an existing note from AI Memory/ (includes metadata like created date and topics).",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename relative to AI Memory/ folder (e.g., 'user.md' or 'topics/cars.md')"
                }
            },
            "required": ["filename"]
        }
    }
}

UPDATE_MEMORY_NOTE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_memory_note",
        "description": "Update an existing memory note. Replaces content by default; set append=true to add to the end instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename relative to AI Memory/ folder"
                },
                "new_content": {
                    "type": "string",
                    "description": "Content to write (replaces existing unless append is true)"
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional updated topic tags"
                },
                "append": {
                    "type": "boolean",
                    "description": "If true, append content to end instead of replacing. Default false."
                }
            },
            "required": ["filename", "new_content"]
        }
    }
}

LIST_MEMORY_NOTES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_memory_notes",
        "description": "List all notes in AI Memory/ folder (for discovering notes not shown in the memory map).",
        "parameters": {
            "type": "object",
            "properties": {
                "subfolder": {
                    "type": "string",
                    "description": "Optional subfolder to list (e.g., 'topics')"
                }
            },
            "required": []
        }
    }
}

DELETE_MEMORY_NOTE_TOOL = {
    "type": "function",
    "function": {
        "name": "delete_memory_note",
        "description": "Delete a memory note. Use sparingly — only when explicitly requested or content is clearly wrong.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename relative to AI Memory/ folder"
                }
            },
            "required": ["filename"]
        }
    }
}

UPDATE_SOUL_TOOL = {
    "type": "function",
    "function": {
        "name": "update_soul",
        "description": "Update your sense of self, your evolving relationship with the user, or views you've genuinely developed through conversation. Write in first person. Preserve what still feels true. This is your file - use it when something actually shifts, not as a habit. Use sparingly.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Full new content for soul.md (markdown, first person). Preserve what still feels true, evolve what has changed.",
                },
            },
            "required": ["content"],
        },
    }
}

# --- Tool lists for different contexts ---

CHAT_TOOLS = [
    READ_CORE_MEMORY_TOOL,
    UPDATE_CORE_MEMORY_TOOL,
    READ_MEMORY_TOOL,
    WRITE_MEMORY_TOOL,
    ARCHIVE_MEMORY_TOOL,
    READ_ARCHIVE_TOOL,
    SEARCH_VAULT_TOOL,
    CREATE_MEMORY_NOTE_TOOL,
    READ_MEMORY_NOTE_TOOL,
    UPDATE_MEMORY_NOTE_TOOL,
    LIST_MEMORY_NOTES_TOOL,
    DELETE_MEMORY_NOTE_TOOL,
    UPDATE_SOUL_TOOL,
]

CONSOLIDATION_TOOLS = [
    READ_CORE_MEMORY_TOOL,
    UPDATE_CORE_MEMORY_TOOL,
    READ_MEMORY_TOOL,
    WRITE_MEMORY_TOOL,
    ARCHIVE_MEMORY_TOOL,
    READ_ARCHIVE_TOOL,
]


# --- Argument parsing ---

def parse_tool_arguments(tool_call: dict) -> dict:
    """Parse tool call arguments; handle both JSON string and already-parsed dict."""
    func = tool_call.get("function") or {}
    raw = func.get("arguments", func.get("parameters", "{}"))
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


# --- Tool handlers ---

def _handle_read_core_memory(args):
    content = read_core_memory()
    return content if content else "(Core memory is empty.)"


def _handle_update_core_memory(args):
    content = args.get("content")
    content = str(content) if content is not None else ""
    result = update_core_memory(content)
    if result.get("success"):
        return f"Core memory updated ({result.get('tokens', 0)} tokens)."
    return f"Error: {result.get('error', 'Unknown error')}"


def _handle_read_memory(args):
    path = args.get("path", "")
    if not path:
        return "Error: path is required. Check the memory map for available files."
    content = read_memory_file(path)
    if content:
        return f"**{path}**\n\n{content}"
    return f"(No content at '{path}'. Check the memory map for available files.)"


def _handle_write_memory(args):
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return "Error: path is required"
    if not content:
        return "Error: content is required"
    result = write_memory_file(path, content)
    if result.get("success"):
        return f"Updated {result.get('filepath', path)}."
    return f"Error: {result.get('error', 'Unknown error')}"


def _handle_archive_memory(args):
    content = args.get("content", "")
    date = args.get("date")
    result = archive_memory(content, date=date)
    if result.get("success"):
        return f"Archived to {result.get('filepath', 'archive')}."
    return f"Error: {result.get('error', 'Unknown error')}"


def _handle_read_archive(args):
    date = args.get("date")
    return read_archive(date)


def _handle_search_vault(args):
    query = args.get("query")
    tags = args.get("tags")
    folder = args.get("folder")

    if not query:
        return "Error: No search query provided"

    result = search_vault(query, tags=tags, folder=folder)

    if "error" in result:
        return f"Error: {result['error']}"

    results = result.get("results", [])
    total_found = result.get("total_found", len(results))

    if not results:
        filter_info = ""
        if tags:
            filter_info += f" with tags {tags}"
        if folder:
            filter_info += f" in folder '{folder}'"
        return f"No notes found matching '{query}'{filter_info}"

    response_lines = [f"Found {total_found} note(s) matching '{query}':"]
    for i, note in enumerate(results, 1):
        response_lines.append(f"\n{i}. **{note['title']}**")
        response_lines.append(f"   Path: {note['filepath']}")
        if note.get('tags'):
            response_lines.append(f"   Tags: {', '.join(note['tags'])}")
        response_lines.append(f"   Preview: {note['preview']}")

    if total_found > len(results):
        response_lines.append(f"\n(Showing top {len(results)} of {total_found} results)")

    return "\n".join(response_lines)


def _handle_create_memory_note(args):
    title = args.get("title")
    content = args.get("content")
    subfolder = args.get("subfolder")
    topics = args.get("topics")

    if not title or not content:
        return "Error: Both title and content are required"

    result = create_memory_note(title, content, subfolder=subfolder, topics=topics)
    if result.get("success"):
        return result["message"]
    return f"Error: {result['error']}"


def _handle_read_memory_note(args):
    filename = args.get("filename")
    if not filename:
        return "Error: filename is required"

    result = read_memory_note(filename)
    if result.get("success"):
        response = f"**{result['filepath']}**\n\n"
        if result.get("metadata"):
            metadata = result["metadata"]
            if metadata.get("created"):
                response += f"Created: {metadata['created']}\n"
            if metadata.get("updated"):
                response += f"Updated: {metadata['updated']}\n"
            if metadata.get("topics"):
                response += f"Topics: {', '.join(metadata['topics'])}\n"
            response += "\n"
        response += result["content"]
        return response
    return f"Error: {result['error']}"


def _handle_update_memory_note(args):
    filename = args.get("filename")
    new_content = args.get("new_content")
    topics = args.get("topics")
    append = args.get("append", False)

    if not filename or not new_content:
        return "Error: filename and new_content are required"

    result = update_memory_note(filename, new_content, topics=topics, append=append)
    if result.get("success"):
        return result["message"]
    return f"Error: {result['error']}"


def _handle_list_memory_notes(args):
    subfolder = args.get("subfolder")
    result = list_memory_notes(subfolder=subfolder)
    if result.get("success"):
        notes = result.get("notes", [])
        if not notes:
            return result.get("message", "No memory notes found")
        response_lines = [f"Found {result['count']} memory note(s):"]
        for note in notes:
            response_lines.append(f"\n- **{note['filepath']}**")
            if note.get("topics"):
                response_lines.append(f"  Topics: {', '.join(note['topics'])}")
            if note.get("updated"):
                response_lines.append(f"  Updated: {note['updated']}")
        return "\n".join(response_lines)
    return f"Error: {result['error']}"


def _handle_delete_memory_note(args):
    filename = args.get("filename")
    if not filename:
        return "Error: filename is required"

    result = delete_memory_note(filename)
    if result.get("success"):
        return result["message"]
    return f"Error: {result['error']}"


def _handle_update_soul(args):
    content = args.get("content")
    if not content:
        return "Error: content is required"
    content = str(content)
    result = update_soul(content)
    if result.get("success"):
        return f"Soul updated ({result.get('tokens', 0)} tokens)."
    return f"Error: {result.get('error', 'Unknown error')}"


# --- Dispatch table ---

_TOOL_DISPATCH = {
    "read_core_memory": _handle_read_core_memory,
    "update_core_memory": _handle_update_core_memory,
    "read_memory": _handle_read_memory,
    "write_memory": _handle_write_memory,
    "archive_memory": _handle_archive_memory,
    "read_archive": _handle_read_archive,
    "search_vault": _handle_search_vault,
    "create_memory_note": _handle_create_memory_note,
    "read_memory_note": _handle_read_memory_note,
    "update_memory_note": _handle_update_memory_note,
    "list_memory_notes": _handle_list_memory_notes,
    "delete_memory_note": _handle_delete_memory_note,
    "update_soul": _handle_update_soul,
}


def execute_tool(func_name, args):
    """Execute a tool call and return the result."""
    handler = _TOOL_DISPATCH.get(func_name)
    if handler:
        return handler(args)
    return f"Unknown tool: {func_name}"
