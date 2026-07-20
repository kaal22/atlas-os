#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-command-centre" / "usr" / "lib" / "atlas"))

from chat_store import ChatStore  # noqa: E402


def test_chat_store_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        store = ChatStore(Path(td))
        thread = store.create_thread("alice", agent="atlas.guide")
        assert thread["id"]
        saved = store.save_thread(
            "alice",
            thread["id"],
            [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi there"}],
        )
        assert saved
        assert saved["title"] == "hello"
        listed = store.list_threads("alice")
        assert len(listed) == 1
        assert listed[0]["title"] == "hello"
        got = store.get_thread("alice", thread["id"])
        assert got and len(got["messages"]) == 2
        assert store.delete_thread("alice", thread["id"])
        assert store.get_thread("alice", thread["id"]) is None


def test_chat_store_rename_without_messages():
    with tempfile.TemporaryDirectory() as td:
        store = ChatStore(Path(td))
        thread = store.create_thread("alice", agent="atlas.guide")
        store.save_thread(
            "alice",
            thread["id"],
            [{"role": "user", "content": "hello"}],
        )
        renamed = store.save_thread("alice", thread["id"], title="Morning chat")
        assert renamed
        assert renamed["title"] == "Morning chat"
        assert len(renamed["messages"]) == 1


if __name__ == "__main__":
    test_chat_store_roundtrip()
    test_chat_store_rename_without_messages()
    print("OK test_chat_store")
