"""
Unit tests for _extract_json() in wisper.launcher.

All tests are offline (no network, no UI, no audio).
Run with:  uv run pytest tests/test_extract_json.py -v
"""
from __future__ import annotations

import re

import pytest

from wisper.launcher import _extract_json


def _strip_think(text: str) -> str:
    """Mirror the <think>-stripping logic in _call_llm."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

DISCORD_OPEN = {"app_name": "Discord", "action": "open"}
DISCORD_CLOSE = {"app_name": "Discord", "action": "close"}


# ── Happy-path inputs ─────────────────────────────────────────────────────────

class TestCleanJson:
    """Model outputs clean JSON — should always parse directly."""

    def test_plain_double_quotes(self):
        assert _extract_json('{"app_name": "Discord", "action": "open"}') == DISCORD_OPEN

    def test_plain_with_spaces(self):
        assert _extract_json(
            '{ "app_name": "Discord",  "action": "open" }'
        ) == DISCORD_OPEN

    def test_action_close(self):
        assert _extract_json('{"app_name": "Discord", "action": "close"}') == DISCORD_CLOSE


class TestMarkdownFenced:
    """Model wraps output in a code fence."""

    def test_json_fence(self):
        src = '```json\n{"app_name": "Discord", "action": "open"}\n```'
        assert _extract_json(src) == DISCORD_OPEN

    def test_plain_fence(self):
        src = '```\n{"app_name": "Discord", "action": "open"}\n```'
        assert _extract_json(src) == DISCORD_OPEN

    def test_fence_single_quotes(self):
        src = "```\n{'app_name': 'Discord', 'action': 'open'}\n```"
        assert _extract_json(src) == DISCORD_OPEN


class TestProseWrapped:
    """Model adds prose before/after the JSON — common with small instruct models."""

    def test_prose_prefix(self):
        src = 'Sure! {"app_name": "Discord", "action": "open"}'
        assert _extract_json(src) == DISCORD_OPEN

    def test_prose_prefix_and_suffix(self):
        src = 'Here it is: {"app_name": "Discord", "action": "open"} Hope that helps!'
        assert _extract_json(src) == DISCORD_OPEN

    def test_prose_multiline(self):
        src = (
            "Based on the command you gave me,\n"
            'I will open Discord for you: {"app_name": "Discord", "action": "open"}'
        )
        assert _extract_json(src) == DISCORD_OPEN


class TestSingleQuotes:
    """Tiny models may output Python-style dicts with single quotes."""

    def test_pure_single_quote_dict(self):
        src = "{'app_name': 'Discord', 'action': 'open'}"
        assert _extract_json(src) == DISCORD_OPEN

    def test_single_quotes_with_prose_prefix(self):
        # THE KEY BUG CASE: apostrophe in prose must not be corrupted.
        src = "Here's the result: {'app_name': 'Discord', 'action': 'open'}"
        assert _extract_json(src) == DISCORD_OPEN

    def test_single_quotes_with_prose_prefix_and_suffix(self):
        src = "Sure, here's what I found: {'app_name': 'Discord', 'action': 'open'} enjoy!"
        assert _extract_json(src) == DISCORD_OPEN


# ── Reasoning models (<think> blocks) ────────────────────────────────────────

class TestReasoningModels:
    """
    Models like nemotron-reasoning, deepseek-r1, qwq prepend a <think>...</think>
    block.  _call_llm strips it before passing content to _extract_json.
    These tests replicate that pipeline to catch regressions.
    """

    def test_think_block_with_correct_answer_after(self):
        src = (
            "<think>The user says 'Nova Ferme Discord'. "
            "Ferme means close in French. The action is close.</think>\n"
            '{"app_name": "Discord", "action": "close"}'
        )
        assert _extract_json(_strip_think(src)) == DISCORD_CLOSE

    def test_think_block_contains_wrong_action_as_candidate(self):
        # The reasoning chain mentions "open" while working through the problem.
        # Only the final answer after </think> should be parsed.
        src = (
            "<think>Could be open? "
            '{"app_name": "Discord", "action": "open"} '
            "No, ferme = close.</think>\n"
            '{"app_name": "Discord", "action": "close"}'
        )
        assert _extract_json(_strip_think(src)) == DISCORD_CLOSE

    def test_think_block_stripped_leaves_clean_json(self):
        src = "<think>Thinking...</think>\n" + '{"app_name": "Discord", "action": "open"}'
        assert _extract_json(_strip_think(src)) == DISCORD_OPEN

    def test_no_think_block_unchanged(self):
        src = '{"app_name": "Discord", "action": "open"}'
        assert _extract_json(_strip_think(src)) == DISCORD_OPEN


# ── Failure cases — must return None, not crash ───────────────────────────────

class TestFailureCases:
    """Garbage inputs — parser must return None gracefully."""

    def test_empty_string(self):
        assert _extract_json("") is None

    def test_plain_text_no_json(self):
        assert _extract_json("I don't know what you mean") is None

    def test_only_braces_no_content(self):
        # Empty object is a valid dict, but has no required keys — that's fine,
        # the *caller* checks for the keys. The parser just returns a dict.
        result = _extract_json("{}")
        assert isinstance(result, dict)

    def test_malformed_json(self):
        assert _extract_json('{"app_name": "Discord", "action":}') is None

    def test_just_a_number(self):
        assert _extract_json("42") is None

    def test_list_extracts_inner_dict(self):
        # Some models wrap the object in a JSON array.
        # The regex finds the first {...} block, so we extract it anyway — useful.
        result = _extract_json('[{"app_name": "Discord", "action": "open"}]')
        assert result == DISCORD_OPEN
