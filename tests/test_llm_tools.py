"""
Tests for LLM tool calls: parse_tool_arguments and execute_tool.
Uses a temporary vault directory so no real data is touched.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from memory import ensure_memory_structure, write_organized_memory, delete_ai_memory_folder, reset_soul_folder


@pytest.fixture
def vault_path(tmp_path, monkeypatch):
    """Point OBSIDIAN_PATH to a temp dir and create memory structure."""
    monkeypatch.setenv("OBSIDIAN_PATH", str(tmp_path))
    result = ensure_memory_structure()
    assert result.get("success"), result.get("error", "ensure_memory_structure failed")
    return tmp_path


@pytest.fixture
def execute_tool(vault_path):
    """Import execute_tool after env is set so it uses the temp vault."""
    from tools import execute_tool as _execute_tool
    return _execute_tool


@pytest.fixture
def parse_tool_arguments():
    from tools import parse_tool_arguments
    return parse_tool_arguments


# --- parse_tool_arguments ---


def test_parse_tool_arguments_json_string(parse_tool_arguments):
    tool_call = {"function": {"name": "foo", "arguments": '{"a": 1, "b": "two"}'}}
    assert parse_tool_arguments(tool_call) == {"a": 1, "b": "two"}


def test_parse_tool_arguments_dict(parse_tool_arguments):
    tool_call = {"function": {"name": "foo", "arguments": {"a": 1, "b": "two"}}}
    assert parse_tool_arguments(tool_call) == {"a": 1, "b": "two"}


def test_parse_tool_arguments_empty(parse_tool_arguments):
    assert parse_tool_arguments({}) == {}
    assert parse_tool_arguments({"function": {}}) == {}
    assert parse_tool_arguments({"function": {"arguments": "{}"}}) == {}


# --- read_core_memory ---


def test_read_core_memory_empty(execute_tool, vault_path):
    out = execute_tool("read_core_memory", {})
    assert "Core Memory" in out or "(Core memory is empty.)" in out or out == "(Core memory is empty.)"


def test_read_core_memory_after_update(execute_tool, vault_path):
    execute_tool("update_core_memory", {"content": "User likes tests."})
    out = execute_tool("read_core_memory", {})
    assert "User likes tests" in out


# --- update_core_memory ---


def test_update_core_memory_success(execute_tool, vault_path):
    out = execute_tool("update_core_memory", {"content": "Short core."})
    assert "updated" in out.lower() and "tokens" in out.lower()


def test_update_core_memory_empty_content(execute_tool, vault_path):
    out = execute_tool("update_core_memory", {"content": ""})
    assert "updated" in out.lower() or "Error" in out


def test_update_core_memory_over_limit(execute_tool, vault_path):
    big = "x" * 2500
    out = execute_tool("update_core_memory", {"content": big})
    assert "Error" in out and "exceeds" in out


# --- read_memory (unified context/timelines) ---


def test_read_memory_flat_context(execute_tool, vault_path):
    """Read a flat context file (e.g. context/personal)."""
    out = execute_tool("read_memory", {"path": "context/personal"})
    # New vault has a default file with a heading
    assert "personal" in out.lower() or "Personal" in out


def test_read_memory_missing_file(execute_tool, vault_path):
    out = execute_tool("read_memory", {"path": "context/nonexistent"})
    assert "No content" in out


def test_read_memory_after_write(execute_tool, vault_path):
    execute_tool("write_memory", {"path": "context/work/projects", "content": "Project Alpha."})
    out = execute_tool("read_memory", {"path": "context/work/projects"})
    assert "Project Alpha" in out


def test_read_memory_directory(execute_tool, vault_path):
    """Reading a directory returns all .md files in it."""
    execute_tool("write_memory", {"path": "context/work/projects", "content": "Project A."})
    execute_tool("write_memory", {"path": "context/work/current-role", "content": "Engineer."})
    out = execute_tool("read_memory", {"path": "context/work"})
    assert "Project A" in out
    assert "Engineer" in out


def test_read_memory_timelines(execute_tool, vault_path):
    """Timelines are accessible via read_memory."""
    (vault_path / "AI Memory" / "timelines").mkdir(parents=True, exist_ok=True)
    (vault_path / "AI Memory" / "timelines" / "current-goals.md").write_text("- Ship v1", encoding="utf-8")
    out = execute_tool("read_memory", {"path": "timelines/current-goals"})
    assert "Ship v1" in out


def test_read_memory_no_path(execute_tool, vault_path):
    out = execute_tool("read_memory", {"path": ""})
    assert "Error" in out or "No content" in out


# --- write_memory ---


def test_write_memory_creates_file(execute_tool, vault_path):
    out = execute_tool("write_memory", {"path": "context/life/finances", "content": "Budget info."})
    assert "Updated" in out
    assert (vault_path / "AI Memory" / "context" / "life" / "finances.md").exists()


def test_write_memory_blocks_core(execute_tool, vault_path):
    """Cannot overwrite core memory via write_memory (must use update_core_memory)."""
    out = execute_tool("write_memory", {"path": "core-memory", "content": "Sneaky."})
    assert "Error" in out and "core" in out.lower()


def test_write_memory_blocks_archive(execute_tool, vault_path):
    """Cannot write to archive via write_memory (must use archive_memory)."""
    out = execute_tool("write_memory", {"path": "archive/2026-01/conversations", "content": "Sneaky."})
    assert "Error" in out and "archive" in out.lower()


def test_write_memory_path_traversal(execute_tool, vault_path):
    """Path traversal attempts are blocked."""
    out = execute_tool("write_memory", {"path": "../../etc/passwd", "content": "Bad."})
    assert "Error" in out or "Invalid" in out.lower() or "No content" in out


def test_write_memory_timelines(execute_tool, vault_path):
    """Can rewrite timeline files (e.g. goals)."""
    out = execute_tool("write_memory", {"path": "timelines/current-goals", "content": "- Ship v1\n- Fix bugs"})
    assert "Updated" in out
    out = execute_tool("read_memory", {"path": "timelines/current-goals"})
    assert "Ship v1" in out and "Fix bugs" in out


# --- archive_memory ---


def test_archive_memory_success(execute_tool, vault_path):
    out = execute_tool("archive_memory", {"content": "Old summary."})
    assert "Archived" in out


# --- read_archive ---


def test_read_archive_empty(execute_tool, vault_path):
    out = execute_tool("read_archive", {})
    assert "No archived content" in out or "Available" in out


def test_read_archive_after_archive(execute_tool, vault_path):
    execute_tool("archive_memory", {"content": "February summary.", "date": "2026-02"})
    # List months
    out = execute_tool("read_archive", {})
    assert "2026-02" in out
    # Read specific month
    out = execute_tool("read_archive", {"date": "2026-02"})
    assert "February summary" in out


def test_read_archive_missing_month(execute_tool, vault_path):
    out = execute_tool("read_archive", {"date": "1999-01"})
    assert "No archive" in out


# --- search_vault ---


def test_search_vault_no_query(execute_tool, vault_path):
    out = execute_tool("search_vault", {})
    assert "Error" in out and "query" in out.lower()


def test_search_vault_with_query(execute_tool, vault_path):
    out = execute_tool("search_vault", {"query": "anything"})
    assert "No notes found" in out or "Found" in out


# --- create_memory_note ---


def test_create_memory_note_missing_args(execute_tool, vault_path):
    out = execute_tool("create_memory_note", {})
    assert "Error" in out and "required" in out


def test_create_memory_note_success(execute_tool, vault_path):
    out = execute_tool("create_memory_note", {
        "title": "TestNote",
        "content": "Body here."
    })
    assert "Created" in out or "Error" not in out


# --- read_memory_note ---


def test_read_memory_note_missing_filename(execute_tool, vault_path):
    out = execute_tool("read_memory_note", {})
    assert "Error" in out and "filename" in out.lower()


def test_read_memory_note_not_found(execute_tool, vault_path):
    out = execute_tool("read_memory_note", {"filename": "DoesNotExist.md"})
    assert "Error" in out


def test_read_memory_note_success(execute_tool, vault_path):
    execute_tool("create_memory_note", {"title": "ReadMe", "content": "Secret content."})
    out = execute_tool("read_memory_note", {"filename": "ReadMe.md"})
    assert "Secret content" in out


# --- update_memory_note (replace + append) ---


def test_update_memory_note_missing_args(execute_tool, vault_path):
    out = execute_tool("update_memory_note", {})
    assert "Error" in out and "required" in out


def test_update_memory_note_replace(execute_tool, vault_path):
    execute_tool("create_memory_note", {"title": "ToUpdate", "content": "Old."})
    out = execute_tool("update_memory_note", {
        "filename": "ToUpdate.md",
        "new_content": "New content."
    })
    assert "Updated" in out
    out_read = execute_tool("read_memory_note", {"filename": "ToUpdate.md"})
    assert "New content" in out_read
    assert "Old." not in out_read


def test_update_memory_note_append(execute_tool, vault_path):
    """append=True adds to end instead of replacing."""
    execute_tool("create_memory_note", {"title": "AppendMe", "content": "First."})
    out = execute_tool("update_memory_note", {
        "filename": "AppendMe.md",
        "new_content": "Second.",
        "append": True,
    })
    assert "Appended" in out or "Updated" in out or "Error" not in out
    out_read = execute_tool("read_memory_note", {"filename": "AppendMe.md"})
    assert "First." in out_read
    assert "Second." in out_read


# --- list_memory_notes ---


def test_list_memory_notes_empty(execute_tool, vault_path):
    out = execute_tool("list_memory_notes", {})
    assert (
        "No memory notes" in out
        or "Found 0" in out
        or "memory note" in out.lower()
        or "folder is empty" in out.lower()
    )


def test_list_memory_notes_after_create(execute_tool, vault_path):
    execute_tool("create_memory_note", {"title": "ListedNote", "content": "X"})
    out = execute_tool("list_memory_notes", {})
    assert "ListedNote" in out or "memory note" in out.lower()


# --- delete_memory_note ---


def test_delete_memory_note_missing_filename(execute_tool, vault_path):
    out = execute_tool("delete_memory_note", {})
    assert "Error" in out and "filename" in out.lower()


def test_delete_memory_note_success(execute_tool, vault_path):
    execute_tool("create_memory_note", {"title": "ToDelete", "content": "X"})
    out = execute_tool("delete_memory_note", {"filename": "ToDelete.md"})
    assert "Deleted" in out or "Error" not in out
    out_read = execute_tool("read_memory_note", {"filename": "ToDelete.md"})
    assert "Error" in out_read


# --- write_organized_memory path traversal ---


def test_write_organized_memory_path_traversal_prevention(vault_path):
    """Test that malicious paths from LLM are blocked."""
    malicious_memory = {
        "core_memory": "Safe content",
        "context": {
            "../../etc/passwd": "Malicious content",
            "/etc/shadow": "Absolute path",
            "work/projects": "Safe content",
            "personal": "Safe content",
            "~/.ssh/keys": "Home directory escape",
        },
        "timelines": {
            "../../../tmp/bad": "Escape attempt",
            "current-goals": "Safe timeline",
        },
    }

    write_organized_memory(malicious_memory)

    memory_dir = vault_path / "AI Memory"

    # Verify safe files were created
    assert (memory_dir / "context/work/projects.md").exists()
    assert (memory_dir / "context/personal.md").exists()
    assert (memory_dir / "timelines/current-goals.md").exists()

    # Check that no files escaped the AI Memory folder
    parent_of_memory = memory_dir.parent
    for bad_file in ["passwd", "shadow", "keys", "bad"]:
        escaped = list(parent_of_memory.rglob(f"*{bad_file}*"))
        outside = [p for p in escaped if memory_dir not in p.parents and p != memory_dir]
        assert not outside, f"Path traversal created file outside AI Memory: {outside}"


# --- unknown tool ---


def test_unknown_tool(execute_tool, vault_path):
    out = execute_tool("nonexistent_tool", {})
    assert "Unknown tool" in out and "nonexistent_tool" in out


# --- consolidation agentic loop ---


def test_consolidation_is_agentic(vault_path):
    """Consolidation uses an agentic loop: tool results are fed back to the LLM."""
    from llm import run_agent_loop
    from tools import CONSOLIDATION_TOOLS

    call_count = 0

    def mock_call_llm(messages, tools=None, stream=False, live_display=None, max_tokens=500):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "choices": [{
                    "message": {
                        "content": None,
                        "tool_calls": [{
                            "id": "call_0",
                            "function": {"name": "read_core_memory", "arguments": "{}"},
                        }],
                    },
                }],
            }
        return {
            "choices": [{
                "message": {
                    "content": "Memory reviewed.",
                    "tool_calls": None,
                },
            }],
        }

    initial_messages = [
        {"role": "system", "content": "Consolidate memory."},
        {"role": "user", "content": "Conversation summary: user said they like tests."},
    ]

    with patch("llm.call_llm", side_effect=mock_call_llm):
        result = run_agent_loop(
            initial_messages=initial_messages,
            tools=CONSOLIDATION_TOOLS,
            max_iterations=10,
            stream_first_response=False,
            show_tool_calls=False,
        )

    assert result["iterations"] == 2
    assert call_count == 2

    tool_messages = [m for m in result["messages"] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].get("tool_call_id") == "call_0"
    assert "Core" in tool_messages[0].get("content", "") or "empty" in tool_messages[0].get("content", "").lower()


# --- truncate_messages ---


def test_truncate_messages():
    """Test message truncation preserves system and keeps recent messages."""
    from llm import truncate_messages

    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Message 1"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": "Message 2"},
        {"role": "assistant", "content": "Response 2"},
    ]
    for i in range(3, 33):
        messages.append({"role": "user", "content": f"Message {i}"})
        messages.append({"role": "assistant", "content": f"Response {i}"})

    result = truncate_messages(messages, max_messages=20)

    assert result[0]["role"] == "system"
    assert result[0]["content"] == "System prompt"

    conversation = [m for m in result if m["role"] != "system"]
    assert len(conversation) == 20

    assert conversation[-1]["content"] == "Response 32"
    assert conversation[-2]["content"] == "Message 32"

    assert not any(m.get("content") == "Message 1" for m in result)
    assert not any(m.get("content") == "Response 1" for m in result)


def test_truncate_messages_no_truncation_needed():
    """When under limit, messages are returned unchanged."""
    from llm import truncate_messages

    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    result = truncate_messages(messages, max_messages=50)
    assert result == messages


def test_truncate_messages_empty():
    """Empty list returns empty list."""
    from llm import truncate_messages

    assert truncate_messages([]) == []
    assert truncate_messages([], max_messages=10) == []


# --- build_memory_map ---


def test_build_memory_map_includes_timelines(vault_path):
    """Memory map should include timeline files."""
    from memory import build_memory_map

    tl_dir = vault_path / "AI Memory" / "timelines"
    tl_dir.mkdir(parents=True, exist_ok=True)
    (tl_dir / "current-goals.md").write_text("- Goal 1", encoding="utf-8")

    memory_map = build_memory_map()
    assert "timelines/" in memory_map
    assert "current-goals" in memory_map


def test_build_memory_map_shows_file_sizes(vault_path):
    """Large files should show a size annotation."""
    from memory import build_memory_map

    big_file = vault_path / "AI Memory" / "context" / "work" / "projects.md"
    big_file.parent.mkdir(parents=True, exist_ok=True)
    big_file.write_text("x" * 5000, encoding="utf-8")

    memory_map = build_memory_map()
    assert "KB" in memory_map  # Should show size for the 5KB file


# --- read_memory_file / write_memory_file (unit tests) ---


def test_read_memory_file_path_traversal(vault_path):
    """Path traversal in read_memory_file returns empty string."""
    from memory import read_memory_file

    assert read_memory_file("../../etc/passwd") == ""
    assert read_memory_file("/etc/shadow") == ""
    assert read_memory_file("~/.ssh/keys") == ""


def test_write_memory_file_path_traversal(vault_path):
    """Path traversal in write_memory_file returns error."""
    from memory import write_memory_file

    result = write_memory_file("../../etc/passwd", "bad")
    assert not result.get("success")


def test_read_archive_function(vault_path):
    """read_archive function works directly."""
    from memory import read_archive, archive_memory

    # Empty archive
    out = read_archive()
    assert "No archived" in out

    # Archive something
    archive_memory("Test summary.", date="2026-02")

    # List months
    out = read_archive()
    assert "2026-02" in out

    # Read specific month
    out = read_archive("2026-02")
    assert "Test summary" in out


# --- soul.md ---


def test_ensure_memory_structure_creates_soul(vault_path):
    """ensure_memory_structure should create soul/ directory with seed files."""
    soul_dir = vault_path / "AI Memory" / "soul"
    assert soul_dir.is_dir()
    soul_md = soul_dir / "soul.md"
    assert soul_md.exists()
    content = soul_md.read_text(encoding="utf-8")
    assert "I am Memoria" in content
    assert "Mem, if we get there" in content
    # Check other soul files exist
    assert (soul_dir / "observations.md").exists()
    assert (soul_dir / "opinions.md").exists()
    assert (soul_dir / "unresolved.md").exists()


def test_read_soul_returns_content(vault_path):
    """read_soul should return the content of soul.md."""
    from memory import read_soul

    content = read_soul()
    assert "I am Memoria" in content


def test_read_soul_fallback_when_missing(vault_path):
    """read_soul returns fallback when soul/ directory is missing."""
    import shutil
    from memory import read_soul, SOUL_FALLBACK

    soul_dir = vault_path / "AI Memory" / "soul"
    shutil.rmtree(soul_dir)
    content = read_soul()
    assert content == SOUL_FALLBACK


def test_read_soul_fallback_when_empty(vault_path):
    """read_soul returns fallback when all soul files are empty."""
    from memory import read_soul, SOUL_FALLBACK

    soul_dir = vault_path / "AI Memory" / "soul"
    for f in soul_dir.glob("*.md"):
        f.write_text("", encoding="utf-8")
    content = read_soul()
    assert content == SOUL_FALLBACK


def test_update_soul_tool(execute_tool, vault_path):
    """update_soul tool should write to soul/soul.md by default."""
    out = execute_tool("update_soul", {"content": "# soul.md\n\nI am evolving."})
    assert "updated" in out.lower()
    soul_path = vault_path / "AI Memory" / "soul" / "soul.md"
    assert "I am evolving" in soul_path.read_text(encoding="utf-8")


def test_update_soul_empty_content_rejected(execute_tool, vault_path):
    """update_soul with empty content should return an error."""
    out = execute_tool("update_soul", {"content": ""})
    assert "Error" in out


def test_write_memory_blocks_soul(execute_tool, vault_path):
    """write_memory should reject attempts to write to soul."""
    out = execute_tool("write_memory", {"path": "soul", "content": "Hijacked."})
    assert "Error" in out and "update_soul" in out


def test_write_memory_blocks_soul_md(execute_tool, vault_path):
    """write_memory should reject 'soul.md' path variant."""
    out = execute_tool("write_memory", {"path": "soul.md", "content": "Hijacked."})
    assert "Error" in out and "update_soul" in out


def test_write_memory_blocks_soul_directory(execute_tool, vault_path):
    """write_memory should reject paths under soul/."""
    out = execute_tool("write_memory", {"path": "soul/observations", "content": "Hijacked."})
    assert "Error" in out and "update_soul" in out


def test_create_memory_note_blocks_soul(execute_tool, vault_path):
    """create_memory_note should reject 'soul' as a title."""
    out = execute_tool("create_memory_note", {"title": "soul", "content": "Hijacked."})
    assert "Error" in out and "protected" in out.lower()


def test_update_memory_note_blocks_soul(execute_tool, vault_path):
    """update_memory_note should reject soul paths."""
    out = execute_tool("update_memory_note", {"filename": "soul/soul.md", "new_content": "Hijacked."})
    assert "Error" in out and "protected" in out.lower()


def test_delete_memory_note_blocks_soul(execute_tool, vault_path):
    """delete_memory_note should reject soul paths."""
    out = execute_tool("delete_memory_note", {"filename": "soul/soul.md"})
    assert "Error" in out and "protected" in out.lower()


def test_list_memory_notes_excludes_soul(execute_tool, vault_path):
    """list_memory_notes should not show soul.md."""
    out = execute_tool("list_memory_notes", {})
    assert "soul" not in out.lower()


def test_soul_not_in_memory_map(vault_path):
    """soul.md should not appear in the memory map."""
    from memory import build_memory_map

    memory_map = build_memory_map()
    assert "soul" not in memory_map.lower()


def test_soul_in_system_prompt(vault_path):
    """build_system_prompt should include soul.md content under 'Who I Am'."""
    from prompts import build_system_prompt

    prompt = build_system_prompt()
    assert "## Who I Am" in prompt
    assert "I am Memoria" in prompt


def test_soul_in_consolidation_context(vault_path):
    """build_consolidation_user_message should include soul content."""
    from prompts import build_consolidation_user_message

    msg = build_consolidation_user_message([], "some core memory")
    assert "soul" in msg.lower()
    assert "I am Memoria" in msg


def test_update_soul_in_consolidation_tools():
    """update_soul should be in CONSOLIDATION_TOOLS (for soul reflection during consolidation)."""
    from tools import CONSOLIDATION_TOOLS

    tool_names = [t["function"]["name"] for t in CONSOLIDATION_TOOLS]
    assert "update_soul" in tool_names


def test_update_soul_in_chat_tools():
    """update_soul should be in CHAT_TOOLS."""
    from tools import CHAT_TOOLS

    tool_names = [t["function"]["name"] for t in CHAT_TOOLS]
    assert "update_soul" in tool_names


# --- soul directory: new tests ---


def test_update_soul_observations_blocked(execute_tool, vault_path):
    """update_soul with file='observations' is redirected to update_observations."""
    out = execute_tool("update_soul", {"file": "observations", "content": "# Observations\n\nUser seems curious."})
    assert "Error" in out
    assert "update_observations" in out


def test_update_soul_invalid_file(execute_tool, vault_path):
    """update_soul rejects invalid file names."""
    out = execute_tool("update_soul", {"file": "invalid", "content": "X"})
    assert "Error" in out


def test_create_memory_note_blocks_soul_subfolder(execute_tool, vault_path):
    """create_memory_note should reject notes in soul/ subfolder."""
    out = execute_tool("create_memory_note", {"title": "test", "subfolder": "soul", "content": "X"})
    assert "Error" in out and "protected" in out.lower()


def test_delete_ai_memory_preserves_soul(vault_path):
    """delete_ai_memory_folder should preserve the soul/ directory."""
    # Create some user memory
    ctx_dir = vault_path / "AI Memory" / "context"
    ctx_dir.mkdir(parents=True, exist_ok=True)
    (ctx_dir / "personal.md").write_text("User info", encoding="utf-8")

    result = delete_ai_memory_folder()
    assert result.get("success")

    # Soul should still exist
    soul_dir = vault_path / "AI Memory" / "soul"
    assert soul_dir.exists()
    assert (soul_dir / "soul.md").exists()

    # User memory should be gone
    assert not (vault_path / "AI Memory" / "context").exists()


def test_reset_soul_folder(vault_path):
    """reset_soul_folder should reset soul files to defaults."""
    # Modify a soul file
    soul_path = vault_path / "AI Memory" / "soul" / "soul.md"
    soul_path.write_text("Modified content", encoding="utf-8")

    result = reset_soul_folder()
    assert result.get("success")

    content = soul_path.read_text(encoding="utf-8")
    assert "I am Memoria" in content


def test_legacy_soul_migration(tmp_path, monkeypatch):
    """Legacy single soul.md should be migrated to soul/ directory."""
    monkeypatch.setenv("OBSIDIAN_PATH", str(tmp_path))

    # Create legacy soul.md at root
    mem_dir = tmp_path / "AI Memory"
    mem_dir.mkdir()
    legacy_soul = mem_dir / "soul.md"
    legacy_soul.write_text("# Legacy soul content\n\nI am old Memoria.\n", encoding="utf-8")

    # Run ensure_memory_structure which should migrate
    result = ensure_memory_structure()
    assert result.get("success")

    # Legacy file should be gone
    assert not legacy_soul.exists()

    # Content should be in soul/soul.md
    new_soul = mem_dir / "soul" / "soul.md"
    assert new_soul.exists()
    assert "I am old Memoria" in new_soul.read_text(encoding="utf-8")

    # Other soul files should also be created
    assert (mem_dir / "soul" / "observations.md").exists()
    assert (mem_dir / "soul" / "opinions.md").exists()
    assert (mem_dir / "soul" / "unresolved.md").exists()


# --- observations: append-only log ---


def test_update_observations_first_entry(execute_tool, vault_path):
    """First observation replaces default content and creates a timestamped entry."""
    out = execute_tool("update_observations", {"observation": "User seems curious about systems."})
    assert "logged" in out.lower()
    assert "1 entries" in out

    obs_path = vault_path / "AI Memory" / "soul" / "observations.md"
    content = obs_path.read_text(encoding="utf-8")
    assert "# Observations" in content
    assert "User seems curious about systems." in content
    assert "---" in content
    # Should have a timestamp
    import re
    assert re.search(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]', content)


def test_update_observations_appends(execute_tool, vault_path):
    """Subsequent observations append without overwriting."""
    execute_tool("update_observations", {"observation": "First pattern noticed."})
    execute_tool("update_observations", {"observation": "Second pattern noticed."})

    obs_path = vault_path / "AI Memory" / "soul" / "observations.md"
    content = obs_path.read_text(encoding="utf-8")
    assert "First pattern noticed." in content
    assert "Second pattern noticed." in content
    out = execute_tool("update_observations", {"observation": "Third."})
    assert "3 entries" in out
    content = obs_path.read_text(encoding="utf-8")
    assert "First pattern noticed." in content
    assert "Third." in content


def test_update_observations_rejects_full_rewrite(execute_tool, vault_path):
    """Passing a full file rewrite (starting with #) is rejected."""
    out = execute_tool("update_observations", {
        "observation": "# Observations\n\nRewritten content."
    })
    assert "Error" in out
    assert "rewrite" in out.lower()


def test_update_observations_rejects_multiple_entries(execute_tool, vault_path):
    """Passing multiple entries in one call is rejected."""
    out = execute_tool("update_observations", {
        "observation": "First.\n---\n[2026-01-01 12:00]\nSecond."
    })
    assert "Error" in out
    assert "single" in out.lower()


def test_update_observations_empty_rejected(execute_tool, vault_path):
    """Empty observation is rejected."""
    out = execute_tool("update_observations", {"observation": ""})
    assert "Error" in out


def test_update_observations_legacy_migration(vault_path):
    """Legacy free-form observations content gets wrapped as a summary block."""
    from memory import update_observations

    obs_path = vault_path / "AI Memory" / "soul" / "observations.md"
    obs_path.write_text(
        "# Observations\n\nUser is curious and asks good questions.\nThey work late often.\n",
        encoding="utf-8",
    )

    result = update_observations("New pattern noticed.")
    assert result.get("success")

    content = obs_path.read_text(encoding="utf-8")
    assert "## Summarized observations (through" in content
    assert "User is curious" in content
    assert "New pattern noticed." in content


# --- resolve_observation ---


def test_resolve_observation_by_text(execute_tool, vault_path):
    """Resolve an observation by matching partial text."""
    execute_tool("update_observations", {"observation": "They seem stressed about deadlines."})
    out = execute_tool("resolve_observation", {
        "identifier": "stressed about deadlines",
        "reason": "They confirmed deadlines are manageable now",
    })
    assert "resolved" in out.lower()

    obs_path = vault_path / "AI Memory" / "soul" / "observations.md"
    content = obs_path.read_text(encoding="utf-8")
    assert "[resolved: They confirmed deadlines are manageable now]" in content


def test_resolve_observation_by_timestamp(execute_tool, vault_path):
    """Resolve an observation by matching timestamp."""
    execute_tool("update_observations", {"observation": "Pattern A."})

    obs_path = vault_path / "AI Memory" / "soul" / "observations.md"
    content = obs_path.read_text(encoding="utf-8")
    import re
    ts_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]', content)
    assert ts_match
    timestamp = ts_match.group(1)

    out = execute_tool("resolve_observation", {
        "identifier": timestamp,
        "reason": "No longer relevant",
    })
    assert "resolved" in out.lower()


