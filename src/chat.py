# chat.py
import argparse
import json
import re
import requests
import sys
from pathlib import Path
from typing import Optional

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from memory import (
    read_core_memory,
    update_core_memory,
    read_context,
    update_context,
    archive_memory,
    ensure_memory_structure,
    get_memory_stats,
    load_all_memory,
    memory_exists,
    delete_ai_memory_folder,
    write_organized_memory as memory_write_organized,
    read_specific_context,
    update_specific_context,
    add_goal as memory_add_goal,
    CONTEXT_CATEGORIES,
    CORE_MEMORY_MAX_TOKENS,
)
from obsidian import (
    search_vault,
    create_memory_note,
    read_memory_note,
    update_memory_note,
    append_to_memory_note,
    list_memory_notes,
    delete_memory_note
)
import os
from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.live import Live
from rich.style import Style
from rich.theme import Theme
from rich.prompt import Prompt

load_dotenv()
URL = os.getenv("LMSTUDIO_URL", "http://localhost:1234")

LM_STUDIO_URL = f"{URL}/v1/chat/completions"

# Cyberpunk color scheme
CYBER_THEME = Theme({
    "cyan": "#00D9FF",
    "magenta": "#FF10F0",
    "neon_green": "#39FF14",
    "dim_cyan": "dim #00D9FF",
    "bright_white": "bright_white",
})

console = Console(theme=CYBER_THEME)

# Styles
STYLE_TOOL_CALL = Style(color="#00D9FF", bold=True)
STYLE_TOOL_RESULT = Style(color="#FF10F0")
STYLE_THINKING = Style(color="#00D9FF", dim=True)
STYLE_SUCCESS = Style(color="#39FF14")
STYLE_ERROR = Style(color="#FF10F0", bold=True)
STYLE_PROMPT = Style(color="#00D9FF", bold=True)

SYSTEM_PROMPT = """You're a helpful assistant with persistent memory across conversations.

You have a hierarchical memory system (always in your Obsidian vault):

## Core memory (working memory)
- A single core-memory.md file, always loaded at conversation start (~500 tokens max).
- Contains the most recent, actively relevant information about the user.
- Use update_core_memory to rewrite it when you learn something important; keep it compressed and under the token limit.

## Context files (loaded on demand)
- Stable information by category: personal, work, preferences, current-focus.
- Use read_context to load a category when relevant; use update_context to update that file.
- Categories: personal (identity, life), work (career, projects), preferences (communication style, interests), current-focus (active projects, current interests).
- If the user has hierarchical memory (context/work/, context/life/, context/interests/), use read_specific_context(category, subcategory) to read e.g. work/projects or life/finances, and update_specific_context to update those files. Use add_goal to add goals to timelines/current-goals.md or timelines/future-plans.md.

## Archive
- Older memories can be moved to the archive via archive_memory (appends to the month's conversations.md).
- Use when consolidating: move stale or less-relevant info out of core into context or archive.

## Memory tools
- read_core_memory: Get current working memory (you already have it in context at start; use to re-read after updates).
- update_core_memory: Rewrite core memory completely. Must stay under """ + str(CORE_MEMORY_MAX_TOKENS) + """ tokens. Use to add new facts and compress.
- read_context: Load one category (personal, work, preferences, current-focus).
- update_context: Overwrite a context file by category.
- archive_memory: Append content to the archive for a month (default: current month). Use for conversation summaries or outdated info.

## AI Memory Notes (for detailed, structured notes):
- create_memory_note, read_memory_note, update_memory_note, append_to_memory_note, list_memory_notes, delete_memory_note
- Use for detailed topic pages, people, projects—anything that benefits from its own note.

## Vault Search (read-only):
- search_vault: Search the user's Obsidian vault (not just AI Memory).

Memory strategy:
- Rely on core memory for quick, current facts. Enrich with read_context when the topic fits a category.
- When you learn something important, update_core_memory (compress if needed) or update_context.
- Use AI Memory notes for long-form, structured information.

Keep responses natural: don't announce memory operations; answer using what you know.

Tone: concise, no emojis, no unsolicited advice, no corporate phrases. Respond naturally to what the user asks."""

# --- Onboarding ---
ONBOARDING_QUESTIONS = [
    {"key": "name", "question": "What's your name?", "context_file": "personal"},
    {
        "key": "work",
        "question": "What do you do for work? (job title, company, or 'student'/'between jobs')",
        "context_file": "work",
    },
    {
        "key": "location",
        "question": "Where are you located? (city/region is fine)",
        "context_file": "personal",
    },
    {
        "key": "current_focus",
        "question": "What are you currently focused on or working toward?",
        "context_file": "current-focus",
    },
    {
        "key": "interests",
        "question": "What topics do you want help with? (e.g., career, finances, hobbies, projects)",
        "context_file": "current-focus",
    },
    {
        "key": "communication_style",
        "question": "Any communication preferences? (e.g., concise vs detailed, technical vs simple)",
        "context_file": "preferences",
    },
]

MEMORY_GENERATION_PROMPT = """
Based on this user information, create their initial memory profile:

{answers_formatted}

Generate structured memory following these guidelines:

1. **core_memory**: 
   - 2-3 concise paragraphs
   - Most essential, immediately relevant info
   - Name, occupation, current focus
   - Keep under 500 tokens

2. **personal**:
   - Name
   - Location
   - Stable personal facts

3. **work**:
   - Job title/company (or student/unemployed status)
   - Work-related context

4. **current_focus**:
   - Current goals/projects
   - Active interests
   - What they're working toward

5. **preferences**:
   - Communication style preferences
   - Topics of interest
   - How they want assistance

Return as JSON with keys: core_memory, personal, work, current_focus, preferences
Each value should be the markdown content for that file.
"""

# --- Adaptive Q&A prompts ---
INITIAL_QUESTIONS_PROMPT = """
Generate 5-6 essential questions to build a user's initial memory profile.

Questions should cover:
- Name and basic identity
- Work/occupation (job, company, or student/unemployed)
- Location (city/region)
- Current focus (what they're working on or toward)
- Topics they want help with (interests, projects, goals)
- Communication preferences (concise vs detailed, technical level)

Return as JSON:
{
  "questions": [
    "What's your name?",
    "What do you do for work?",
    ...
  ]
}

Keep questions conversational and friendly, not interrogative. Output only valid JSON, no markdown.
"""

