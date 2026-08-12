"""Command and path safety. Ambiguity is never permission (spec 16)."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from .errors import SafetyError

_COMMAND_REJECT = set(";<|>`$\\")
_DENIED_EXE = {
    "sh", "bash", "dash", "zsh", "ksh", "csh", "tcsh", "ash", "busybox", "fish",
}


def _controls() -> set:
    return {chr(i) for i in range(32)} | {"\x7f"}


def within_repo(target, repo_root) -> bool:
    repo = Path(repo_root).resolve()
    try:
        resolved = (repo / str(target)).resolve(strict=False)
        resolved.relative_to(repo)
        return True
    except (OSError, ValueError):
        return False


def validate_targets(targets, repo_root, field_name="implementation_targets"):
    """Return list of (target, reason) confinement violations."""
    repo = Path(repo_root).resolve()
    violations = []
    for t in targets or []:
        p = str(t)
        ap = Path(p)
        if ap.is_absolute():
            violations.append((p, "absolute path not allowed"))
            continue
        if ".." in ap.parts:
            violations.append((p, "path traversal (..) not allowed"))
            continue
        if "~" in ap.parts:
            violations.append((p, "home (~) path not allowed"))
            continue
        if ".git" in ap.parts:
            violations.append((p, "writes inside .git are prohibited"))
            continue
        full = repo / p
        try:
            resolved = full.resolve(strict=False)
            resolved.relative_to(repo)
        except (OSError, ValueError):
            violations.append((p, "target escapes repository"))
            continue
        if full.is_symlink():
            try:
                tgt = full.resolve(strict=False)
                tgt.relative_to(repo)
            except (ValueError, OSError):
                violations.append((p, "symlink escapes repository"))
    return violations


def validate_command(command, allow=None):
    """Validate a command. Returns shlex tokens. Exact allowlist (ADR-0011)."""
    if not isinstance(command, str):
        raise SafetyError("command must be a string")
    if not command.strip():
        raise SafetyError("empty command")
    if "\x00" in command:
        raise SafetyError("null byte in command")
    for ch in command:
        if ch in _COMMAND_REJECT:
            raise SafetyError(f"forbidden shell character {ch!r}")
        if ch in _controls():
            raise SafetyError(f"forbidden control character (ord {ord(ch)})")
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        raise SafetyError(f"malformed command tokens: {e}") from e
    if not tokens:
        raise SafetyError("empty command")

    exe = tokens[0]
    if exe.startswith(".") or "/" in exe or "\\" in exe or os.sep in exe:
        raise SafetyError(f"executable must be a bare tool name: {exe!r}")
    if exe in _DENIED_EXE:
        raise SafetyError(f"shell interpreter executables are prohibited: {exe!r}")

    allow_list = list(allow or [])
    if not allow_list:
        raise SafetyError("no allowlist provided; no tool is authorized")
    if exe not in allow_list:
        raise SafetyError(f"executable {exe!r} not in allowlist {allow_list}")

    for tok in tokens[1:]:
        if tok.startswith("/") or (len(tok) >= 2 and tok[1] == ":"):
            raise SafetyError(f"absolute path argument not allowed: {tok!r}")
        if ".." in tok.split("/"):
            raise SafetyError(f"path traversal argument not allowed: {tok!r}")
    return tokens