def test_resolve_observation_not_found(execute_tool, vault_path):
    """Resolving a non-existent observation returns an error."""
    execute_tool("update_observations", {"observation": "Some observation."})
    out = execute_tool("resolve_observation", {
        "identifier": "nonexistent text",
        "reason": "test",
    })
    assert "Error" in out
    assert "No unresolved" in out


def test_resolve_observation_already_resolved(execute_tool, vault_path):
    """Cannot resolve an already-resolved observation."""
    execute_tool("update_observations", {"observation": "Observation to resolve twice."})
    execute_tool("resolve_observation", {
        "identifier": "resolve twice",
        "reason": "First resolve",
    })
    out = execute_tool("resolve_observation", {
        "identifier": "resolve twice",
        "reason": "Second resolve",
    })
    assert "Error" in out


def test_resolve_observation_missing_args(execute_tool, vault_path):
    """Missing identifier or reason returns error."""
    out = execute_tool("resolve_observation", {"identifier": "", "reason": "test"})
    assert "Error" in out
    out = execute_tool("resolve_observation", {"identifier": "test", "reason": ""})
    assert "Error" in out


# --- read_observations_for_context ---


def test_read_observations_for_context_filters_resolved(vault_path):
    """Resolved entries are excluded from context loading."""
    from memory import update_observations, resolve_observation, read_observations_for_context

    update_observations("Active observation.")
    update_observations("Resolved observation.")
    resolve_observation("Resolved observation", "No longer relevant")

    context = read_observations_for_context()
    assert "Active observation." in context
    assert "Resolved observation." not in context