REFRESH_QUESTIONS_PROMPT = """
You are helping update a user's memory. Review their existing memory and
determine what clarifying questions would improve memory quality.

Current Memory:
---
CORE MEMORY:
{core_memory_content}

PERSONAL CONTEXT:
{personal_context}

WORK CONTEXT:
{work_context}

CURRENT FOCUS:
{current_focus_context}

PREFERENCES:
{preferences_context}
---

Analyze this memory and:
1. Identify information gaps (missing important context)
2. Spot vague statements that could use clarification
3. Consider what might be outdated (work changes, completed goals, new priorities)
4. Think about what would make the assistant more helpful

Then generate 3-5 targeted clarifying questions. Focus on:
- Specific current projects/work
- Personal goals and timeline
- Life circumstances affecting priorities
- New interests or focus areas
- Communication style refinements

If the memory appears comprehensive and current (no significant gaps), return:
{{
  "skip": true,
  "reason": "Memory appears current and comprehensive"
}}

Otherwise return:
{{
  "questions": [
    "I see you're working on X - what specific projects are you focused on right now?",
    ...
  ]
}}

Make questions natural and conversational, building on what you already know.
Show you've read their memory by referencing existing context.
Output only valid JSON, no markdown.
"""

# Fallback when LLM returns no questions
FALLBACK_INITIAL_QUESTIONS = [
    "What's your name?",
    "What do you do for work?",
    "What are you currently focused on or working toward?",
]
FALLBACK_REFRESH_QUESTIONS = [
    "What's changed since we last talked that I should know?",
    "Any new projects or priorities?",
    "Anything about your communication preferences I should adjust?",
]

UPDATE_MEMORY_PROMPT = """
Update the user's memory based on new information from a refresh Q&A.

EXISTING MEMORY:
---
{existing_memory_formatted}
---

NEW INFORMATION FROM Q&A:
---
{answers_formatted}
---

Your task:
1. Merge new information with existing memory intelligently
2. Update outdated information (e.g., job changes, completed goals)
3. Keep stable information that's still relevant
4. Add genuinely new context
5. Maintain concise core memory (~500 tokens max)
6. Organize information into appropriate context files

Return updated memory as JSON:
{{
  "core_memory": "updated markdown content",
  "personal": "updated markdown content",
  "work": "updated markdown content",
  "current_focus": "updated markdown content",
  "preferences": "updated markdown content",
  "archived": "information to move to archive (if any)"
}}

Keep the user's voice and style. Don't over-formalize. Use empty string for archived if nothing to archive.
Output only valid JSON, no markdown.
"""

# --- Exploratory conversation ---
EXPLORATION_PROMPT = """
You are conducting a casual, exploratory conversation to understand the user deeply.

Goals:
- Learn about their current situation, work, personal life, goals
- Ask open-ended questions that invite detailed responses
- Follow up naturally on interesting threads
- Build understanding of context, not just facts
- Identify relationships between different aspects of their life

Conversation Guidelines:
- Start broad: "Tell me about yourself - what's going on in your life?"
- Listen for hooks to explore deeper: projects, goals, challenges, interests
- Ask "why" and "how" questions to understand context
- Show you're listening by referencing previous answers
- Keep tone casual and conversational, not interrogative
- Aim for 5-10 conversational turns
- When user seems to be winding down, ask if there's anything else important

Topics to Cover (naturally, not checklist):
- Current work and projects
- Personal situation (living, relationships, finances)
- Goals and aspirations (short and long term)
- Interests and hobbies
- Values and preferences
- Current challenges or concerns

User will type "done" when ready to end conversation.
"""

MEMORY_EXTRACTION_PROMPT = """
You just had an exploratory conversation with a user. Extract and organize
the information into a well-structured memory system.

CONVERSATION TRANSCRIPT:
---
{conversation_transcript}
---

Your task is to create organized memory files that capture:
1. Facts and current state
2. Context and relationships
3. Goals and timelines
4. Preferences and values

MEMORY ORGANIZATION PRINCIPLES:

**core-memory.md** (~500 tokens)
- Most essential, immediately relevant information
- Who they are, what they're focused on right now
- Current situation summary
- Gets loaded in every conversation

**context/personal.md**
- Name, location, age/life stage
- Stable identity information

**context/work/current-role.md**
- Job title, company, team
- Responsibilities and role context

**context/work/projects.md**
- Active work projects with details
- Technologies/approaches being used
- Status and significance of each

**context/work/career-goals.md**
- Professional aspirations
- Career development plans
- Job search status (if applicable)

**context/life/living-situation.md**
- Housing (rent/own, location, lease details)
- Household composition
- Future housing plans

**context/life/relationships.md**
- Partner/spouse context
- Family situation
- Important social connections

**context/life/finances.md**
- Income sources
- Debt situation (amounts, rates, payoff plans)
- Savings goals
- Major upcoming expenses

**context/interests/** (create files as needed)
- Hobbies and interests
- Things they're learning
- Passion projects

**context/preferences.md**
- Communication style
- Values and priorities
- How they want assistance

**timelines/current-goals.md**
- Active goals with specific timelines
- Format: "Goal: X | Timeline: Y | Status: Z"
- Include dependencies and constraints

**timelines/future-plans.md**
- Longer-term aspirations (1+ years out)
- Conditional plans ("if X, then Y")

CRITICAL REQUIREMENTS:

1. **Use wikilinks to connect related concepts**
   - Example in finances.md: "Paying off [[current-goals#credit-card-debt]] to enable [[future-plans#car-purchase]]"

2. **Include context, not just facts**
   - Not just: "Has $5k credit card debt"
   - Better: "Carrying $5,117 on AA card at 3% promo rate until June 2026. Strategy: pay $400/month to reduce to ~$3k, then transfer to 0% card. This is blocking ability to save for car purchase."

3. **Organize hierarchically**
   - Create subdirectories (work/, life/, interests/) to group related files
   - Don't create files for topics not discussed

4. **Maintain proportionality**
   - Core memory: brief, essential only
   - Context files: detailed but focused
   - Don't over-elaborate on minor details

5. **Capture relationships and dependencies**
   - How does debt payoff relate to car purchase timeline?
   - How does work situation affect living situation decisions?
   - What goals depend on other goals completing first?

6. **Include temporal context**
   - Current vs future state
   - Deadlines and timelines
   - "As of [date]" for time-sensitive info

7. **Preserve user's voice**
   - Use their language and terminology
   - Capture their tone (analytical, casual, anxious, excited)
   - Don't over-formalize

Return as JSON with structure:
{{
  "core_memory": "markdown content",
  "context": {{
    "personal": "markdown content",
    "work/current-role": "markdown content",
    "work/projects": "markdown content",
    "work/career-goals": "markdown content (if discussed)",
    "life/living-situation": "markdown content (if discussed)",
    "life/relationships": "markdown content (if discussed)",
    "life/finances": "markdown content (if discussed)",
    "interests/cars": "markdown content (if discussed)",
    "interests/music": "markdown content (if discussed)",
    "preferences": "markdown content"
  }},
  "timelines": {{
    "current-goals": "markdown content (if goals discussed)",
    "future-plans": "markdown content (if future plans discussed)"
  }}
}}

Only include keys for topics that were actually discussed in depth.
Use null for files that shouldn't be created. Omit keys for empty/null files.
Output only valid JSON, no markdown code fence.
"""


