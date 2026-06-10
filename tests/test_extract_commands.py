"""
Unit tests for _extract_commands() in wisper.launcher.

All tests are offline.
Run with:  uv run pytest tests/test_extract_commands.py -v
"""
from __future__ import annotations

import pytest

from wisper.launcher import _extract_commands

DISCORD_OPEN  = {"app_name": "Discord", "action": "open"}
DISCORD_CLOSE = {"app_name": "Discord", "action": "close"}
STEAM_OPEN    = {"app_name": "Steam",   "action": "open"}


class TestSingleCommand:
    """Single-app responses still work after the move to arrays."""

    def test_clean_array_one_element(self):
        assert _extract_commands('[{"app_name": "Discord", "action": "open"}]') == [DISCORD_OPEN]

    def test_plain_dict_wrapped_in_list(self):
        assert _extract_commands('{"app_name": "Discord", "action": "open"}') == [DISCORD_OPEN]

    def test_markdown_fenced_array(self):
        src = '```json\n[{"app_name": "Discord", "action": "open"}]\n```'
        assert _extract_commands(src) == [DISCORD_OPEN]

    def test_prose_prefix(self):
        src = 'Sure! [{"app_name": "Discord", "action": "open"}]'
        assert _extract_commands(src) == [DISCORD_OPEN]


class TestMultipleCommands:
    """Chained voice commands: 'nova open Discord and Steam'."""

    def test_two_opens(self):
        src = '[{"app_name": "Discord", "action": "open"}, {"app_name": "Steam", "action": "open"}]'
        assert _extract_commands(src) == [DISCORD_OPEN, STEAM_OPEN]

    def test_open_and_close(self):
        src = '[{"app_name": "Discord", "action": "open"}, {"app_name": "Discord", "action": "close"}]'
        assert _extract_commands(src) == [DISCORD_OPEN, DISCORD_CLOSE]

    def test_array_with_prose(self):
        src = (
            "Here are the commands: "
            '[{"app_name": "Discord", "action": "open"}, {"app_name": "Steam", "action": "open"}]'
            " — done!"
        )
        assert _extract_commands(src) == [DISCORD_OPEN, STEAM_OPEN]

    def test_fallback_two_separate_blocks(self):
        # Some models emit multiple {...} blocks instead of an array
        src = '{"app_name": "Discord", "action": "open"} {"app_name": "Steam", "action": "open"}'
        result = _extract_commands(src)
        assert DISCORD_OPEN in result
        assert STEAM_OPEN   in result


class TestFailureCases:
    def test_empty_string(self):
        assert _extract_commands("") == []

    def test_garbage(self):
        assert _extract_commands("I don't understand") == []

    def test_missing_action_key(self):
        # Dict without "action" is not a valid command
        assert _extract_commands('[{"app_name": "Discord"}]') == []

    def test_missing_app_name_key(self):
        assert _extract_commands('[{"action": "open"}]') == []