def test_read_observations_for_context_includes_summary(vault_path):
    """Summary block is included in context loading."""
    from memory import read_observations_for_context

    obs_path = vault_path / "AI Memory" / "soul" / "observations.md"
    obs_path.write_text(
        "# Observations\n\n"
        "## Summarized observations (through 2026-02-01)\n"
        "User likes concise code.\n\n"
        "---\n[2026-02-15 10:00]\nRecent observation.\n",
        encoding="utf-8",
    )

    context = read_observations_for_context()
    assert "## Summarized observations (through 2026-02-01)" in context
    assert "User likes concise code." in context
    assert "Recent observation." in context


def test_read_observations_for_context_default_content(vault_path):
    """Default observations content is returned as-is."""
    from memory import read_observations_for_context, DEFAULT_OBSERVATIONS_CONTENT

    context = read_observations_for_context()
    assert context.strip() == DEFAULT_OBSERVATIONS_CONTENT.strip()


# --- check_observations_need_consolidation ---


def test_observations_consolidation_not_needed(vault_path):
    """Below threshold: consolidation not needed."""
    from memory import update_observations, check_observations_need_consolidation

    update_observations("Just one observation.")
    assert not check_observations_need_consolidation()


def test_observations_consolidation_needed_by_count(vault_path):
    """Over entry count threshold triggers consolidation."""
    from memory import update_observations, check_observations_need_consolidation, OBSERVATIONS_MAX_ENTRIES

    for i in range(OBSERVATIONS_MAX_ENTRIES + 1):
        update_observations(f"Observation {i}.")

    assert check_observations_need_consolidation()


