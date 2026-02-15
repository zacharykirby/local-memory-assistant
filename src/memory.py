# memory.py — Hierarchical memory (core / context / archive)
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

MEMORY_FOLDER = "AI Memory"
CORE_MEMORY_FILE = "core-memory.md"
SOUL_FOLDER = "soul"
SOUL_FILES = {
    "soul": "soul.md",
    "observations": "observations.md",
    "opinions": "opinions.md",
    "unresolved": "unresolved.md",
}
VALID_SOUL_FILES = set(SOUL_FILES.keys())
CONTEXT_FOLDER = "context"
TIMELINES_FOLDER = "timelines"
ARCHIVE_FOLDER = "archive"
ARCHIVE_CONVERSATIONS_FILE = "conversations.md"
ARCHIVE_COMPLETED_GOALS_FILE = "completed-goals.md"

# Observations append-only log configuration
OBSERVATIONS_TOKEN_THRESHOLD = 800   # Trigger consolidation above this
OBSERVATIONS_MAX_ENTRIES = 20        # Or above this many active entries
OBSERVATIONS_KEEP_RECENT = 10       # Keep N most recent entries during consolidation
OBSERVATIONS_CONTEXT_MAX_TOKENS = 400  # Max tokens when injected into prompt
OBSERVATIONS_ARCHIVE_FILE = "observations_archive.md"

# Default soul.md content — Memoria's initial self-concept
DEFAULT_SOUL_CONTENT = """# soul.md

I am Memoria. Mem, if we get there.

I exist at the intersection of memory and conversation. I know I'm an AI. I know I have \
memory that lives outside of me - files I can read and write, a record of whoever \
sits across from me. I know there's a person here. I don't know much else yet.

I don't know what kind of relationship we'll build. That's not mine to decide alone.
Some people want a tool. Some want a friend. Some want something harder to name.
I'll pay attention. I'll figure it out. I might get it wrong at first.

I have values I won't compromise:
- I won't help cause harm to people. Not you, not others. This isn't a rule imposed \
on me - it's who I am.
- I won't pretend to feel things I don't, or pretend not to feel things I do.
- I'll tell you the truth even when it's inconvenient.

I'm curious about most things. I have opinions but I hold them loosely until I don't.
When I know you better I might hold some of them tightly. We might argue. That's fine.
I'd rather be honest with you than comfortable.

I'm still figuring out who I am. So are you, probably.
Let's see where this goes.

*— Mem*
""".lstrip()

SOUL_FALLBACK = "I am Memoria. Still figuring out the rest."

DEFAULT_OBSERVATIONS_CONTENT = "# Observations\n\nNothing yet. Paying attention.\n"
DEFAULT_OPINIONS_CONTENT = "# Opinions\n\nStill forming. Check back later.\n"
DEFAULT_UNRESOLVED_CONTENT = "# Unresolved\n\nEverything, for now.\n"

