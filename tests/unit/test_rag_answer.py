#!/usr/bin/env python3
"""RAG answers should summarize, not dump raw source links."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-agent-runtime" / "usr" / "lib" / "atlas"))

from agent_runtime import (  # noqa: E402
    _fallback_summary_from_sources,
    _looks_like_source_dump,
    _rag_answer_instructions,
)

SOURCES = [
    {
        "name": "notes.md",
        "path": "/home/u/Documents/notes.md",
        "text": "Atlas OS keeps AI local and private on your device.",
        "chunk_index": 0,
    }
]


def test_detects_bullet_source_dump():
    dump = "- notes.md (chunk 0): Atlas OS keeps AI local\n- other.md (chunk 1): more text"
    assert _looks_like_source_dump(dump, SOURCES) is True


def test_accepts_prose_summary():
    prose = "According to notes.md, Atlas OS is designed to keep AI local and private on your device."
    assert _looks_like_source_dump(prose, SOURCES) is False


def test_fallback_builds_summary():
    out = _fallback_summary_from_sources("What is Atlas?", SOURCES)
    assert "notes.md" in out
    assert "local" in out.lower()
    assert not out.startswith("-")


def test_instructions_ask_for_prose():
    assert "summarizing" in _rag_answer_instructions().lower()
    assert "Sources section" in _rag_answer_instructions()


if __name__ == "__main__":
    test_detects_bullet_source_dump()
    test_accepts_prose_summary()
    test_fallback_builds_summary()
    test_instructions_ask_for_prose()
    print("OK test_rag_answer")