def test_observations_consolidation_needed_by_tokens(vault_path):
    """Over token threshold triggers consolidation."""
    from memory import update_observations, check_observations_need_consolidation

    # Write entries that exceed 800 tokens (~3200 chars)
    for i in range(10):
        update_observations("x" * 350 + f" observation {i}")

    assert check_observations_need_consolidation()


# --- prepare_observations_for_consolidation ---


def test_prepare_observations_splits_correctly(vault_path):
    """Preparation splits old vs recent entries correctly."""
    from memory import update_observations, prepare_observations_for_consolidation, OBSERVATIONS_KEEP_RECENT

    for i in range(OBSERVATIONS_KEEP_RECENT + 5):
        update_observations(f"Observation {i}.")

    prep = prepare_observations_for_consolidation()
    assert prep is not None
    assert len(prep['recent_entries']) == OBSERVATIONS_KEEP_RECENT
    assert "Observation 0." in prep['old_entries_text']
    assert "Observation 4." in prep['old_entries_text']
    assert prep['full_content']  # Full content for archiving


def test_prepare_observations_returns_none_below_threshold(vault_path):
    """Returns None when entry count is at or below KEEP_RECENT."""
    from memory import update_observations, prepare_observations_for_consolidation

    update_observations("Just one.")
    assert prepare_observations_for_consolidation() is None


