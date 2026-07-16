#!/usr/bin/env python3
"""Command Centre must not shell out to docker/ufw/root privileged tools."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CC = ROOT / "packages" / "atlas-command-centre" / "usr" / "lib" / "atlas" / "command_centre.py"

FORBIDDEN_BINARIES = {
    "docker",
    "docker-compose",
    "ufw",
    "iptables",
    "nft",
    "sudo",
    "su",
    "pkexec",
}


def _collect_string_literals(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
        # subprocess call first arg lists
        if isinstance(node, (ast.List, ast.Tuple)):
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.add(elt.value)
    return out


def test_cc_source_has_no_docker_ufw_subprocess():
    src = CC.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # No subprocess / os.system import usage for privileged tools
    imports_subprocess = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    imports_subprocess = True
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            imports_subprocess = True
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "os" and node.attr in {"system", "popen"}:
                raise AssertionError("command_centre must not use os.system/popen")

    literals = _collect_string_literals(tree)
    # Path-like invocations
    for lit in literals:
        base = Path(lit).name
        assert base not in FORBIDDEN_BINARIES, f"CC references forbidden binary {base!r}"

    # Explicit grep-style checks on source
    lower = src.lower()
    assert "docker.sock" not in lower
    assert "subprocess" not in src or not imports_subprocess
    # Even without import, do not hardcode privileged CLIs
    for bad in ("/usr/sbin/ufw", "/usr/bin/docker", "ufw --force", "docker compose"):
        assert bad not in src, f"CC must not contain {bad!r}"


def test_privileged_hint_uses_daemon():
    src = CC.read_text(encoding="utf-8")
    assert "system_daemon" in src or "atlas-system-daemon" in src or "use_system_daemon" in src


if __name__ == "__main__":
    test_cc_source_has_no_docker_ufw_subprocess()
    test_privileged_hint_uses_daemon()
    print("OK test_cc_no_privileged_subprocess")
