# memory.py — Hierarchical memory (core / context / archive)
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()

MEMORY_FOLDER = "AI Memory"
CORE_MEMORY_FILE = "core-memory.md"
CONTEXT_FOLDER = "context"
TIMELINES_FOLDER = "timelines"
ARCHIVE_FOLDER = "archive"
ARCHIVE_CONVERSATIONS_FILE = "conversations.md"
ARCHIVE_COMPLETED_GOALS_FILE = "completed-goals.md"

# Allowed context categories (file names under context/)
CONTEXT_CATEGORIES = ("personal", "work", "preferences", "current-focus")

# Max tokens for core memory (~500)
CORE_MEMORY_MAX_TOKENS = 500

# Rough token estimate: ~4 chars per token
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token count (~4 characters per token)."""
    if not text:
        return 0
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def _get_vault_path() -> Optional[Path]:
    """Get vault path from environment. Returns None if missing or invalid."""
    vault_path = os.getenv("OBSIDIAN_PATH")
    if not vault_path:
        return None
    vault_path = Path(vault_path)
    if not vault_path.exists() or not vault_path.is_dir():
        return None
    return vault_path


def _memory_root() -> Optional[Path]:
    """Return AI Memory folder path, or None if vault not configured."""
    vault = _get_vault_path()
    if not vault:
        return None
    return vault / MEMORY_FOLDER


def memory_exists() -> bool:
    """Return True if core-memory.md exists (memory has been initialized)."""
    root = _memory_root()
    if not root:
        return False
    return (root / CORE_MEMORY_FILE).exists()


def delete_ai_memory_folder() -> Dict:
    """
    Delete the entire AI Memory folder and its contents.
    Used when --reset-memory is requested. Returns dict with 'success' and optional 'error'.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}
    if not root.exists():
        return {"success": True}
    try:
        shutil.rmtree(root)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def ensure_memory_structure() -> Dict:
    """
    Create AI Memory folder structure and default files if missing.
    Returns dict with 'success' and optional 'error'.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    try:
        root.mkdir(parents=True, exist_ok=True)

        # Core memory (empty or minimal if new)
        core_path = root / CORE_MEMORY_FILE
        if not core_path.exists():
            core_path.write_text(
                "# Core Memory\n\n<!-- Working memory, ~500 tokens max. Most recent, relevant information. -->\n",
                encoding="utf-8",
            )

        # Context folder and category files
        context_dir = root / CONTEXT_FOLDER
        context_dir.mkdir(parents=True, exist_ok=True)
        for cat in CONTEXT_CATEGORIES:
            p = context_dir / f"{cat}.md"
            if not p.exists():
                p.write_text(f"# {cat.replace('-', ' ').title()}\n\n", encoding="utf-8")

        # Archive folder (no files until first archive)
        (root / ARCHIVE_FOLDER).mkdir(parents=True, exist_ok=True)

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_core_memory() -> str:
    """Load core-memory.md content. Returns empty string if missing or on error."""
    root = _memory_root()
    if not root:
        return ""
    path = root / CORE_MEMORY_FILE
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def update_core_memory(content: str) -> Dict:
    """
    Rewrite core-memory.md. Content must be under CORE_MEMORY_MAX_TOKENS.
    Returns dict with 'success', optional 'error', and optional 'tokens'.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    if content is None:
        content = ""
    content = str(content)

    tokens = estimate_tokens(content)
    if tokens > CORE_MEMORY_MAX_TOKENS:
        return {
            "success": False,
            "error": f"Core memory exceeds limit: {tokens} tokens (max {CORE_MEMORY_MAX_TOKENS})",
            "tokens": tokens,
        }

    path = root / CORE_MEMORY_FILE
    try:
        ensure_memory_structure()
        path.write_text(content, encoding="utf-8")
        return {"success": True, "tokens": tokens}
    except Exception as e:
        return {"success": False, "error": str(e), "tokens": tokens}