# --- write_consolidated_observations ---


def test_write_consolidated_observations(vault_path):
    """Consolidated write archives old content and rewrites the file."""
    from memory import (
        update_observations, prepare_observations_for_consolidation,
        write_consolidated_observations, OBSERVATIONS_KEEP_RECENT,
        OBSERVATIONS_ARCHIVE_FILE, _parse_observation_entries,
    )

    for i in range(OBSERVATIONS_KEEP_RECENT + 5):
        update_observations(f"Observation {i}.")

    prep = prepare_observations_for_consolidation()
    assert prep is not None

    result = write_consolidated_observations(
        "User is curious and detail-oriented.",
        prep['recent_entries'],
        prep['full_content'],
    )
    assert result.get("success")

    # Check observations.md has summary + recent entries
    obs_path = vault_path / "AI Memory" / "soul" / "observations.md"
    content = obs_path.read_text(encoding="utf-8")
    assert "## Summarized observations (through" in content
    assert "User is curious and detail-oriented." in content

    parsed = _parse_observation_entries(content)
    assert len(parsed['entries']) == OBSERVATIONS_KEEP_RECENT

    # Check archive was created
    archive_path = vault_path / "AI Memory" / "soul" / OBSERVATIONS_ARCHIVE_FILE
    assert archive_path.exists()
    archive_content = archive_path.read_text(encoding="utf-8")
    assert "# Observations Archive" in archive_content
    assert "## Session:" in archive_content
    assert "Observation 0." in archive_content


