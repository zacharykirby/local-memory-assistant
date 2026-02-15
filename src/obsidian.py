# obsidian.py
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from memory import MEMORY_FOLDER, SOUL_FILE, _get_vault_path as _memory_get_vault_path


def _parse_frontmatter_tags(content: str) -> List[str]:
    """Extract tags from YAML frontmatter"""
    tags = []
    frontmatter_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)

    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)
        # Match tags in various formats: tags: [tag1, tag2] or tags:\n  - tag1
        tag_lines = re.findall(r'tags:\s*\[(.*?)\]', frontmatter)
        if tag_lines:
            for tag_line in tag_lines:
                tags.extend([t.strip().strip('"\'') for t in tag_line.split(',')])

        # Also match list format
        in_tags_section = False
        for line in frontmatter.split('\n'):
            if line.strip().startswith('tags:'):
                in_tags_section = True
                continue
            if in_tags_section:
                if line.strip().startswith('- '):
                    tags.append(line.strip()[2:].strip())
                elif not line.startswith(' ') and not line.startswith('\t'):
                    in_tags_section = False

    return tags


def _parse_inline_tags(content: str) -> List[str]:
    """Extract inline #tags from content"""
    # Match #tag but not ##heading
    return re.findall(r'(?:^|[^#\w])#([\w-]+)(?:[^\w-]|$)', content)


def _get_all_tags(content: str) -> List[str]:
    """Get all tags from a note (frontmatter + inline)"""
    tags = set()
    tags.update(_parse_frontmatter_tags(content))
    tags.update(_parse_inline_tags(content))
    return list(tags)


