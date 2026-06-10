"""
Unit tests for the orchestrator routing regexes.

Verifies that:
- _NOTE_RE matches exactly what should be routed to NoteManager
- _NOVA_PREFIX_RE matches exactly what should be routed to AppLauncher
- Note trigger has priority over app-launcher trigger

Run with:  uv run pytest tests/test_routing.py -v
"""
from __future__ import annotations

import re

import pytest

from wisper.orchestrator import _NOTE_RE, _NOVA_PREFIX_RE


# ── Note trigger ──────────────────────────────────────────────────────────────

class TestNoteRegex:
    """_NOTE_RE must match all "nova note[s]" variants."""

    def test_bare_nova_note(self):
        assert _NOTE_RE.match("nova note") is not None

    def test_bare_nova_notes(self):
        assert _NOTE_RE.match("nova notes") is not None

    def test_uppercase(self):
        assert _NOTE_RE.match("Nova Note") is not None

    def test_asr_variant_missing_e(self):
        # ASR sometimes drops the final 'e'
        assert _NOTE_RE.match("nova not") is not None

    def test_with_content(self):
        m = _NOTE_RE.match("nova note buy milk")
        assert m is not None
        assert m.group(1) == "buy milk"

    def test_with_content_comma_separator(self):
        m = _NOTE_RE.match("Nova note, call dentist")
        assert m is not None
        assert m.group(1) == "call dentist"

    def test_nova_note_no_notebook(self):
        # "nova notebook" must NOT match (would hijack typed sentence)
        assert _NOTE_RE.match("nova notebook") is None

    def test_plain_note_no_nova(self):
        assert _NOTE_RE.match("note buy milk") is None


# ── App-launcher trigger ──────────────────────────────────────────────────────

class TestNovaPrefix:
    """_NOVA_PREFIX_RE must match any utterance starting with 'nova'."""

    def test_nova_open_discord(self):
        assert _NOVA_PREFIX_RE.match("nova open discord") is not None

    def test_nova_ferme_chrome(self):
        assert _NOVA_PREFIX_RE.match("nova ferme chrome") is not None

    def test_nova_launch_spotify(self):
        assert _NOVA_PREFIX_RE.match("nova launch spotify") is not None

    def test_uppercase(self):
        assert _NOVA_PREFIX_RE.match("Nova Open Discord") is not None

    def test_does_not_match_plain_text(self):
        assert _NOVA_PREFIX_RE.match("hello world") is None

    def test_does_not_match_partial_word(self):
        # "novas" starts with "nova" but "nova\b" requires a word boundary
        assert _NOVA_PREFIX_RE.match("novas") is None


# ── Priority: note trigger wins over app-launcher trigger ────────────────────

class TestRoutingPriority:
    """
    Simulate the orchestrator routing logic: note check runs FIRST.
    "nova note ..." must never reach AppLauncher even though it also
    starts with "nova".
    """

    def _route(self, cleaned: str) -> str:
        """Mirror the on_release() routing logic. Returns the winning route."""
        m = _NOTE_RE.match(cleaned)
        if m is not None:
            return "note"
        if _NOVA_PREFIX_RE.match(cleaned):
            return "launcher"
        return "inject"

    def test_nova_note_routes_to_notes(self):
        assert self._route("nova note") == "note"

    def test_nova_note_with_content_routes_to_notes(self):
        assert self._route("nova note buy milk") == "note"

    def test_nova_open_routes_to_launcher(self):
        assert self._route("nova open discord") == "launcher"

    def test_plain_text_routes_to_inject(self):
        assert self._route("hello world") == "inject"

    def test_nova_notes_routes_to_notes_not_launcher(self):
        assert self._route("nova notes") == "note"
