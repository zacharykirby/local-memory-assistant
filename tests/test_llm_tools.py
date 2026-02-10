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
    from chat import execute_tool as _execute_tool
    return _execute_tool


@pytest.fixture
def parse_tool_arguments():
    from chat import parse_tool_arguments
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
    # New vault has minimal core-memory; read_core_memory returns it or empty message
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
    # 500 token limit, ~4 chars per token -> 2000+ chars fails
    big = "x" * 2500
    out = execute_tool("update_core_memory", {"content": big})
    assert "Error" in out and "exceeds" in out


# --- read_context ---


def test_read_context_empty_category(execute_tool, vault_path):
    out = execute_tool("read_context", {"category": "personal"})
    assert "context" in out and "personal" in out


def test_read_context_invalid_category(execute_tool, vault_path):
    out = execute_tool("read_context", {"category": "invalid"})
    assert "Error" in out and "Invalid category" in out


def test_read_context_with_content(execute_tool, vault_path):
    execute_tool("update_context", {"category": "work", "content": "Engineer at Acme."})
    out = execute_tool("read_context", {"category": "work"})
    assert "Engineer at Acme" in out


# --- update_context ---


def test_update_context_success(execute_tool, vault_path):
    out = execute_tool("update_context", {"category": "preferences", "content": "Concise."})
    assert "Updated" in out


# --- archive_memory ---


def test_archive_memory_success(execute_tool, vault_path):
    out = execute_tool("archive_memory", {"content": "Old summary."})
    assert "Archived" in out


# --- search_vault ---


def test_search_vault_no_query(execute_tool, vault_path):
    out = execute_tool("search_vault", {})
    assert "Error" in out and "query" in out.lower()


def test_search_vault_with_query(execute_tool, vault_path):
    # Empty vault: no results
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


# --- update_memory_note ---


def test_update_memory_note_missing_args(execute_tool, vault_path):
    out = execute_tool("update_memory_note", {})
    assert "Error" in out and "required" in out


def test_update_memory_note_success(execute_tool, vault_path):
    execute_tool("create_memory_note", {"title": "ToUpdate", "content": "Old."})
    out = execute_tool("update_memory_note", {
        "filename": "ToUpdate.md",
        "new_content": "New content."
    })
    assert "Updated" in out
    out_read = execute_tool("read_memory_note", {"filename": "ToUpdate.md"})
    assert "New content" in out_read


# --- append_to_memory_note ---


def test_append_to_memory_note_missing_args(execute_tool, vault_path):
    out = execute_tool("append_to_memory_note", {})
    assert "Error" in out and "required" in out


def test_append_to_memory_note_success(execute_tool, vault_path):
    execute_tool("create_memory_note", {"title": "AppendMe", "content": "First."})
    out = execute_tool("append_to_memory_note", {"filename": "AppendMe.md", "content": " Second."})
    assert "Updated" in out or "Appended" in out or "Error" not in out


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


# --- read_specific_context ---


def test_read_specific_context_no_content(execute_tool, vault_path):
    out = execute_tool("read_specific_context", {"category": "work", "subcategory": "projects"})
    assert "No content" in out or "context" in out


def test_read_specific_context_with_content(execute_tool, vault_path):
    execute_tool("update_specific_context", {
        "category": "work", "subcategory": "projects", "content": "Project A."
    })
    out = execute_tool("read_specific_context", {"category": "work", "subcategory": "projects"})
    assert "Project A" in out


# --- update_specific_context ---


def test_update_specific_context_success(execute_tool, vault_path):
    out = execute_tool("update_specific_context", {
        "category": "work", "subcategory": "goals", "content": "Ship v1."
    })
    assert "Updated" in out


# --- add_goal ---


def test_add_goal_success(execute_tool, vault_path):
    out = execute_tool("add_goal", {
        "goal_description": "Finish tests",
        "timeline": "This week",
        "goal_type": "current"
    })
    assert "Goal added" in out or "Updated" in out or "timeline" in out.lower()


# --- write_organized_memory path traversal ---


def test_write_organized_memory_path_traversal_prevention(vault_path):
    """Test that malicious paths from LLM are blocked."""
    malicious_memory = {
        "core_memory": "Safe content",
        "context": {
            "../../etc/passwd": "Malicious content",  # Path traversal
            "/etc/shadow": "Absolute path",  # Absolute path
            "work/projects": "Safe content",  # Valid nested path
            "personal": "Safe content",  # Valid simple path
            "~/.ssh/keys": "Home directory escape",  # Home dir escape
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
        # Only allow matches inside memory_dir, not outside
        outside = [p for p in escaped if memory_dir not in p.parents and p != memory_dir]
        assert not outside, f"Path traversal created file outside AI Memory: {outside}"


# --- unknown tool ---


def test_unknown_tool(execute_tool, vault_path):
    out = execute_tool("nonexistent_tool", {})
    assert "Unknown tool" in out and "nonexistent_tool" in out


# --- consolidation agentic loop ---


def test_consolidation_is_agentic(vault_path):
    """Consolidation uses an agentic loop: tool results are fed back to the LLM (read-then-write works)."""
    from chat import run_agent_loop, CONSOLIDATION_TOOLS

    call_count = 0

    def mock_call_llm(messages, tools=None, stream=False, live_display=None, max_tokens=500):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First response: LLM asks to read core memory
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
        # Second response: LLM had seen the read result, now responds without more tools
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

    with patch("chat.call_llm", side_effect=mock_call_llm):
        result = run_agent_loop(
            initial_messages=initial_messages,
            tools=CONSOLIDATION_TOOLS,
            max_iterations=10,
            stream_first_response=False,
            show_tool_calls=False,
        )

    assert result["iterations"] == 2, "Loop should run twice: once with tool call, once with final response"
    assert call_count == 2, "LLM should be called twice (second time with tool result in messages)"

    # Tool result must have been appended so the second LLM call could see it
    tool_messages = [m for m in result["messages"] if m.get("role") == "tool"]
    assert len(tool_messages) == 1, "Exactly one tool result should be in history"
    assert tool_messages[0].get("tool_call_id") == "call_0"
    assert "Core" in tool_messages[0].get("content", "") or "empty" in tool_messages[0].get("content", "").lower()


# --- truncate_messages (context window management) ---


def test_truncate_messages():
    """Test message truncation preserves system and keeps recent messages."""
    from chat import truncate_messages

    # Build test conversation: system + 60 conversation messages (30 turns)
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

    # Truncate to 20 messages
    result = truncate_messages(messages, max_messages=20)

    # Verify system message preserved
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "System prompt"

    # Verify only 20 conversation messages kept
    conversation = [m for m in result if m["role"] != "system"]
    assert len(conversation) == 20

    # Verify most recent messages kept
    assert conversation[-1]["content"] == "Response 32"
    assert conversation[-2]["content"] == "Message 32"

    # Verify oldest messages dropped
    assert not any(m.get("content") == "Message 1" for m in result)
    assert not any(m.get("content") == "Response 1" for m in result)


def test_truncate_messages_no_truncation_needed():
    """When under limit, messages are returned unchanged."""
    from chat import truncate_messages

    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    result = truncate_messages(messages, max_messages=50)
    assert result == messages


def test_truncate_messages_empty():
    """Empty list returns empty list."""
    from chat import truncate_messages

    assert truncate_messages([]) == []
    assert truncate_messages([], max_messages=10) == []
