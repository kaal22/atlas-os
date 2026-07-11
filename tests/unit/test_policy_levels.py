#!/usr/bin/env python3
"""Policy Gateway side-effect levels and approval defaults (product §17.8)."""

LEVELS = {
    0: "read_only_no_personal",
    1: "read_only_personal",
    2: "reversible_local_write",
    3: "external_or_meaningful_change",
    4: "destructive_or_privileged",
}

DEFAULT_APPROVAL = {
    0: "auto",
    1: "scoped_logged",
    2: "preference_or_task",
    3: "explicit",
    4: "explicit_reauth",
}

PROHIBITED_DEFAULT_TOOLS = {
    "shell.unrestricted",
    "docker.socket",
    "host.root_shell",
    "filesystem.delete_tree",
}


def approval_for(level: int) -> str:
    if level not in DEFAULT_APPROVAL:
        raise ValueError(f"invalid side-effect level: {level}")
    return DEFAULT_APPROVAL[level]


def is_prohibited(tool_id: str) -> bool:
    return tool_id in PROHIBITED_DEFAULT_TOOLS


def can_auto_run(level: int, tool_id: str) -> bool:
    if is_prohibited(tool_id):
        return False
    return approval_for(level) == "auto"


def test_levels_complete():
    assert set(LEVELS) == set(DEFAULT_APPROVAL) == {0, 1, 2, 3, 4}


def test_auto_only_level_zero():
    assert can_auto_run(0, "knowledge.search") is True
    assert can_auto_run(1, "documents.read") is False
    assert can_auto_run(3, "network.fetch") is False


def test_prohibited_never_auto():
    assert can_auto_run(0, "shell.unrestricted") is False
    assert is_prohibited("docker.socket")


def test_invalid_level():
    try:
        approval_for(9)
        assert False
    except ValueError:
        pass


if __name__ == "__main__":
    test_levels_complete()
    test_auto_only_level_zero()
    test_prohibited_never_auto()
    test_invalid_level()
    print("OK test_policy_levels")