def _get_preview_snippet(content: str, match_pos: int, context_length: int = 100) -> str:
    """Extract a preview snippet around a match position"""
    start = max(0, match_pos - context_length // 2)
    end = min(len(content), match_pos + context_length // 2)

    snippet = content[start:end]

    # Clean up the snippet
    snippet = ' '.join(snippet.split())  # Normalize whitespace

    if start > 0:
        snippet = '...' + snippet
    if end < len(content):
        snippet = snippet + '...'

    return snippet


def _calculate_relevance_score(filepath: Path, title: str, content: str, query: str) -> tuple:
    """Calculate relevance score for sorting. Returns (score, match_type)"""
    query_lower = query.lower()
    title_lower = title.lower()
    content_lower = content.lower()

    # Title exact match: highest priority
    if query_lower == title_lower:
        return (1000, "title_exact")

    # Title contains query
    if query_lower in title_lower:
        return (500, "title_contains")

    # Count occurrences in content
    content_matches = content_lower.count(query_lower)
    if content_matches > 0:
        return (content_matches * 10, "content_matches")

    return (0, "no_match")


def search_vault(query: str, tags: Optional[List[str]] = None, folder: Optional[str] = None) -> Dict:
    """
    Search Obsidian vault for notes matching criteria.

    Args:
        query: Text to search for (searches note content and titles)
        tags: Optional list of tags to filter by (e.g., ["project", "work"])
        folder: Optional folder path to limit search (e.g., "Work/Projects")

    Returns:
        dict with 'results': list of {filepath, title, preview, matches, tags}
    """
    vault_path, error = _get_vault_path()
    if error:
        return {
            "error": error,
            "results": []
        }

    # Determine search root
    search_root = vault_path / folder if folder else vault_path

    if not search_root.exists():
        return {
            "error": f"Folder does not exist: {search_root}",
            "results": []
        }

    results = []
    query_lower = query.lower()
    tags_lower = [t.lower() for t in tags] if tags else []

    # Search all markdown files
    try:
        for md_file in search_root.rglob("*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Extract title (filename without extension)
                title = md_file.stem

                # Get all tags from the note
                note_tags = _get_all_tags(content)

                # Filter by tags if specified
                if tags_lower:
                    note_tags_lower = [t.lower() for t in note_tags]
                    if not any(tag in note_tags_lower for tag in tags_lower):
                        continue

                # Search for query in title or content
                title_lower = title.lower()
                content_lower = content.lower()

                if query_lower not in title_lower and query_lower not in content_lower:
                    continue

                # Calculate relevance score
                score, match_type = _calculate_relevance_score(md_file, title, content, query)

                # Find match position for preview
                match_pos = content_lower.find(query_lower)
                if match_pos == -1:
                    # Must be in title
                    preview = content[:100].strip()
                else:
                    preview = _get_preview_snippet(content, match_pos)

                # Get relative path from vault root
                relative_path = md_file.relative_to(vault_path)

                results.append({
                    "filepath": str(relative_path),
                    "title": title,
                    "preview": preview,
                    "match_type": match_type,
                    "tags": note_tags,
                    "score": score
                })

            except (IOError, UnicodeDecodeError) as e:
                # Skip files that can't be read
                continue

        # Sort by relevance score (highest first)
        results.sort(key=lambda x: x["score"], reverse=True)

        # Return top 10 results
        top_results = results[:10]

        # Remove score before returning (internal use only)
        for r in top_results:
            del r["score"]

        return {
            "results": top_results,
            "total_found": len(results)
        }

    except Exception as e:
        return {
            "error": f"Error searching vault: {str(e)}",
            "results": []
        }


# ============================================================================
# AI MEMORY MANAGEMENT
# ============================================================================

def _validate_memory_path(filename: str, vault_path: Path) -> tuple:
    """
    Validate that a filename is safe and within AI Memory folder.
    Returns: (is_valid, error_message, absolute_path)
    """
    # Block dangerous patterns
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        return False, "Invalid path: cannot use '..' or absolute paths", None

    # Ensure .md extension
    if not filename.endswith('.md'):
        filename = filename + '.md'

    # Construct full path
    memory_folder = vault_path / MEMORY_FOLDER
    target_path = memory_folder / filename

    # Resolve to absolute path
    try:
        target_resolved = target_path.resolve()
        memory_resolved = memory_folder.resolve()
    except Exception as e:
        return False, f"Path resolution error: {str(e)}", None

    # Verify it's within AI Memory folder
    try:
        target_resolved.relative_to(memory_resolved)
    except ValueError:
        return False, "Path escapes AI Memory folder", None

    return True, "", target_resolved


def _ensure_memory_folder(vault_path: Path) -> tuple:
    """Create AI Memory folder if it doesn't exist. Returns (success, error_msg)"""
    memory_folder = vault_path / MEMORY_FOLDER
    try:
        memory_folder.mkdir(parents=True, exist_ok=True)
        return True, ""
    except Exception as e:
        return False, f"Failed to create AI Memory folder: {str(e)}"


def _format_frontmatter(created: str = None, updated: str = None, topics: List[str] = None) -> str:
    """Generate YAML frontmatter"""
    now = datetime.now().isoformat()
    created = created or now
    updated = updated or now

    frontmatter = f"---\ncreated: {created}\nupdated: {updated}\n"
    if topics:
        frontmatter += "topics:\n"
        for topic in topics:
            frontmatter += f"  - {topic}\n"
    frontmatter += "---\n\n"
    return frontmatter


def _parse_frontmatter_metadata(content: str) -> Dict:
    """Extract metadata from frontmatter"""
    metadata = {}
    frontmatter_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)

    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)

        # Extract created/updated
        created_match = re.search(r'created:\s*(.+)', frontmatter)
        if created_match:
            metadata['created'] = created_match.group(1).strip()

        updated_match = re.search(r'updated:\s*(.+)', frontmatter)
        if updated_match:
            metadata['updated'] = updated_match.group(1).strip()

        # Extract topics
        topics = []
        in_topics_section = False
        for line in frontmatter.split('\n'):
            if line.strip().startswith('topics:'):
                in_topics_section = True
                continue
            if in_topics_section:
                if line.strip().startswith('- '):
                    topics.append(line.strip()[2:].strip())
                elif not line.startswith(' ') and not line.startswith('\t'):
                    in_topics_section = False

        if topics:
            metadata['topics'] = topics

    return metadata


def _get_vault_path() -> tuple:
    """Get vault path from env. Returns (vault_path, error_msg)."""
    vault = _memory_get_vault_path()
    if vault is None:
        return None, "OBSIDIAN_PATH not set or invalid"
    return vault, None


def _is_soul_path(filename: str) -> bool:
    """Check if a filename resolves to soul.md (Memoria's protected self-concept file)."""
    normalized = filename.strip().lower().replace("\\", "/")
    # Match 'soul.md', 'soul', or paths ending in '/soul.md', '/soul'
    stem = normalized.removesuffix(".md")
    return stem == "soul" or stem.endswith("/soul")


def create_memory_note(title: str, content: str, subfolder: str = None, topics: List[str] = None) -> Dict:
    """
    Create new markdown note in AI Memory/ folder.

    Args:
        title: Note title (will be filename without .md)
        content: Note content (markdown)
        subfolder: Optional subfolder within AI Memory (e.g., "topics")
        topics: Optional list of topic tags for frontmatter

    Returns:
        dict with 'success', 'filepath', or 'error'
    """
    vault_path, error = _get_vault_path()
    if error:
        return {"success": False, "error": error}

    # Guard soul.md — use update_soul tool instead
    check_name = f"{subfolder}/{title}" if subfolder else title
    if _is_soul_path(check_name):
        return {"success": False, "error": "soul.md is protected — use update_soul to modify it"}

    # Ensure AI Memory folder exists
    success, error = _ensure_memory_folder(vault_path)
    if not success:
        return {"success": False, "error": error}

    # Build filename with subfolder if provided
    filename = f"{subfolder}/{title}" if subfolder else title

    # Validate path
    is_valid, error_msg, target_path = _validate_memory_path(filename, vault_path)
    if not is_valid:
        return {"success": False, "error": error_msg}

    # Check if file already exists
    if target_path.exists():
        return {"success": False, "error": f"Note already exists: {filename}"}

    # Create parent directories if needed
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate frontmatter
    frontmatter = _format_frontmatter(topics=topics)

    # Write file
    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(frontmatter + content)

        relative_path = target_path.relative_to(vault_path)
        return {
            "success": True,
            "filepath": str(relative_path),
            "message": f"Created note: {relative_path}"
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to write file: {str(e)}"}


def read_memory_note(filename: str) -> Dict:
    """
    Read existing memory note.

    Args:
        filename: Filename relative to AI Memory/ folder

    Returns:
        dict with 'success', 'content', 'metadata', or 'error'
    """
    vault_path, error = _get_vault_path()
    if error:
        return {"success": False, "error": error}

    # Validate path
    is_valid, error_msg, target_path = _validate_memory_path(filename, vault_path)
    if not is_valid:
        return {"success": False, "error": error_msg}

    # Check if file exists
    if not target_path.exists():
        return {"success": False, "error": f"Note not found: {filename}"}

    # Read file
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse metadata
        metadata = _parse_frontmatter_metadata(content)

        # Remove frontmatter from content for display
        content_without_frontmatter = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)

        return {
            "success": True,
            "content": content_without_frontmatter,
            "full_content": content,
            "metadata": metadata,
            "filepath": str(target_path.relative_to(vault_path))
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to read file: {str(e)}"}


def update_memory_note(filename: str, new_content: str, topics: List[str] = None, append: bool = False) -> Dict:
    """
    Update a memory note.  By default replaces entire content; set append=True
    to add content to the end instead.  Preserves created date and updates
    the 'updated' timestamp.

    Args:
        filename: Filename relative to AI Memory/ folder
        new_content: Content to write (replacement) or append
        topics: Optional new/updated topics list
        append: If True, append new_content to end of existing body

    Returns:
        dict with 'success', 'filepath', or 'error'
    """
    vault_path, error = _get_vault_path()
    if error:
        return {"success": False, "error": error}

    # Guard soul.md — use update_soul tool instead
    if _is_soul_path(filename):
        return {"success": False, "error": "soul.md is protected — use update_soul to modify it"}

    # Validate path
    is_valid, error_msg, target_path = _validate_memory_path(filename, vault_path)
    if not is_valid:
        return {"success": False, "error": error_msg}

    # Check if file exists
    if not target_path.exists():
        return {"success": False, "error": f"Note not found: {filename}"}

    # Read existing file to preserve created date
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            old_content = f.read()

        old_metadata = _parse_frontmatter_metadata(old_content)
        created = old_metadata.get('created')

        # If topics not provided, preserve existing topics
        if topics is None:
            topics = old_metadata.get('topics')

        # Generate new frontmatter with updated timestamp
        frontmatter = _format_frontmatter(created=created, topics=topics)

        if append:
            # Remove old frontmatter from existing content, then append
            body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', old_content, flags=re.DOTALL)
            final_body = body + "\n\n" + new_content
        else:
            final_body = new_content

        # Write updated file
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(frontmatter + final_body)

        relative_path = target_path.relative_to(vault_path)
        verb = "Appended to" if append else "Updated"
        return {
            "success": True,
            "filepath": str(relative_path),
            "message": f"{verb} note: {relative_path}"
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to update file: {str(e)}"}


def append_to_memory_note(filename: str, content: str) -> Dict:
    """Backward-compat wrapper: append content to a memory note."""
    return update_memory_note(filename, content, append=True)


def list_memory_notes(subfolder: str = None) -> Dict:
    """
    List all notes in AI Memory/ folder.

    Args:
        subfolder: Optional subfolder to list (e.g., "topics")

    Returns:
        dict with 'success', 'notes' (list of dicts with filepath, title, metadata), or 'error'
    """
    vault_path, error = _get_vault_path()
    if error:
        return {"success": False, "error": error}

    # Ensure AI Memory folder exists
    memory_folder = vault_path / MEMORY_FOLDER
    if not memory_folder.exists():
        return {"success": True, "notes": [], "message": "AI Memory folder is empty"}

    # Determine search path
    if subfolder:
        # Validate subfolder path (similar to files but without .md extension)
        if ".." in subfolder or subfolder.startswith("/") or subfolder.startswith("\\"):
            return {"success": False, "error": "Invalid path: cannot use '..' or absolute paths"}

        search_path = (memory_folder / subfolder).resolve()

        # Verify it's within AI Memory folder
        try:
            search_path.relative_to(memory_folder.resolve())
        except ValueError:
            return {"success": False, "error": "Path escapes AI Memory folder"}
    else:
        search_path = memory_folder

    if not search_path.exists():
        return {"success": True, "notes": [], "message": f"Subfolder not found: {subfolder}"}

    # List all markdown files (excluding soul.md — Memoria's private self-concept)
    notes = []
    try:
        for md_file in search_path.rglob("*.md"):
            try:
                # Skip soul.md — not a user memory note
                relative_path = md_file.relative_to(vault_path / MEMORY_FOLDER)
                if str(relative_path) == SOUL_FILE:
                    continue

                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                metadata = _parse_frontmatter_metadata(content)

                notes.append({
                    "filepath": str(relative_path),
                    "title": md_file.stem,
                    "created": metadata.get('created'),
                    "updated": metadata.get('updated'),
                    "topics": metadata.get('topics', [])
                })
            except Exception:
                # Skip files that can't be read
                continue

        # Sort by updated date (most recent first); treat None as ''
        notes.sort(key=lambda x: x.get('updated') or '', reverse=True)

        return {
            "success": True,
            "notes": notes,
            "count": len(notes)
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to list notes: {str(e)}"}


def delete_memory_note(filename: str) -> Dict:
    """
    Delete a memory note (use sparingly).

    Args:
        filename: Filename relative to AI Memory/ folder

    Returns:
        dict with 'success', 'message', or 'error'
    """
    vault_path, error = _get_vault_path()
    if error:
        return {"success": False, "error": error}

    # Guard soul.md — cannot be deleted via this tool
    if _is_soul_path(filename):
        return {"success": False, "error": "soul.md is protected and cannot be deleted"}

    # Validate path
    is_valid, error_msg, target_path = _validate_memory_path(filename, vault_path)
    if not is_valid:
        return {"success": False, "error": error_msg}

    # Check if file exists
    if not target_path.exists():
        return {"success": False, "error": f"Note not found: {filename}"}

    # Delete file
    try:
        target_path.unlink()
        return {
            "success": True,
            "message": f"Deleted note: {filename}"
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to delete file: {str(e)}"}