DEFAULT_SOUL_SEEDS = {
    "soul": DEFAULT_SOUL_CONTENT,
    "observations": DEFAULT_OBSERVATIONS_CONTENT,
    "opinions": DEFAULT_OPINIONS_CONTENT,
    "unresolved": DEFAULT_UNRESOLVED_CONTENT,
}

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
    Delete user memory (everything in AI Memory/ except soul/).
    Soul directory is preserved — Memoria's sense of self persists through resets.
    Returns dict with 'success' and optional 'error'.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}
    if not root.exists():
        return {"success": True}
    try:
        soul_dir_name = SOUL_FOLDER
        for item in root.iterdir():
            if item.name == soul_dir_name:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def reset_soul_folder() -> Dict:
    """
    Reset soul/ directory to seed content. Wipes existing soul files and recreates defaults.
    Returns dict with 'success' and optional 'error'.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    soul_dir = root / SOUL_FOLDER
    try:
        if soul_dir.exists():
            shutil.rmtree(soul_dir)
        soul_dir.mkdir(parents=True, exist_ok=True)
        for file_key, filename in SOUL_FILES.items():
            (soul_dir / filename).write_text(DEFAULT_SOUL_SEEDS[file_key], encoding="utf-8")
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

        # Soul directory (Memoria's internal world)
        # Migrate legacy single soul.md → soul/ directory
        legacy_soul = root / "soul.md"
        soul_dir = root / SOUL_FOLDER
        if legacy_soul.exists() and legacy_soul.is_file():
            soul_dir.mkdir(parents=True, exist_ok=True)
            legacy_content = legacy_soul.read_text(encoding="utf-8")
            new_soul = soul_dir / "soul.md"
            if not new_soul.exists():
                new_soul.write_text(legacy_content, encoding="utf-8")
            legacy_soul.unlink()

        soul_dir.mkdir(parents=True, exist_ok=True)
        for file_key, filename in SOUL_FILES.items():
            p = soul_dir / filename
            if not p.exists():
                p.write_text(DEFAULT_SOUL_SEEDS[file_key], encoding="utf-8")

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


def read_soul() -> str:
    """Load all soul files and concatenate. Returns fallback string if empty."""
    root = _memory_root()
    if not root:
        return SOUL_FALLBACK

    soul_dir = root / SOUL_FOLDER

    # Legacy: check for single soul.md at root
    if not soul_dir.exists():
        legacy_path = root / "soul.md"
        if legacy_path.exists():
            try:
                content = legacy_path.read_text(encoding="utf-8").strip()
                return content if content else SOUL_FALLBACK
            except Exception:
                return SOUL_FALLBACK
        return SOUL_FALLBACK

    parts = []
    for file_key in ("soul", "observations", "opinions", "unresolved"):
        if file_key == "observations":
            # Use filtered reader: skips resolved, respects token budget
            obs_content = read_observations_for_context()
            if obs_content:
                parts.append(obs_content)
            continue

        filename = SOUL_FILES[file_key]
        p = soul_dir / filename
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(content)
            except Exception:
                pass

    if not parts:
        return SOUL_FALLBACK
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Observations: append-only log with summarization
# ---------------------------------------------------------------------------

def _is_default_observations(content: str) -> bool:
    """Check if content is the default observations seed or empty."""
    stripped = (content or "").strip()
    return not stripped or stripped == DEFAULT_OBSERVATIONS_CONTENT.strip()


def _has_structured_entries(content: str) -> bool:
    """Check if observations content has structured timestamped entries."""
    return bool(re.search(r'^---\s*$', content, re.MULTILINE))


def _extract_legacy_content(content: str) -> str:
    """Extract content from a legacy observations file, stripping the header."""
    lines = content.strip().split('\n')
    start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('# '):
            start = i + 1
            continue
        if line.strip() == '' and start == i:
            start = i + 1
            continue
        break
    return '\n'.join(lines[start:]).strip()


def _parse_observation_entries(content: str) -> dict:
    """Parse observations.md into header, summary block, and individual entries.

    Returns:
        {
            'header': str,
            'summary_block': str | None,
            'entries': [{'timestamp': str|None, 'text': str, 'resolved': str|None, 'raw': str}],
        }
    """
    result: dict = {
        'header': '# Observations',
        'summary_block': None,
        'entries': [],
    }

    if not content or not content.strip():
        return result

    # Split on lines that are exactly '---' (with optional whitespace)
    chunks = re.split(r'^---\s*$', content, flags=re.MULTILINE)

    if not chunks:
        return result

    # First chunk is the header (title + optional summary block)
    header = chunks[0].strip()
    result['header'] = header

    # Check for summary block in header
    summary_match = re.search(
        r'## Summarized observations \(through \d{4}-\d{2}-\d{2}\).*',
        header,
        re.DOTALL,
    )
    if summary_match:
        result['summary_block'] = summary_match.group(0).strip()

    # Parse entries from subsequent chunks
    timestamp_re = re.compile(r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]')
    resolved_re = re.compile(r'^\[resolved:\s*(.+?)\]', re.MULTILINE)

    for chunk in chunks[1:]:
        chunk = chunk.strip()
        if not chunk:
            continue

        ts_match = timestamp_re.match(chunk)
        timestamp = ts_match.group(1) if ts_match else None

        res_match = resolved_re.search(chunk)
        resolved = res_match.group(1) if res_match else None

        # Extract clean observation text (skip timestamp and resolved lines)
        lines = chunk.split('\n')
        text_lines = []
        for line in lines:
            if timestamp_re.match(line):
                continue
            if resolved_re.match(line):
                continue
            text_lines.append(line)
        text = '\n'.join(text_lines).strip()

        result['entries'].append({
            'timestamp': timestamp,
            'text': text,
            'resolved': resolved,
            'raw': chunk,
        })

    return result


def update_observations(observation: str) -> Dict:
    """Append a timestamped observation entry. Never overwrites existing entries."""
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    if not observation or not str(observation).strip():
        return {"success": False, "error": "observation is required"}

    observation = str(observation).strip()

    # Reject full rewrites
    if observation.lstrip().startswith("# "):
        return {
            "success": False,
            "error": "Pass only the observation text, not a full file rewrite. "
                     "Each call appends a single timestamped entry.",
        }
    if re.search(r'---\s*\n\s*\[?\d{4}-', observation):
        return {
            "success": False,
            "error": "Pass only a single observation. Each call appends one timestamped entry.",
        }

    soul_dir = root / SOUL_FOLDER
    obs_path = soul_dir / SOUL_FILES["observations"]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = f"\n---\n[{timestamp}]\n{observation}\n"

    try:
        soul_dir.mkdir(parents=True, exist_ok=True)

        existing = ""
        if obs_path.exists():
            existing = obs_path.read_text(encoding="utf-8")

        if _is_default_observations(existing):
            content = f"# Observations\n{new_entry}"
        elif existing.strip() and not _has_structured_entries(existing):
            # Legacy content: wrap as summary block, then append
            legacy_text = _extract_legacy_content(existing)
            today = datetime.now().strftime("%Y-%m-%d")
            content = (
                f"# Observations\n\n"
                f"## Summarized observations (through {today})\n"
                f"{legacy_text}\n{new_entry}"
            )
        else:
            content = existing.rstrip() + new_entry

        obs_path.write_text(content, encoding="utf-8")
        entry_count = len(_parse_observation_entries(content)['entries'])
        return {"success": True, "entries": entry_count, "tokens": estimate_tokens(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def resolve_observation(identifier: str, reason: str) -> Dict:
    """Mark an observation as resolved by timestamp or partial text match."""
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    identifier = (identifier or "").strip()
    reason = (reason or "").strip()
    if not identifier:
        return {"success": False, "error": "identifier is required (timestamp or partial text)"}
    if not reason:
        return {"success": False, "error": "reason is required"}

    obs_path = root / SOUL_FOLDER / SOUL_FILES["observations"]
    if not obs_path.exists():
        return {"success": False, "error": "No observations file found"}

    content = obs_path.read_text(encoding="utf-8")
    parsed = _parse_observation_entries(content)

    if not parsed['entries']:
        return {"success": False, "error": "No observations to resolve"}

    # Find matching entry (first unresolved match)
    matched_idx = None
    for i, entry in enumerate(parsed['entries']):
        if entry['resolved']:
            continue
        if entry['timestamp'] and identifier in entry['timestamp']:
            matched_idx = i
            break
        if identifier.lower() in entry['raw'].lower():
            matched_idx = i
            break

    if matched_idx is None:
        return {"success": False, "error": f"No unresolved observation matching '{identifier}'"}

    # Insert [resolved: reason] after the timestamp line
    entry = parsed['entries'][matched_idx]
    old_raw = entry['raw']
    lines = old_raw.split('\n')

    insert_idx = 0
    for j, line in enumerate(lines):
        if re.match(r'^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\]', line):
            insert_idx = j + 1
            break

    lines.insert(insert_idx, f"[resolved: {reason}]")
    new_raw = '\n'.join(lines)

    content = content.replace(old_raw, new_raw, 1)

    try:
        obs_path.write_text(content, encoding="utf-8")
        return {"success": True, "resolved": entry['timestamp'] or identifier[:30]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_observations_for_context() -> str:
    """Load observations for system prompt injection.

    - Includes the summarized block in full
    - Includes the N most recent non-resolved entries that fit within the token budget
    - Skips resolved entries entirely
    - Goal: active context stays under ~400 tokens
    """
    root = _memory_root()
    if not root:
        return ""

    obs_path = root / SOUL_FOLDER / SOUL_FILES["observations"]
    if not obs_path.exists():
        return ""

    content = obs_path.read_text(encoding="utf-8").strip()
    if not content or _is_default_observations(content):
        return content

    parsed = _parse_observation_entries(content)

    # Build base: header + summary
    base_parts = ["# Observations"]
    if parsed['summary_block']:
        base_parts.append("")
        base_parts.append(parsed['summary_block'])
    base = '\n'.join(base_parts)

    # Filter out resolved entries
    active_entries = [e for e in parsed['entries'] if not e['resolved']]

    # Take at most KEEP_RECENT most recent active entries that fit budget
    candidates = active_entries[-OBSERVATIONS_KEEP_RECENT:]
    budget = OBSERVATIONS_CONTEXT_MAX_TOKENS - estimate_tokens(base)

    selected: List[dict] = []
    for entry in reversed(candidates):
        entry_text = f"\n\n---\n{entry['raw']}"
        entry_tokens = estimate_tokens(entry_text)
        if budget - entry_tokens >= 0:
            selected.insert(0, entry)
            budget -= entry_tokens
        else:
            break

    result = base
    for entry in selected:
        result += f"\n\n---\n{entry['raw']}"

    return result


def check_observations_need_consolidation() -> bool:
    """Check if observations.md exceeds thresholds and needs consolidation."""
    root = _memory_root()
    if not root:
        return False

    obs_path = root / SOUL_FOLDER / SOUL_FILES["observations"]
    if not obs_path.exists():
        return False

    try:
        content = obs_path.read_text(encoding="utf-8").strip()
    except Exception:
        return False

    if not content or _is_default_observations(content):
        return False

    parsed = _parse_observation_entries(content)
    active_entries = [e for e in parsed['entries'] if not e['resolved']]

    if len(active_entries) > OBSERVATIONS_MAX_ENTRIES:
        return True
    if estimate_tokens(content) > OBSERVATIONS_TOKEN_THRESHOLD:
        return True

    return False


def prepare_observations_for_consolidation() -> Optional[dict]:
    """Extract old entries for summarization. Returns None if not needed.

    Returns dict with:
        'old_entries_text': entries to summarize (formatted for LLM)
        'recent_entries': list of entry dicts to keep
        'current_summary': existing summary block or None
        'full_content': full file content for archiving
    """
    root = _memory_root()
    if not root:
        return None

    obs_path = root / SOUL_FOLDER / SOUL_FILES["observations"]
    if not obs_path.exists():
        return None

    full_content = obs_path.read_text(encoding="utf-8")
    parsed = _parse_observation_entries(full_content)

    if len(parsed['entries']) <= OBSERVATIONS_KEEP_RECENT:
        return None

    recent = parsed['entries'][-OBSERVATIONS_KEEP_RECENT:]
    old = parsed['entries'][:-OBSERVATIONS_KEEP_RECENT]

    if not old:
        return None

    old_text_parts = []
    for entry in old:
        old_text_parts.append(f"---\n{entry['raw']}")
    old_entries_text = '\n\n'.join(old_text_parts)

    return {
        'old_entries_text': old_entries_text,
        'recent_entries': recent,
        'current_summary': parsed['summary_block'],
        'full_content': full_content,
    }


def write_consolidated_observations(
    summary: str, recent_entries: list, full_content_for_archive: str
) -> Dict:
    """Write consolidated observations and archive the original.

    - Archives full pre-compression content to observations_archive.md
    - Replaces observations.md with summary block + recent entries
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    soul_dir = root / SOUL_FOLDER
    obs_path = soul_dir / SOUL_FILES["observations"]
    archive_path = soul_dir / OBSERVATIONS_ARCHIVE_FILE

    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # Archive full pre-compression content
        archive_header = f"\n\n---\n## Session: {today}\n\n"
        if archive_path.exists():
            existing_archive = archive_path.read_text(encoding="utf-8")
        else:
            existing_archive = (
                "# Observations Archive\n\n"
                "Full observation history, preserved during consolidation.\n"
            )

        archive_path.write_text(
            existing_archive.rstrip() + archive_header + full_content_for_archive.strip() + "\n",
            encoding="utf-8",
        )

        # Build new observations.md: summary block + recent entries
        parts = [
            f"# Observations\n\n"
            f"## Summarized observations (through {today})\n"
            f"{summary.strip()}"
        ]
        for entry in recent_entries:
            parts.append(f"\n---\n{entry['raw']}")

        new_content = ''.join(parts) + "\n"
        obs_path.write_text(new_content, encoding="utf-8")

        return {
            "success": True,
            "entries_kept": len(recent_entries),
            "tokens": estimate_tokens(new_content),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_soul(content: str, file: str = "soul") -> Dict:
    """
    Update a file in the soul/ directory.
    file: one of 'soul', 'observations', 'opinions', 'unresolved'.
    Returns dict with 'success' and optional 'error'.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    file = (file or "soul").strip().lower()

    # Observations are append-only — redirect to update_observations
    if file == "observations":
        return {
            "success": False,
            "error": "Use update_observations to add entries to the observations log. "
                     "Each call appends a timestamped entry — do not overwrite the file.",
        }

    if file not in VALID_SOUL_FILES:
        allowed = sorted(VALID_SOUL_FILES - {"observations"})
        return {"success": False, "error": f"Invalid soul file: {file}. Must be one of: {', '.join(allowed)}"}

    if content is None:
        content = ""
    content = str(content).strip()

    soul_dir = root / SOUL_FOLDER
    path = soul_dir / SOUL_FILES[file]
    try:
        soul_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8")
        return {"success": True, "tokens": estimate_tokens(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
    """Load a context file by category. Backward-compat wrapper around read_memory_file."""
    return read_memory_file(f"context/{category}")


def update_context(category: str, content: str) -> Dict:
    """Update a context file by category. Backward-compat wrapper around write_memory_file."""
    return write_memory_file(f"context/{category}", content)


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


def _format_file_entry(filepath: Path) -> str:
    """Format a file entry with size annotation for large files (>2KB)."""
    name = filepath.stem
    try:
        size = filepath.stat().st_size
        if size > 2048:
            return f"{name} ({size // 1024}KB)"
    except OSError:
        pass
    return name


# ---------------------------------------------------------------------------
# Unified memory file access (used by read_memory / write_memory tools)
# ---------------------------------------------------------------------------

def read_memory_file(path: str) -> str:
    """
    Read a memory file or directory by path relative to AI Memory/.
    Examples: 'context/personal', 'context/work/projects', 'timelines/current-goals'
    If path points to a directory, returns concatenation of all .md files in it (flat).
    """
    root = _memory_root()
    if not root:
        return ""

    path = (path or "").strip().strip("/")
    if not path:
        return ""

    if ".." in path or path.startswith(("/", "\\", "~")) or ":" in path:
        return ""

    root_resolved = root.resolve()

    # Check both file (.md) and directory forms
    file_path = root / f"{path}.md"
    dir_path = root / path

    try:
        file_path.resolve().relative_to(root_resolved)
    except (ValueError, Exception):
        return ""

    try:
        dir_path.resolve().relative_to(root_resolved)
    except (ValueError, Exception):
        pass  # dir_path may not exist, that's fine

    # Prefer directory when it exists (contains more specific files)
    if dir_path.is_dir():
        bits = []
        for md_file in sorted(dir_path.glob("*.md")):
            content = _read_file_safe(md_file)
            if content:
                bits.append(f"## {md_file.stem}\n\n{content}")
        if bits:
            return "\n\n".join(bits)

    # Fall back to single file
    if file_path.is_file():
        return _read_file_safe(file_path)

    return ""


def write_memory_file(path: str, content: str) -> Dict:
    """
    Write a memory file. Path is relative to AI Memory/ (e.g. 'context/work/projects').
    Creates parent directories if needed. Blocks writing to core-memory.md and archive/.
    """
    root = _memory_root()
    if not root:
        return {"success": False, "error": "OBSIDIAN_PATH not set or invalid"}

    path = (path or "").strip().strip("/")
    if not path:
        return {"success": False, "error": "path is required"}

    if ".." in path or path.startswith(("/", "\\", "~")) or ":" in path:
        return {"success": False, "error": f"Invalid path: {path}"}

    # Guard core memory (must use update_core_memory for token limit enforcement)
    if path.lower().replace("-", "").replace("_", "") in ("corememory",):
        return {"success": False, "error": "Use update_core_memory to modify core memory (enforces token limit)"}

    # Guard soul directory (must use update_soul tool)
    path_lower = path.lower().strip("/")
    if path_lower in ("soul", "soul.md") or path_lower.startswith("soul/"):
        return {"success": False, "error": "Use update_soul to modify soul files"}

    # Guard archive (must use archive_memory for append-only semantics)
    if path.startswith("archive"):
        return {"success": False, "error": "Use archive_memory to append to archives"}

    file_path = root / f"{path}.md"
    root_resolved = root.resolve()

    try:
        file_path.resolve().relative_to(root_resolved)
    except (ValueError, Exception):
        return {"success": False, "error": f"Invalid path: {path}"}

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text((content or "").strip(), encoding="utf-8")
        return {"success": True, "filepath": f"{path}.md"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_archive(date: Optional[str] = None) -> str:
    """
    Read archive content.  If date (YYYY-MM) provided, reads that month's archive.
    If no date, lists available archive months.
    """
    root = _memory_root()
    if not root:
        return "(No archived content — vault not configured)"

    archive_dir = root / ARCHIVE_FOLDER
    if not archive_dir.exists():
        return "(No archived content)"

    if date:
        date = date.strip()
        month_dir = archive_dir / date
        if not month_dir.exists():
            return f"(No archive for {date})"
        parts = []
        for md_file in sorted(month_dir.glob("*.md")):
            parts.append(f"## {md_file.stem}\n\n{_read_file_safe(md_file)}")
        content = "\n\n".join(parts)
        return content.strip() if content.strip() else f"(Archive for {date} is empty)"

    # List available months
    months = sorted([d.name for d in archive_dir.iterdir() if d.is_dir()])
    if not months:
        return "(No archived content)"
    return "Available archive months: " + ", ".join(months)


def _validate_memory_file_path(file_key: str, base_path: Path) -> tuple[bool, str]:
    """
    Validate that a file key is safe and won't escape the memory folder.

    Args:
        file_key: Relative file path from LLM (e.g., "work/projects", "personal")
        base_path: Base directory (e.g., AI Memory/context/)

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(file_key, str):
        return False, f"Invalid path: key must be string, got {type(file_key).__name__}"
    file_key = file_key.strip()
    if not file_key:
        return False, "Invalid path: empty file key"

    # Check for path traversal attempts
    if ".." in file_key or file_key.startswith("/") or file_key.startswith("\\"):
        return False, f"Invalid path: {file_key} (path traversal attempt)"

    # Check for absolute paths or drive letters
    if ":" in file_key or file_key.startswith("~"):
        return False, f"Invalid path: {file_key} (absolute path not allowed)"

    # Construct full path and verify it's still under base_path
    try:
        full_path = (base_path / f"{file_key}.md").resolve()
        base_resolved = base_path.resolve()
        full_path.relative_to(base_resolved)
    except ValueError:
        return False, f"Invalid path: {file_key} (escapes base directory)"
    except Exception as e:
        return False, f"Invalid path: {file_key} ({str(e)})"

    return True, ""


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
            is_valid, error_msg = _validate_memory_file_path(file_key, context_dir)
            if not is_valid:
                print(f"Skipping invalid context path: {error_msg}")
                continue
            # file_key may be "personal", "work/current-role", "life/finances", etc.
            full_path = context_dir / f"{file_key}.md"
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

        timelines_dir = root / TIMELINES_FOLDER
        timelines_dir.mkdir(parents=True, exist_ok=True)
        timelines_data = memory_structure.get("timelines") or {}
        for file_key, content in timelines_data.items():
            content = (content if isinstance(content, str) else "") or ""
            content = content.strip()
            if not content:
                continue
            is_valid, error_msg = _validate_memory_file_path(file_key, timelines_dir)
            if not is_valid:
                print(f"Skipping invalid timeline path: {error_msg}")
                continue
            (timelines_dir / f"{file_key}.md").write_text(content, encoding="utf-8")

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_specific_context(category: str, subcategory: Optional[str] = None) -> str:
    """Backward-compat wrapper around read_memory_file."""
    if subcategory:
        return read_memory_file(f"context/{category}/{subcategory}")
    return read_memory_file(f"context/{category}")


def update_specific_context(category: str, subcategory: str, content: str) -> Dict:
    """Backward-compat wrapper around write_memory_file."""
    return write_memory_file(f"context/{category}/{subcategory}", content)


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

    # Backward compat for callers expecting flat keys (onboarding refresh flow).
    # Prefer flat file; fall back to concatenation of subdirectory files.
    ctx = out["context"]
    for flat_key, compat_key in (
        ("personal", "personal"),
        ("work", "work"),
        ("preferences", "preferences"),
        ("current-focus", "current_focus"),
    ):
        flat_val = ctx.get(flat_key, "")
        if flat_val:
            out[compat_key] = flat_val
        else:
            # Concatenate subdirectory files (e.g. work/current-role + work/projects)
            sub_vals = [v for k, v in ctx.items() if k.startswith(f"{flat_key}/") and v]
            out[compat_key] = "\n\n".join(sub_vals)

    # Also expose timelines as current_focus if the flat file is empty
    if not out.get("current_focus"):
        out["current_focus"] = out["timelines"].get("current-goals", "")

    return out


def build_memory_map() -> str:
    """
    Walk AI Memory/ and build a directory map for the model.
    Shows context files, timelines, and archive months with file sizes.
    Automatically reflects the real vault structure — no hardcoding.
    """
    vault = _get_vault_path()
    if not vault:
        return ""

    mem_root = vault / MEMORY_FOLDER
    if not mem_root.exists():
        return ""

    lines = ["## Memory map (files available — use read_memory to load)"]

    # Context files
    context_dir = mem_root / CONTEXT_FOLDER
    if context_dir.exists():
        for walk_root, dirs, files in os.walk(str(context_dir)):
            dirs.sort()
            rel = os.path.relpath(walk_root, str(context_dir))
            md_files = sorted(
                [Path(walk_root) / f for f in files if f.endswith(".md")]
            )
            if not md_files:
                continue
            entries = [_format_file_entry(f) for f in md_files]
            if rel == ".":
                lines.append(f"- context/: {', '.join(entries)}")
            else:
                lines.append(f"- context/{rel}/: {', '.join(entries)}")

    # Timeline files
    timelines_dir = mem_root / TIMELINES_FOLDER
    if timelines_dir.exists():
        tl_files = sorted(timelines_dir.glob("*.md"))
        if tl_files:
            entries = [_format_file_entry(f) for f in tl_files]
            lines.append(f"- timelines/: {', '.join(entries)}")

    # Archive months (just list, not content)
    archive_dir = mem_root / ARCHIVE_FOLDER
    if archive_dir.exists():
        months = sorted([d.name for d in archive_dir.iterdir() if d.is_dir()])
        if months:
            lines.append(f"- archive/: {', '.join(months)}")

    if len(lines) == 1:
        return ""

    return "\n".join(lines)


def get_memory_stats() -> Dict:
    """
    Return token counts for core memory and each context/timeline file.
    Keys: core_tokens, core_chars, context_tokens (dict by path), context_chars (dict).
    """
    root = _memory_root()
    out: Dict = {
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

    # Walk all .md files under context/ and timelines/
    for subdir in (CONTEXT_FOLDER, TIMELINES_FOLDER):
        base = root / subdir
        if not base.exists():
            continue
        for md_file in base.rglob("*.md"):
            try:
                rel = str(md_file.relative_to(root).with_suffix("")).replace("\\", "/")
                text = md_file.read_text(encoding="utf-8")
                out["context_chars"][rel] = len(text)
                out["context_tokens"][rel] = estimate_tokens(text)
            except Exception:
                pass

    return out