def read_context(category: str) -> str:
    """
    Load a context file. Category must be one of: personal, work, preferences, current-focus.
    Returns empty string if invalid or on error.
    """
    category = (category or "").strip().lower()
    if category not in CONTEXT_CATEGORIES:
        return ""

    root = _memory_root()
    if not root:
        return ""
    path = root / CONTEXT_FOLDER / f"{category}.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def update_context(category: str, content: str) -> Dict:
    """
    Update a context file. Category must be one of: personal, work, preferences, current-focus.
    Returns dict with 'success' and optional 'error'.
    """
    category = (category or "").strip().lower()
    if category not in CONTEXT_CATEGORIES:
        return {"success": False, "error": f"Invalid category. Use one of: {', '.join(CONTEXT_CATEGORIES)}"}

    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    path = root / CONTEXT_FOLDER / f"{category}.md"
    try:
        ensure_memory_structure()
        path.write_text(content, encoding="utf-8")
        return {"success": True, "filepath": f"{CONTEXT_FOLDER}/{category}.md"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def archive_memory(content: str, date: Optional[str] = None) -> Dict:
    """
    Append content to archive for a given month. Date format YYYY-MM; default is current month.
    Returns dict with 'success', optional 'error', and optional 'filepath'.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    if date:
        date = date.strip()
        if len(date) != 7 or date[4] != "-":
            return {"success": False, "error": "date must be YYYY-MM"}
    else:
        date = datetime.now().strftime("%Y-%m")

    archive_dir = root / ARCHIVE_FOLDER / date
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / ARCHIVE_CONVERSATIONS_FILE

    try:
        sep = "\n\n---\n\n" if path.exists() and path.read_text(encoding="utf-8").strip() else ""
        with open(path, "a", encoding="utf-8") as f:
            f.write(sep + content.strip())
        return {"success": True, "filepath": f"{ARCHIVE_FOLDER}/{date}/{ARCHIVE_CONVERSATIONS_FILE}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _read_file_safe(path: Path) -> str:
    """Read file content; return empty string if missing or on error."""
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def write_organized_memory(memory_structure: Dict) -> Dict:
    """
    Write memory from exploration extraction. Creates subdirs as needed.
    memory_structure: { core_memory, context: { "path/key": "markdown" }, timelines: { "current-goals": "..." } }
    Returns dict with 'success' and optional 'error'.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    try:
        root.mkdir(parents=True, exist_ok=True)

        core_content = (memory_structure.get("core_memory") or "").strip()
        if core_content:
            core_path = root / CORE_MEMORY_FILE
            core_path.write_text(core_content, encoding="utf-8")

        context_dir = root / CONTEXT_FOLDER
        context_data = memory_structure.get("context") or {}
        for file_key, content in context_data.items():
            content = (content if isinstance(content, str) else "") or ""
            content = content.strip()
            if not content:
                continue
            # file_key may be "personal", "work/current-role", "life/finances", etc.
            full_path = context_dir / f"{file_key}.md"
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

        timelines_dir = root / TIMELINES_FOLDER
        timelines_data = memory_structure.get("timelines") or {}
        for file_name, content in timelines_data.items():
            content = (content if isinstance(content, str) else "") or ""
            content = content.strip()
            if not content:
                continue
            timelines_dir.mkdir(parents=True, exist_ok=True)
            (timelines_dir / f"{file_name}.md").write_text(content, encoding="utf-8")

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_specific_context(category: str, subcategory: Optional[str] = None) -> str:
    """
    Read a specific context file or all files in a category.
    Examples:
      read_specific_context("work", "projects") -> context/work/projects.md
      read_specific_context("interests") -> concatenation of context/interests/*.md
    """
    root = _memory_root()
    if not root:
        return ""
    context_dir = root / CONTEXT_FOLDER
    if not context_dir.exists():
        return ""

    category = (category or "").strip().lower()
    if not category:
        return ""

    if subcategory:
        subcategory = (subcategory or "").strip().lower()
        path = context_dir / category / f"{subcategory}.md"
        if path.exists():
            return _read_file_safe(path)
        return ""

    # No subcategory: return all .md under context/category/
    parts_dir = context_dir / category
    if not parts_dir.exists() or not parts_dir.is_dir():
        # Single file context/category.md (legacy)
        single = context_dir / f"{category}.md"
        if single.exists():
            return _read_file_safe(single)
        return ""

    bits = []
    for md_file in sorted(parts_dir.glob("*.md")):
        bits.append(f"## {md_file.stem}\n\n{_read_file_safe(md_file)}")
    return "\n\n".join(bits) if bits else ""


def update_specific_context(category: str, subcategory: str, content: str) -> Dict:
    """
    Update a specific context file (e.g. work/projects, life/finances).
    Creates parent dirs if needed.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    category = (category or "").strip().lower()
    subcategory = (subcategory or "").strip().lower()
    if not category or not subcategory:
        return {"success": False, "error": "category and subcategory are required"}

    path = root / CONTEXT_FOLDER / category / f"{subcategory}.md"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((content or "").strip(), encoding="utf-8")
        rel = path.relative_to(root)
        return {"success": True, "filepath": str(rel)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def add_goal(goal_description: str, timeline: str, goal_type: str = "current") -> Dict:
    """
    Add a goal to the appropriate timeline file.
    goal_type: "current" -> timelines/current-goals.md, "future" -> timelines/future-plans.md.
    Appends a new line/section; does not overwrite.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    goal_description = (goal_description or "").strip()
    timeline = (timeline or "").strip()
    if not goal_description:
        return {"success": False, "error": "goal_description is required"}

    goal_type = (goal_type or "current").strip().lower()
    if goal_type not in ("current", "future"):
        goal_type = "current"
    filename = "current-goals.md" if goal_type == "current" else "future-plans.md"
    path = root / TIMELINES_FOLDER / filename
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = f"\n\n- **Goal:** {goal_description}\n- **Timeline:** {timeline}\n"
        if path.exists():
            path.write_text(path.read_text(encoding="utf-8").rstrip() + entry, encoding="utf-8")
        else:
            path.write_text(f"# {'Current goals' if goal_type == 'current' else 'Future plans'}\n" + entry.strip(), encoding="utf-8")
        return {"success": True, "filepath": f"{TIMELINES_FOLDER}/{filename}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def load_all_memory() -> Dict:
    """
    Load all memory content. Supports both legacy flat structure and hierarchical.
    Returns:
      - core_memory: str
      - context: dict mapping path (e.g. "personal", "work/current-role") to content
      - timelines: dict mapping file stem (e.g. "current-goals") to content
    For legacy flat structure, context has keys personal, work, current-focus, preferences.
    """
    root = _memory_root()
    out = {
        "core_memory": read_core_memory(),
        "context": {},
        "timelines": {},
    }
    if not root:
        return out

    context_dir = root / CONTEXT_FOLDER
    if context_dir.exists():
        for md_file in context_dir.rglob("*.md"):
            try:
                rel = md_file.relative_to(context_dir).with_suffix("")
                key = str(rel).replace("\\", "/")
                out["context"][key] = _read_file_safe(md_file)
            except Exception:
                pass

    timelines_dir = root / TIMELINES_FOLDER
    if timelines_dir.exists():
        for md_file in timelines_dir.glob("*.md"):
            out["timelines"][md_file.stem] = _read_file_safe(md_file)

    # Backward compat for callers expecting flat keys (e.g. refresh flow)
    ctx = out["context"]
    out["personal"] = ctx.get("personal", "")
    out["work"] = ctx.get("work", "") or "\n\n".join(
        f"## {k}\n{v}" for k, v in ctx.items() if k.startswith("work/") and v
    )
    out["current_focus"] = ctx.get("current-focus", "") or out["timelines"].get("current-goals", "")
    out["preferences"] = ctx.get("preferences", "")

    return out


def get_memory_stats() -> Dict:
    """
    Return token counts for core memory and each context file.
    Keys: core_tokens, core_chars, context_tokens (dict by category), context_chars (dict).
    """
    root = _memory_root()
    out = {
        "core_tokens": 0,
        "core_chars": 0,
        "context_tokens": {},
        "context_chars": {},
    }
    if not root:
        return out

    core_path = root / CORE_MEMORY_FILE
    if core_path.exists():
        try:
            text = core_path.read_text(encoding="utf-8")
            out["core_chars"] = len(text)
            out["core_tokens"] = estimate_tokens(text)
        except Exception:
            pass

    for cat in CONTEXT_CATEGORIES:
        path = root / CONTEXT_FOLDER / f"{cat}.md"
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                out["context_chars"][cat] = len(text)
                out["context_tokens"][cat] = estimate_tokens(text)
            except Exception:
                out["context_chars"][cat] = 0
                out["context_tokens"][cat] = 0
        else:
            out["context_chars"][cat] = 0
            out["context_tokens"][cat] = 0

    return out