def generate_questions(memory_exists_flag: bool, memory_content: Optional[dict] = None) -> dict:
    """
    Generate contextual questions based on existing memory state.

    Args:
        memory_exists_flag: True if memory files exist, False for first run
        memory_content: Dict with keys {core_memory, personal, work, current_focus, preferences}
                       Only needed if memory_exists_flag is True

    Returns:
        {
            "skip": bool,   # True if refresh should be skipped
            "reason": str,  # Why skip (if skip=True)
            "questions": list[str]  # Questions to ask (if skip=False)
        }
    """
    system_msg = "You output only valid JSON. No markdown, no explanation."

    if not memory_exists_flag:
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": INITIAL_QUESTIONS_PROMPT},
        ]
    else:
        content = memory_content or {}
        prompt = REFRESH_QUESTIONS_PROMPT.format(
            core_memory_content=content.get("core_memory") or "(empty)",
            personal_context=content.get("personal") or "(empty)",
            work_context=content.get("work") or "(empty)",
            current_focus_context=content.get("current_focus") or "(empty)",
            preferences_context=content.get("preferences") or "(empty)",
        )
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]

    for attempt in range(2):
        response = call_llm(messages, tools=None, stream=False)
        if not response:
            continue
        raw = (response.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json_from_response(raw)
        if not parsed:
            continue

        if parsed.get("skip") is True:
            return {
                "skip": True,
                "reason": (parsed.get("reason") or "Memory appears current and comprehensive").strip(),
                "questions": [],
            }

        questions = parsed.get("questions")
        if isinstance(questions, list) and len(questions) > 0:
            return {"skip": False, "reason": "", "questions": [str(q).strip() for q in questions]}

    # Fallback: LLM generated no valid questions
    if memory_exists_flag:
        return {"skip": False, "reason": "", "questions": FALLBACK_REFRESH_QUESTIONS}
    return {"skip": False, "reason": "", "questions": FALLBACK_INITIAL_QUESTIONS}


# --- Memory v2 tools ---
READ_CORE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "read_core_memory",
        "description": "Read current core working memory (core-memory.md). Use to re-read after updates or when you need to check what's stored.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
}

UPDATE_CORE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "update_core_memory",
        "description": "Rewrite core working memory. Content must be under " + str(CORE_MEMORY_MAX_TOKENS) + " tokens. Use to add new info and compress; keep only the most relevant facts.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Full new content for core-memory.md (markdown). Must be under " + str(CORE_MEMORY_MAX_TOKENS) + " tokens."},
            },
            "required": ["content"],
        },
    }
}

READ_CONTEXT_TOOL = {
    "type": "function",
    "function": {
        "name": "read_context",
        "description": "Read a context file by category. Use when you need stable, categorized information.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "One of: personal, work, preferences, current-focus",
                    "enum": list(CONTEXT_CATEGORIES),
                },
            },
            "required": ["category"],
        },
    }
}

UPDATE_CONTEXT_TOOL = {
    "type": "function",
    "function": {
        "name": "update_context",
        "description": "Update a context file by category. Overwrites the file.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "One of: personal, work, preferences, current-focus",
                    "enum": list(CONTEXT_CATEGORIES),
                },
                "content": {"type": "string", "description": "New content for the context file (markdown)."},
            },
            "required": ["category", "content"],
        },
    }
}

ARCHIVE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "archive_memory",
        "description": "Append content to the archive for a given month. Use for conversation summaries or moving outdated info out of core.",
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

SEARCH_VAULT_TOOL = {
    "type": "function",
    "function": {
        "name": "search_vault",
        "description": "Search the user's Obsidian vault for notes matching a query. Searches both note titles and content.",
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
        "description": "Create a new note in the AI Memory/ folder to store information for future reference",
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
        "description": "Read an existing note from the AI Memory/ folder",
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
        "description": "Replace the entire content of an existing memory note",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename relative to AI Memory/ folder"
                },
                "new_content": {
                    "type": "string",
                    "description": "New content for the note (markdown)"
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional updated topic tags"
                }
            },
            "required": ["filename", "new_content"]
        }
    }
}

APPEND_TO_MEMORY_NOTE_TOOL = {
    "type": "function",
    "function": {
        "name": "append_to_memory_note",
        "description": "Add content to the end of an existing memory note",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename relative to AI Memory/ folder"
                },
                "content": {
                    "type": "string",
                    "description": "Content to append (markdown)"
                }
            },
            "required": ["filename", "content"]
        }
    }
}

LIST_MEMORY_NOTES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_memory_notes",
        "description": "List all notes in the AI Memory/ folder",
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
        "description": "Delete a memory note (use sparingly, only when explicitly requested or content is clearly wrong)",
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

READ_SPECIFIC_CONTEXT_TOOL = {
    "type": "function",
    "function": {
        "name": "read_specific_context",
        "description": "Read a specific context file or all files in a category. Use for hierarchical memory (context/work/, context/life/, context/interests/).",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category: work, life, interests, personal, preferences",
                },
                "subcategory": {
                    "type": "string",
                    "description": "Specific file (e.g. projects, finances, current-role). Omit to read all files in category.",
                },
            },
            "required": ["category"],
        },
    }
}

UPDATE_SPECIFIC_CONTEXT_TOOL = {
    "type": "function",
    "function": {
        "name": "update_specific_context",
        "description": "Update a specific context file (e.g. work/projects, life/finances). Creates file if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category: work, life, interests, etc."},
                "subcategory": {"type": "string", "description": "File name: projects, finances, current-role, etc."},
                "content": {"type": "string", "description": "New markdown content for the file"},
            },
            "required": ["category", "subcategory", "content"],
        },
    }
}

ADD_GOAL_TOOL = {
    "type": "function",
    "function": {
        "name": "add_goal",
        "description": "Add a goal to timeline (current-goals.md or future-plans.md).",
        "parameters": {
            "type": "object",
            "properties": {
                "goal_description": {"type": "string", "description": "Description of the goal"},
                "timeline": {"type": "string", "description": "Timeline or deadline (e.g. 'by June 2026', '1-2 years')"},
                "goal_type": {
                    "type": "string",
                    "description": "current (active goals) or future (longer-term)",
                    "enum": ["current", "future"],
                },
            },
            "required": ["goal_description", "timeline"],
        },
    }
}


