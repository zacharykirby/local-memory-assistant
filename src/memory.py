# memory.py
import os
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MEMORY_FOLDER = "AI Memory"
FACTS_FILE = "facts.md"


def _get_vault_path():
    """Get vault path from environment"""
    vault_path = os.getenv("OBSIDIAN_PATH")
    if not vault_path:
        return None

    vault_path = Path(vault_path)
    if not vault_path.exists() or not vault_path.is_dir():
        return None

    return vault_path


def _ensure_facts_file():
    """Ensure AI Memory folder and facts.md file exist"""
    vault_path = _get_vault_path()
    if not vault_path:
        return None

    memory_folder = vault_path / MEMORY_FOLDER
    memory_folder.mkdir(parents=True, exist_ok=True)

    facts_path = memory_folder / FACTS_FILE

    # Create facts.md with frontmatter if it doesn't exist
    if not facts_path.exists():
        now = datetime.now().isoformat()
        initial_content = f"""---
created: {now}
updated: {now}
topics:
  - facts
  - user
---

# Facts About User

<!-- Facts are stored as bullet points below -->

"""
        with open(facts_path, 'w', encoding='utf-8') as f:
            f.write(initial_content)

    return facts_path


def _update_timestamp(facts_path: Path):
    """Update the 'updated' timestamp in frontmatter"""
    try:
        with open(facts_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Update the timestamp in frontmatter
        now = datetime.now().isoformat()
        content = re.sub(
            r'(updated:\s*)(.+)',
            f'updated: {now}',
            content
        )

        with open(facts_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception:
        pass  # Ignore timestamp update failures


def load_facts():
    """Load facts from AI Memory/facts.md"""
    facts_path = _ensure_facts_file()
    if not facts_path:
        return []

    try:
        with open(facts_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Remove frontmatter
        content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)

        # Extract bullet points (facts)
        facts = []
        for line in content.split('\n'):
            line = line.strip()
            # Match bullet points (-, *, +)
            if line.startswith('- ') or line.startswith('* ') or line.startswith('+ '):
                fact = line[2:].strip()
                if fact and not fact.startswith('<!--'):  # Skip comments
                    facts.append(fact)

        return facts
    except Exception:
        return []


def save_fact(fact):
    """Append a new fact to AI Memory/facts.md"""
    facts_path = _ensure_facts_file()
    if not facts_path:
        return False

    # Check if fact already exists
    existing_facts = load_facts()
    if fact in existing_facts:
        return False

    try:
        # Append the fact as a new bullet point
        with open(facts_path, 'a', encoding='utf-8') as f:
            f.write(f"- {fact}\n")

        # Update timestamp
        _update_timestamp(facts_path)

        return True
    except Exception:
        return False


def retrieve_facts(query=None):
    """Retrieve facts, optionally filtered by query"""
    facts = load_facts()

    # Return all facts if no query or empty string
    if not query or query.strip() == "":
        return facts

    # Case-insensitive substring search with partial word matching
    query_lower = query.lower().strip()

    # Split query into words for more flexible matching
    query_words = query_lower.split()

    matching_facts = []
    for fact in facts:
        fact_lower = fact.lower()
        # Match if the full query is in the fact OR if any query word matches
        if query_lower in fact_lower or any(word in fact_lower for word in query_words):
            matching_facts.append(fact)

    return matching_facts