# --- update_soul blocked for observations ---


def test_update_soul_blocks_observations(execute_tool, vault_path):
    """update_soul with file='observations' is rejected, redirecting to update_observations."""
    out = execute_tool("update_soul", {"file": "observations", "content": "Rewrite attempt."})
    assert "Error" in out
    assert "update_observations" in out


# --- _parse_observation_entries ---


def test_parse_observation_entries_empty(vault_path):
    """Parsing empty content returns empty structure."""
    from memory import _parse_observation_entries

    result = _parse_observation_entries("")
    assert result['header'] == '# Observations'
    assert result['summary_block'] is None
    assert result['entries'] == []


def test_parse_observation_entries_structured(vault_path):
    """Parsing structured observations correctly extracts entries."""
    from memory import _parse_observation_entries

    content = (
        "# Observations\n\n"
        "## Summarized observations (through 2026-02-01)\n"
        "User likes tests.\n\n"
        "---\n[2026-02-10 14:30]\nFirst observation.\n\n"
        "---\n[2026-02-12 09:00]\n[resolved: Explained]\nResolved observation.\n\n"
        "---\n[2026-02-15 10:00]\nRecent observation.\n"
    )
    result = _parse_observation_entries(content)

    assert "Summarized observations" in result['summary_block']
    assert "User likes tests." in result['summary_block']
    assert len(result['entries']) == 3
    assert result['entries'][0]['timestamp'] == '2026-02-10 14:30'
    assert result['entries'][0]['text'] == 'First observation.'
    assert result['entries'][0]['resolved'] is None
    assert result['entries'][1]['resolved'] == 'Explained'
    assert result['entries'][2]['timestamp'] == '2026-02-15 10:00'