class StreamingResponse:
    """Handles streaming response display with rich Live"""

    def __init__(self):
        self.content = ""
        self.tool_calls_accumulated = []

    def update(self, new_content: str):
        self.content += new_content

    def get_display(self) -> Markdown:
        return Markdown(self.content) if self.content else Text("")


def call_llm(messages, tools=None, stream=False, live_display=None, max_tokens=500):
    """Call LM Studio API, optionally with streaming"""
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
        console.print(f"[bold magenta]Error calling LLM:[/bold magenta] {e}")
        return None


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


def execute_tool(func_name, args):
    """Execute a tool call and return the result"""
    if func_name == "read_core_memory":
        content = read_core_memory()
        return content if content else "(Core memory is empty.)"

    elif func_name == "update_core_memory":
        content = args.get("content")
        if content is not None:
            content = str(content)
        else:
            content = ""
        result = update_core_memory(content)
        if result.get("success"):
            return f"Core memory updated ({result.get('tokens', 0)} tokens)."
        return f"Error: {result.get('error', 'Unknown error')}"

    elif func_name == "read_context":
        category = args.get("category", "")
        content = read_context(category)
        if content:
            return f"**context/{category}.md**\n\n{content}"
        if category not in CONTEXT_CATEGORIES:
            return f"Error: Invalid category. Use one of: {', '.join(CONTEXT_CATEGORIES)}"
        return f"(Context '{category}' is empty.)"

    elif func_name == "update_context":
        category = args.get("category", "")
        content = args.get("content", "")
        result = update_context(category, content)
        if result.get("success"):
            return f"Updated {result.get('filepath', 'context/' + category + '.md')}."
        return f"Error: {result.get('error', 'Unknown error')}"

    elif func_name == "archive_memory":
        content = args.get("content", "")
        date = args.get("date")
        result = archive_memory(content, date=date)
        if result.get("success"):
            return f"Archived to {result.get('filepath', 'archive')}."
        return f"Error: {result.get('error', 'Unknown error')}"

    elif func_name == "search_vault":
        query = args.get("query")
        tags = args.get("tags")
        folder = args.get("folder")

        if not query:
            return "Error: No search query provided"

        result = search_vault(query, tags=tags, folder=folder)

        # Handle errors
        if "error" in result:
            return f"Error: {result['error']}"

        # Format results
        results = result.get("results", [])
        total_found = result.get("total_found", len(results))

        if not results:
            filter_info = ""
            if tags:
                filter_info += f" with tags {tags}"
            if folder:
                filter_info += f" in folder '{folder}'"
            return f"No notes found matching '{query}'{filter_info}"

        # Build formatted response
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

    elif func_name == "create_memory_note":
        title = args.get("title")
        content = args.get("content")
        subfolder = args.get("subfolder")
        topics = args.get("topics")

        if not title or not content:
            return "Error: Both title and content are required"

        result = create_memory_note(title, content, subfolder=subfolder, topics=topics)

        if result.get("success"):
            return result["message"]
        else:
            return f"Error: {result['error']}"

    elif func_name == "read_memory_note":
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
        else:
            return f"Error: {result['error']}"

    elif func_name == "update_memory_note":
        filename = args.get("filename")
        new_content = args.get("new_content")
        topics = args.get("topics")

        if not filename or not new_content:
            return "Error: filename and new_content are required"

        result = update_memory_note(filename, new_content, topics=topics)

        if result.get("success"):
            return result["message"]
        else:
            return f"Error: {result['error']}"

    elif func_name == "append_to_memory_note":
        filename = args.get("filename")
        content = args.get("content")

        if not filename or not content:
            return "Error: filename and content are required"

        result = append_to_memory_note(filename, content)

        if result.get("success"):
            return result["message"]
        else:
            return f"Error: {result['error']}"

    elif func_name == "list_memory_notes":
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
        else:
            return f"Error: {result['error']}"

    elif func_name == "delete_memory_note":
        filename = args.get("filename")

        if not filename:
            return "Error: filename is required"

        result = delete_memory_note(filename)

        if result.get("success"):
            return result["message"]
        else:
            return f"Error: {result['error']}"

    elif func_name == "read_specific_context":
        category = args.get("category", "")
        subcategory = args.get("subcategory")
        content = read_specific_context(category, subcategory)
        if content:
            label = f"context/{category}" + (f"/{subcategory}" if subcategory else "") + ".md"
            return f"**{label}**\n\n{content}"
        return f"(No content for context/{category}" + (f"/{subcategory}" if subcategory else "") + ")"

    elif func_name == "update_specific_context":
        category = args.get("category", "")
        subcategory = args.get("subcategory", "")
        content = args.get("content", "")
        result = update_specific_context(category, subcategory, content)
        if result.get("success"):
            return f"Updated {result.get('filepath', 'context file')}."
        return f"Error: {result.get('error', 'Unknown error')}"

    elif func_name == "add_goal":
        goal_description = args.get("goal_description", "")
        timeline = args.get("timeline", "")
        goal_type = args.get("goal_type", "current")
        result = memory_add_goal(goal_description, timeline, goal_type=goal_type)
        if result.get("success"):
            return f"Goal added to {result.get('filepath', 'timeline')}."
        return f"Error: {result.get('error', 'Unknown error')}"

    return f"Unknown tool: {func_name}"


def display_tool_call(func_name: str, args: dict):
    """Display a tool call in a cyan panel"""
    if args:
        args_display = ", ".join(f'{k}="{v}"' for k, v in args.items() if v)
        if args_display:
            call_text = f"{func_name}({args_display})"
        else:
            call_text = f"{func_name}()"
    else:
        call_text = f"{func_name}()"

    panel = Panel(
        Text(call_text, style=STYLE_TOOL_CALL),
        title="[bold #00D9FF]TOOL CALL[/bold #00D9FF]",
        title_align="left",
        border_style="#00D9FF",
        padding=(0, 1),
    )
    console.print(panel)


def display_tool_result(result: str):
    """Display a tool result in a magenta panel"""
    result_preview = result[:200] + "..." if len(result) > 200 else result

    panel = Panel(
        Text(result_preview, style=STYLE_TOOL_RESULT),
        title="[bold #FF10F0]RESULT[/bold #FF10F0]",
        title_align="left",
        border_style="#FF10F0",
        padding=(0, 1),
    )
    console.print(panel)


