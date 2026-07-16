#!/usr/bin/env python3
"""Agent task finite state machine (product §17.6)."""

STATES = {
    "draft",
    "planned",
    "awaiting_approval",
    "queued",
    "running",
    "waiting_for_user",
    "paused",
    "completed",
    "failed",
    "cancelled",
    "rolled_back",
}

TRANSITIONS = {
    "draft": {"planned", "cancelled"},
    "planned": {"awaiting_approval", "queued", "cancelled"},
    "awaiting_approval": {"queued", "cancelled", "draft", "running"},
    "queued": {"running", "cancelled"},
    "running": {"waiting_for_user", "paused", "completed", "failed", "cancelled", "awaiting_approval"},
    "waiting_for_user": {"running", "cancelled", "failed"},
    "paused": {"running", "cancelled"},
    "completed": {"rolled_back"},
    "failed": {"draft", "rolled_back"},
    "cancelled": set(),
    "rolled_back": set(),
}


def can_transition(src: str, dst: str) -> bool:
    return dst in TRANSITIONS.get(src, set())


def test_happy_path():
    path = ["draft", "planned", "queued", "running", "completed"]
    for a, b in zip(path, path[1:]):
        assert can_transition(a, b), f"{a} -> {b}"


def test_approval_gate():
    assert can_transition("planned", "awaiting_approval")
    assert can_transition("awaiting_approval", "queued")
    assert not can_transition("awaiting_approval", "completed")


def test_terminal():
    assert not can_transition("cancelled", "running")
    assert can_transition("completed", "rolled_back")


if __name__ == "__main__":
    test_happy_path()
    test_approval_gate()
    test_terminal()
    print("OK test_task_fsm")