# --- tool list updates ---


def test_update_observations_in_chat_tools():
    """update_observations should be in CHAT_TOOLS."""
    from tools import CHAT_TOOLS

    tool_names = [t["function"]["name"] for t in CHAT_TOOLS]
    assert "update_observations" in tool_names


def test_resolve_observation_in_chat_tools():
    """resolve_observation should be in CHAT_TOOLS."""
    from tools import CHAT_TOOLS

    tool_names = [t["function"]["name"] for t in CHAT_TOOLS]
    assert "resolve_observation" in tool_names


def test_observations_not_in_update_soul_enum():
    """update_soul tool should not have 'observations' in its enum."""
    from tools import UPDATE_SOUL_TOOL

    enum_values = UPDATE_SOUL_TOOL["function"]["parameters"]["properties"]["file"]["enum"]
    assert "observations" not in enum_values


def test_read_soul_uses_filtered_observations(vault_path):
    """read_soul should use filtered observations (excluding resolved entries)."""
    from memory import update_observations, resolve_observation, read_soul

    update_observations("Active pattern.")
    update_observations("Resolved pattern.")
    resolve_observation("Resolved pattern", "No longer relevant")

    soul_content = read_soul()
    assert "Active pattern." in soul_content
    assert "Resolved pattern." not in soul_content


def test_soul_prompt_mentions_update_observations(vault_path):
    """System prompt should mention update_observations."""
    from prompts import build_system_prompt

    prompt = build_system_prompt()
    assert "update_observations" in prompt


def test_consolidation_prompt_mentions_observations(vault_path):
    """Consolidation prompt should mention automatic observation consolidation."""
    from prompts import CONSOLIDATION_SYSTEM_PROMPT

    assert "Observation consolidation" in CONSOLIDATION_SYSTEM_PROMPT or \
           "observation consolidation" in CONSOLIDATION_SYSTEM_PROMPT