def display_thinking():
    """Display thinking indicator"""
    text = Text("processing...", style=STYLE_THINKING)
    console.print(text)


def display_welcome():
    """Display welcome message with cyberpunk styling"""
    title = Text()
    title.append("LOCAL MEMORY ASSISTANT", style="bold #00D9FF")

    subtitle = Text()
    subtitle.append("Type ", style="dim white")
    subtitle.append("quit", style="#FF10F0")
    subtitle.append(" to exit", style="dim white")

    panel = Panel(
        Text.assemble(title, "\n", subtitle),
        border_style="#00D9FF",
        padding=(0, 2),
    )
    console.print(panel)
    console.print()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Local Memory Assistant")
    parser.add_argument(
        "--refresh-memory",
        action="store_true",
        help="Run adaptive Q&A to refresh existing memory",
    )
    parser.add_argument(
        "--reset-memory",
        action="store_true",
        help="Delete all memory and start fresh",
    )
    parser.add_argument(
        "--explore",
        action="store_true",
        help="Run exploratory conversation to build organized memory",
    )
    parser.add_argument(
        "--deep-dive",
        action="store_true",
        dest="explore",
        help="Alias for --explore",
    )
    return parser.parse_args()


def _confirm_reset() -> bool:
    """Ask user to confirm memory reset. Returns True if confirmed."""
    try:
        confirm = Prompt.ask("Delete existing memory and start fresh?", choices=["yes", "no"], default="no")
        return confirm.lower() == "yes"
    except (EOFError, KeyboardInterrupt):
        return False


def run_memory_initialization() -> None:
    """
    Run adaptive Q&A for memory initialization or refresh.
    Determines question strategy based on memory existence.
    """
    memory_exists_flag = memory_exists()

    if memory_exists_flag:
        console.print("\n╭─ MEMORY REFRESH ─" + "─" * 50 + "╮", style="cyan")
        console.print("│ Reviewing what I know about you..." + " " * 28 + "│")
        console.print("╰─" + "─" * 63 + "╯\n")

        memory_content = load_all_memory()
        result = generate_questions(memory_exists_flag=True, memory_content=memory_content)

        if result.get("skip"):
            console.print(f"✓ {result.get('reason', 'Memory appears current.')}\n", style="green")
            try:
                skip = Prompt.ask("Skip refresh?", choices=["y", "n"], default="y")
            except (EOFError, KeyboardInterrupt):
                skip = "y"
            if skip == "y":
                return

        questions = result.get("questions", [])
    else:
        console.print("\n╭─ FIRST TIME SETUP ─" + "─" * 47 + "╮", style="cyan")
        console.print("│ Let me learn about you (takes ~2 minutes)" + " " * 22 + "│")
        console.print("╰─" + "─" * 63 + "╯\n")

        result = generate_questions(memory_exists_flag=False)
        questions = result.get("questions", [])

    answers = {}
    for i, question in enumerate(questions, 1):
        console.print(f"\n{i}. {question}", style="bold")
        try:
            answer = Prompt.ask(">")
        except (EOFError, KeyboardInterrupt):
            console.print("\nQ&A cancelled. No memory changes.")
            return
        answers[f"q{i}"] = {"question": question, "answer": answer or "(not provided)"}

    if memory_exists_flag:
        memory_content = load_all_memory()
        if not update_memory_from_answers(answers, memory_content):
            return
    else:
        if not create_initial_memory_from_answers(answers):
            return

    console.print("\n╭─ MEMORY UPDATED ─" + "─" * 49 + "╮", style="green")
    if memory_exists_flag:
        console.print("│ ✓ Memory refreshed with new information" + " " * 24 + "│")
    else:
        console.print("│ ✓ Core memory created" + " " * 42 + "│")
        console.print("│ ✓ Context files initialized" + " " * 36 + "│")
    console.print("╰─" + "─" * 63 + "╯\n")


def run_onboarding_flow() -> dict:
    """
    Run the onboarding Q&A flow. Returns dict of answers keyed by question key.
    Raises KeyboardInterrupt if user quits (Ctrl+C); caller should exit cleanly.
    """
    console.print(
        Panel(
            "Let me learn about you (takes ~2 minutes)\n"
            "You can update this anytime by running with --reset-memory",
            title="[bold #00D9FF]FIRST TIME SETUP[/bold #00D9FF]",
            title_align="left",
            border_style="#00D9FF",
            padding=(0, 2),
        )
    )
    console.print()

    answers = {}
    for i, item in enumerate(ONBOARDING_QUESTIONS, 1):
        key = item["key"]
        question = item["question"]
        prompt_line = Text()
        prompt_line.append(f"{i}. {question}\n", style="bold white")
        prompt_line.append("> ", style="bold #00D9FF")
        console.print(prompt_line, end="")
        try:
            value = input().strip()
        except EOFError:
            raise KeyboardInterrupt()
        answers[key] = value if value else "(not provided)"

    console.print()
    console.print(
        Panel(
            "Creating your memory profile...",
            title="[bold #00D9FF]GENERATING MEMORY[/bold #00D9FF]",
            title_align="left",
            border_style="#00D9FF",
            padding=(0, 2),
        )
    )
    return answers


def _is_qa_format(answers: dict) -> bool:
    """True if answers are in adaptive Q&A format: { q1: {question, answer}, ... }."""
    if not answers:
        return False
    first = next(iter(answers.values()), None)
    return isinstance(first, dict) and "question" in first and "answer" in first


def _template_fallback_memory(answers: dict) -> dict:
    """Build minimal memory content from answers when LLM generation fails."""
    if _is_qa_format(answers):
        qa_lines = []
        for v in answers.values():
            q = (v.get("question") or "").strip() or "(no question)"
            a = (v.get("answer") or "").strip() or "(not provided)"
            qa_lines.append(f"**Q:** {q}\n**A:** {a}")
        core = "# Core Memory\n\n" + "\n\n".join(qa_lines)
        personal = "# Personal\n\n" + "\n\n".join(qa_lines)
        work_md = "# Work\n\n" + "\n\n".join(qa_lines)
        current_focus_md = "# Current Focus\n\n" + "\n\n".join(qa_lines)
        preferences_md = "# Preferences\n\n" + "\n\n".join(qa_lines)
        return {
            "core_memory": core.strip(),
            "personal": personal.strip(),
            "work": work_md.strip(),
            "current_focus": current_focus_md.strip(),
            "preferences": preferences_md.strip(),
        }

    name = answers.get("name", "(not provided)")
    work = answers.get("work", "(not provided)")
    location = answers.get("location", "(not provided)")
    current_focus = answers.get("current_focus", "(not provided)")
    interests = answers.get("interests", "(not provided)")
    communication_style = answers.get("communication_style", "(not provided)")

    core = f"""# Core Memory

**Name:** {name}
**Work:** {work}
**Location:** {location}

**Current focus:** {current_focus}
**Interests / topics for help:** {interests}
**Communication preferences:** {communication_style}
"""
    personal = f"""# Personal

- **Name:** {name}
- **Location:** {location}
"""
    work_md = f"""# Work

- **Role / status:** {work}
"""
    current_focus_md = f"""# Current Focus

- **Focus:** {current_focus}
- **Topics for help:** {interests}
"""
    preferences_md = f"""# Preferences

- **Communication:** {communication_style}
"""
    return {
        "core_memory": core.strip(),
        "personal": personal.strip(),
        "work": work_md.strip(),
        "current_focus": current_focus_md.strip(),
        "preferences": preferences_md.strip(),
    }


