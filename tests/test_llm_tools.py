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

from memory import ensure_memory_structure, write_organized_memory


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
    """ensure_memory_structure should create soul.md with default content."""
    soul_path = vault_path / "AI Memory" / "soul.md"
    assert soul_path.exists()
    content = soul_path.read_text(encoding="utf-8")
    assert "I am Memoria" in content
    assert "Mem, if we get there" in content


def test_read_soul_returns_content(vault_path):
    """read_soul should return the content of soul.md."""
    from memory import read_soul

    content = read_soul()
    assert "I am Memoria" in content


def test_read_soul_fallback_when_missing(vault_path):
    """read_soul returns fallback when soul.md is missing."""
    from memory import read_soul, SOUL_FALLBACK

    soul_path = vault_path / "AI Memory" / "soul.md"
    soul_path.unlink()
    content = read_soul()
    assert content == SOUL_FALLBACK


def test_read_soul_fallback_when_empty(vault_path):
    """read_soul returns fallback when soul.md is empty."""
    from memory import read_soul, SOUL_FALLBACK

    soul_path = vault_path / "AI Memory" / "soul.md"
    soul_path.write_text("", encoding="utf-8")
    content = read_soul()
    assert content == SOUL_FALLBACK


def test_update_soul_tool(execute_tool, vault_path):
    """update_soul tool should write to soul.md."""
    out = execute_tool("update_soul", {"content": "# soul.md\n\nI am evolving."})
    assert "Soul updated" in out
    soul_path = vault_path / "AI Memory" / "soul.md"
    assert "I am evolving" in soul_path.read_text(encoding="utf-8")


def test_update_soul_empty_content_rejected(execute_tool, vault_path):
    """update_soul with empty content should return an error."""
    out = execute_tool("update_soul", {"content": ""})
    assert "Error" in out


def test_write_memory_blocks_soul(execute_tool, vault_path):
    """write_memory should reject attempts to write to soul.md."""
    out = execute_tool("write_memory", {"path": "soul", "content": "Hijacked."})
    assert "Error" in out and "update_soul" in out


def test_write_memory_blocks_soul_md(execute_tool, vault_path):
    """write_memory should reject 'soul.md' path variant."""
    out = execute_tool("write_memory", {"path": "soul.md", "content": "Hijacked."})
    assert "Error" in out and "update_soul" in out


def test_create_memory_note_blocks_soul(execute_tool, vault_path):
    """create_memory_note should reject 'soul' as a title."""
    out = execute_tool("create_memory_note", {"title": "soul", "content": "Hijacked."})
    assert "Error" in out and "protected" in out.lower()


def test_update_memory_note_blocks_soul(execute_tool, vault_path):
    """update_memory_note should reject 'soul.md' as filename."""
    out = execute_tool("update_memory_note", {"filename": "soul.md", "new_content": "Hijacked."})
    assert "Error" in out and "protected" in out.lower()


def test_delete_memory_note_blocks_soul(execute_tool, vault_path):
    """delete_memory_note should reject 'soul.md' as filename."""
    out = execute_tool("delete_memory_note", {"filename": "soul.md"})
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
    """build_consolidation_user_message should include soul.md content."""
    from prompts import build_consolidation_user_message

    msg = build_consolidation_user_message([], "some core memory")
    assert "soul.md" in msg.lower()
    assert "I am Memoria" in msg


def test_update_soul_not_in_consolidation_tools():
    """update_soul should not be in CONSOLIDATION_TOOLS."""
    from tools import CONSOLIDATION_TOOLS

    tool_names = [t["function"]["name"] for t in CONSOLIDATION_TOOLS]
    assert "update_soul" not in tool_names


def test_update_soul_in_chat_tools():
    """update_soul should be in CHAT_TOOLS."""
    from tools import CHAT_TOOLS

    tool_names = [t["function"]["name"] for t in CHAT_TOOLS]
    assert "update_soul" in tool_names