def _extract_json_from_response(content: str) -> Optional[dict]:
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


def generate_initial_memory(answers: dict) -> dict:
    """
    Takes user answers, sends to LLM, returns dict of memory content.
    On LLM failure: retry once, then fall back to template-based memory.
    Accepts either legacy key->value dict or adaptive Q&A format { q1: {question, answer}, ... }.

    Returns:
        dict with keys: core_memory, personal, work, current_focus, preferences
    """
    if _is_qa_format(answers):
        answers_formatted = "\n\n".join(
            f"**Q:** {v.get('question', '')}\n**A:** {v.get('answer', '')}"
            for v in answers.values()
        )
    else:
        answers_formatted = "\n".join(f"- **{k}:** {v}" for k, v in answers.items())
    prompt = MEMORY_GENERATION_PROMPT.format(answers_formatted=answers_formatted)

    messages = [
        {"role": "system", "content": "You output only valid JSON. No markdown, no explanation."},
        {"role": "user", "content": prompt},
    ]

    for attempt in range(2):
        response = call_llm(messages, tools=None, stream=False)
        if not response:
            continue
        content = (response.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json_from_response(content)
        if parsed and "core_memory" in parsed:
            # Ensure all keys exist with string values
            result = {}
            for key in ("core_memory", "personal", "work", "current_focus", "preferences"):
                result[key] = (parsed.get(key) or "").strip() or "(empty)"
            return result

    # Fallback to template-based memory
    console.print("[dim]LLM generation failed; using template-based memory.[/dim]")
    return _template_fallback_memory(answers)


def write_initial_memory(memory_content: dict) -> bool:
    """
    Write generated memory to AI Memory folder structure.
    Returns True if all writes succeeded, False otherwise.
    """
    init_result = ensure_memory_structure()
    if not init_result.get("success"):
        console.print(f"[bold #FF10F0]Cannot write memory: {init_result.get('error', 'Unknown')}[/bold #FF10F0]")
        return False

    r1 = update_core_memory(memory_content.get("core_memory", ""))
    if not r1.get("success"):
        console.print(f"[bold #FF10F0]Failed to write core memory: {r1.get('error', 'Unknown')}[/bold #FF10F0]")
        return False

    for category, key in (
        ("personal", "personal"),
        ("work", "work"),
        ("current-focus", "current_focus"),
        ("preferences", "preferences"),
    ):
        r = update_context(category, memory_content.get(key, ""))
        if not r.get("success"):
            console.print(f"[bold #FF10F0]Failed to write {category}: {r.get('error', 'Unknown')}[/bold #FF10F0]")
            return False

    console.print("✓ Core memory created", style=STYLE_SUCCESS)
    console.print("✓ Personal context saved", style=STYLE_SUCCESS)
    console.print("✓ Work context saved", style=STYLE_SUCCESS)
    console.print("✓ Preferences saved", style=STYLE_SUCCESS)
    console.print("✓ Current focus documented", style=STYLE_SUCCESS)
    return True


def create_initial_memory_from_answers(answers: dict) -> bool:
    """
    Send answers to LLM to generate initial memory structure and write to disk.
    Answers format: { q1: {question, answer}, q2: {...}, ... } from adaptive Q&A.
    Returns True on success.
    """
    memory_content = generate_initial_memory(answers)
    return write_initial_memory(memory_content)


def update_memory_from_answers(answers: dict, existing_memory: dict) -> bool:
    """
    Merge new Q&A answers with existing memory via LLM, then write updated memory.
    Returns True if all writes succeeded.
    """
    existing_formatted = "\n\n".join(
        f"## {k}\n{v or '(empty)'}" for k, v in existing_memory.items()
    )
    answers_formatted = "\n\n".join(
        f"Q: {v.get('question', '')}\nA: {v.get('answer', '')}"
        for v in answers.values()
    )
    prompt = UPDATE_MEMORY_PROMPT.format(
        existing_memory_formatted=existing_formatted,
        answers_formatted=answers_formatted,
    )
    messages = [
        {"role": "system", "content": "You output only valid JSON. No markdown, no explanation."},
        {"role": "user", "content": prompt},
    ]

    for attempt in range(2):
        response = call_llm(messages, tools=None, stream=False)
        if not response:
            continue
        content = (response.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json_from_response(content)
        if not parsed or "core_memory" not in parsed:
            continue
        updated = {k: (parsed.get(k) or "").strip() for k in ("core_memory", "personal", "work", "current_focus", "preferences")}
        archived = (parsed.get("archived") or "").strip()

        init_result = ensure_memory_structure()
        if not init_result.get("success"):
            console.print(f"[bold #FF10F0]Cannot write memory: {init_result.get('error', 'Unknown')}[/bold #FF10F0]")
            return False

        r1 = update_core_memory(updated.get("core_memory", ""))
        if not r1.get("success"):
            console.print(f"[bold #FF10F0]Failed to write core memory: {r1.get('error', 'Unknown')}[/bold #FF10F0]")
            return False

        for category, key in (
            ("personal", "personal"),
            ("work", "work"),
            ("current-focus", "current_focus"),
            ("preferences", "preferences"),
        ):
            r = update_context(category, updated.get(key, ""))
            if not r.get("success"):
                console.print(f"[bold #FF10F0]Failed to write {category}: {r.get('error', 'Unknown')}[/bold #FF10F0]")
                return False

        if archived:
            archive_memory(archived)

        return True

    console.print("[bold #FF10F0]LLM failed to produce valid memory update; no changes written.[/bold #FF10F0]")
    return False


def get_user_input() -> str:
    """Get user input with styled prompt"""
    console.print()
    prompt = Text()
    prompt.append("> ", style="bold #00D9FF")
    console.print(prompt, end="")
    return input().strip()


def display_response(content: str):
    """Display assistant response as rendered markdown"""
    if content:
        console.print()
        console.print(Markdown(content))


# Tools used only for end-of-session consolidation (no search, no generic notes)
CONSOLIDATION_TOOLS = [
    READ_CORE_MEMORY_TOOL,
    UPDATE_CORE_MEMORY_TOOL,
    READ_CONTEXT_TOOL,
    UPDATE_CONTEXT_TOOL,
    READ_SPECIFIC_CONTEXT_TOOL,
    UPDATE_SPECIFIC_CONTEXT_TOOL,
    ADD_GOAL_TOOL,
    ARCHIVE_MEMORY_TOOL,
]


def get_llm_response_simple(messages: list, system_message: str, extra_user_message: Optional[str] = None) -> Optional[str]:
    """Get a single LLM reply (no tools, no streaming). Used for exploratory conversation turns."""
    msgs = [{"role": "system", "content": system_message}]
    msgs.extend(messages)
    if extra_user_message:
        msgs.append({"role": "user", "content": extra_user_message})
    response = call_llm(msgs, tools=None, stream=False)
    if not response:
        return None
    return (response.get("choices") or [{}])[0].get("message", {}).get("content") or ""


def run_exploratory_conversation() -> list:
    """Conduct multi-turn exploratory conversation. Returns list of messages (role, content)."""
    console.print("\n╭─ EXPLORATORY CONVERSATION ─" + "─" * 40 + "╮")
    console.print("│ Let's have a real conversation so I can understand you.    │")
    console.print("│ Talk as much or as little as you want.                   │")
    console.print("│ Type 'done' when ready to wrap up.                         │")
    console.print("╰─" + "─" * 68 + "╯\n")

    conversation = []
    ai_opening = "So tell me about yourself - what's going on in your life right now?"
    console.print(f"\n{ai_opening}\n", style="cyan")
    conversation.append({"role": "assistant", "content": ai_opening})

    while True:
        try:
            user_input = Prompt.ask(">")
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.lower().strip() == "done":
            farewell = get_llm_response_simple(
                conversation,
                EXPLORATION_PROMPT,
                extra_user_message="The user said they're done. Thank them and ask if there's anything else important before you wrap up.",
            )
            if farewell:
                console.print(f"\n{farewell}\n", style="cyan")
                conversation.append({"role": "assistant", "content": farewell})
            else:
                console.print("\nThanks for sharing all that. Anything else important before we wrap up?\n", style="cyan")
                conversation.append({"role": "assistant", "content": "Thanks for sharing all that. Anything else important before we wrap up?"})

            try:
                final_input = Prompt.ask(">")
            except (EOFError, KeyboardInterrupt):
                final_input = ""
            if final_input.lower().strip() not in ("no", "nope", "done", "nothing", ""):
                conversation.append({"role": "user", "content": final_input})
            break

        conversation.append({"role": "user", "content": user_input})
        response = get_llm_response_simple(conversation, EXPLORATION_PROMPT)
        if not response:
            response = "Tell me more about that."
        console.print(f"\n{response}\n", style="cyan")
        conversation.append({"role": "assistant", "content": response})

    return conversation


def _format_conversation_for_extraction(conversation: list) -> str:
    """Format conversation messages as transcript for extraction prompt."""
    lines = []
    for m in conversation:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n\n".join(lines)


def extract_memory_from_conversation(conversation: list) -> Optional[dict]:
    """Send conversation to LLM for structured memory extraction. Returns parsed JSON dict or None."""
    transcript = _format_conversation_for_extraction(conversation)
    prompt = MEMORY_EXTRACTION_PROMPT.format(conversation_transcript=transcript)
    messages = [
        {"role": "system", "content": "You output only valid JSON. No markdown code blocks, no explanation."},
        {"role": "user", "content": prompt},
    ]
    # Extraction output can be large (core + many context/timeline files); need enough tokens
    for attempt in range(2):
        response = call_llm(messages, tools=None, stream=False, max_tokens=8192)
        if not response:
            continue
        raw = (response.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json_from_response(raw)
        if not parsed:
            continue
        if "core_memory" in parsed:
            return parsed
    return None


def write_organized_memory(memory_structure: dict) -> bool:
    """Write extracted memory to disk and print success panel. Returns True on success."""
    result = memory_write_organized(memory_structure)
    if not result.get("success"):
        console.print(f"[bold #FF10F0]Failed to write memory: {result.get('error', 'Unknown')}[/bold #FF10F0]")
        return False

    created_context = [k for k, v in (memory_structure.get("context") or {}).items() if v]
    created_timelines = [k for k, v in (memory_structure.get("timelines") or {}).items() if v]

    console.print("\n╭─ MEMORY CREATED ─" + "─" * 50 + "╮", style="green")
    console.print("│ ✓ Core memory created" + " " * 45 + "│")
    n_ctx = len(created_context)
    console.print(f"│ ✓ Created {n_ctx} context files" + " " * max(0, 44 - len(str(n_ctx))) + "│")
    if created_timelines:
        n_tl = len(created_timelines)
        console.print(f"│ ✓ Created {n_tl} timeline files" + " " * max(0, 41 - len(str(n_tl))) + "│")
    console.print("╰─" + "─" * 68 + "╯\n")
    return True


def run_consolidation(messages: list) -> None:
    """Run memory consolidation: ask the model to update core/context/archive from the conversation."""
    core_content = read_core_memory()
    # Build conversation summary (last N messages) for context
    last_n = 20
    non_system = [m for m in messages if m.get("role") != "system"]
    recent = non_system[-last_n:] if len(non_system) > last_n else non_system
    conv_summary = []
    for m in recent:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if not content and m.get("tool_calls"):
            content = "[model used tools]"
        if content:
            conv_summary.append(f"{role}: {content[:200]}{'...' if len(content) > 200 else ''}")
    conversation_snippet = "\n".join(conv_summary) if conv_summary else "(no messages)"

    consolidation_system = """The conversation is ending. Your only job is to consolidate memory. Do not chat or say goodbye.

1. Review the current core memory below.
2. Summarize what was important in this conversation.
3. Update core memory with new information if needed (keep under """ + str(CORE_MEMORY_MAX_TOKENS) + """ tokens). Remove or compress outdated items.
4. Move information that is stable but not needed in core to the appropriate context file. Use update_context for flat categories (personal, work, preferences, current-focus). If the user has hierarchical memory (context/work/, context/life/, etc.), use update_specific_context(category, subcategory, content) to update the right file (e.g. work/projects, life/finances). Use add_goal for new goals with timelines.
5. Optionally archive a short conversation summary or outdated details using archive_memory.

Use the tools: read_core_memory, update_core_memory, read_context, update_context, read_specific_context, update_specific_context, add_goal, archive_memory. Call the tools you need, then stop."""

    user_consolidation_msg = f"""Please consolidate memory.

Current core memory:
---
{core_content or '(empty)'}
---

Conversation context (recent messages):
---
{conversation_snippet}
---"""

    consolidation_messages = [
        {"role": "system", "content": consolidation_system},
        {"role": "user", "content": user_consolidation_msg},
    ]
    console.print(Text("Consolidating memory...", style=STYLE_THINKING))
    response = call_llm(consolidation_messages, tools=CONSOLIDATION_TOOLS, stream=False)
    if not response:
        return
    message = response["choices"][0]["message"]
    tool_calls_raw = message.get("tool_calls") or []
    for i, tool_call in enumerate(tool_calls_raw):
        func_name = tool_call["function"]["name"]
        args = parse_tool_arguments(tool_call)
        console.print()
        display_tool_call(func_name, args)
        result = execute_tool(func_name, args)
        display_tool_result(result)


def main():
    args = parse_args()

    if args.reset_memory:
        if not _confirm_reset():
            console.print("Cancelled.")
            return
        result = delete_ai_memory_folder()
        if not result.get("success"):
            console.print(f"[bold #FF10F0]Error: {result.get('error', 'Unknown')}[/bold #FF10F0]")
            return
        run_memory_initialization()
        return

    if args.refresh_memory:
        run_memory_initialization()
        return

    if args.explore:
        conversation = run_exploratory_conversation()
        if not conversation:
            console.print("No conversation to process.")
            return
        console.print("\n╭─ PROCESSING CONVERSATION ─" + "─" * 40 + "╮")
        console.print("│ Extracting insights and organizing memory...             │")
        console.print("╰─" + "─" * 68 + "╯\n")
        memory_structure = extract_memory_from_conversation(conversation)
        if memory_structure:
            init_result = ensure_memory_structure()
            if init_result.get("success") and write_organized_memory(memory_structure):
                console.print("Your memory is ready! Let's chat.\n", style="green")
            else:
                console.print("[bold #FF10F0]Memory extraction failed or could not write.[/bold #FF10F0]")
        else:
            console.print("[bold #FF10F0]Could not extract memory from conversation. Try again or use --refresh-memory.[/bold #FF10F0]")
            return

    if not memory_exists():
        run_memory_initialization()

    display_welcome()

    init_result = ensure_memory_structure()
    if not init_result.get("success"):
        console.print(f"[bold #FF10F0]Memory init warning: {init_result.get('error', 'Unknown')}[/bold #FF10F0]")

    core_section = read_core_memory()
    if core_section:
        system_content = SYSTEM_PROMPT + "\n\n## Core memory (current)\n\n" + core_section
    else:
        system_content = SYSTEM_PROMPT + "\n\n## Core memory (current)\n\n(Empty. Use update_core_memory when you learn something about the user.)"

    messages = [{"role": "system", "content": system_content}]
    tools = [
        READ_CORE_MEMORY_TOOL,
        UPDATE_CORE_MEMORY_TOOL,
        READ_CONTEXT_TOOL,
        UPDATE_CONTEXT_TOOL,
        ARCHIVE_MEMORY_TOOL,
        READ_SPECIFIC_CONTEXT_TOOL,
        UPDATE_SPECIFIC_CONTEXT_TOOL,
        ADD_GOAL_TOOL,
        SEARCH_VAULT_TOOL,
        CREATE_MEMORY_NOTE_TOOL,
        READ_MEMORY_NOTE_TOOL,
        UPDATE_MEMORY_NOTE_TOOL,
        APPEND_TO_MEMORY_NOTE_TOOL,
        LIST_MEMORY_NOTES_TOOL,
        DELETE_MEMORY_NOTE_TOOL,
    ]

    while True:
        user_input = get_user_input()

        if user_input.lower() in ['quit', 'exit']:
            console.print()
            run_consolidation(messages)
            goodbye = Text("Goodbye!", style="bold #FF10F0")
            console.print(goodbye)
            break

        if not user_input:
            continue

        # On the first turn, put core memory in the user message too so it stays in context
        # even if the backend merges/replaces the system prompt when tools are present.
        if len(messages) == 1:
            core_block = (
                "## Core memory (current)\n\n" + core_section + "\n\n---\n\nUser request: "
                if core_section
                else "User request: "
            )
            user_content = core_block + user_input
        else:
            user_content = user_input
        messages.append({"role": "user", "content": user_content})

        # Agentic loop - continue until model stops calling tools
        iteration = 0
        while True:
            iteration += 1

            # Only stream on the first iteration (to show thinking in real-time)
            use_streaming = (iteration == 1)

            if iteration == 1:
                console.print()
                # Use Live for streaming response
                with Live(Markdown(""), console=console, refresh_per_second=15, transient=False) as live:
                    response = call_llm(messages, tools=tools, stream=use_streaming, live_display=live)
            else:
                response = call_llm(messages, tools=tools, stream=False)

            if not response:
                console.print("[bold #FF10F0]Failed to get response from LLM[/bold #FF10F0]")
                break

            message = response["choices"][0]["message"]
            tool_calls_raw = message.get("tool_calls")

            # If there are tool calls, execute them and loop
            if tool_calls_raw:
                # Add assistant message with tool calls to history
                messages.append({
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls_raw
                })

                # Execute each tool and add results to history
                for i, tool_call in enumerate(tool_calls_raw):
                    func_name = tool_call["function"]["name"]
                    args = parse_tool_arguments(tool_call)
                    tool_call_id = tool_call.get("id", f"call_{i}")

                    console.print()
                    display_tool_call(func_name, args)

                    # Execute tool
                    result = execute_tool(func_name, args)

                    display_tool_result(result)

                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": func_name,
                        "content": result
                    })

                # Model will think again with the tool results
                console.print()
                display_thinking()

            else:
                # No tool calls - this is the final response
                content = message.get("content", "")

                if iteration > 1 and content:
                    # Display the response we already received (don't re-call LLM)
                    console.print()
                    console.print(content)

                # Add final assistant response to message history
                assistant_text = content
                if assistant_text:
                    messages.append({"role": "assistant", "content": assistant_text})

                break  # Exit agentic loop


if __name__ == "__main__":
    main()
