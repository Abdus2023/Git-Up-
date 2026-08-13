"""Safety primitives: command validation and repository path confinement.

These are fail-closed validators. They never transform ambiguity into
permission. They are pure (no I/O side effects) except path confinement
which reads the filesystem to detect symlink escape.
"""
from __future__ import annotations

import hashlib
import os
import shlex
from pathlib import Path
from typing import Optional


class SafetyError(ValueError):
    """Raised when a command or path violates a safety property."""


# Shell metacharacters / redirection that must never appear in a validated
# command. Backslash is included because it is a shell escape character.
_COMMAND_REJECT_CHARS = set(";&|>`$<\\")


def _control_chars() -> set:
    # ASCII control characters (excludes space); covers \n \r \t \0 etc.
    return {chr(i) for i in range(32)} | {"\x7f"}


def within_repo(target, repo_root) -> bool:
    """True iff ``target`` resolves to a path inside ``repo_root``."""
    repo = Path(repo_root).resolve()
    try:
        resolved = (repo / str(target)).resolve(strict=False)
    except (OSError, ValueError):
        return False
    try:
        resolved.relative_to(repo)
        return True
    except ValueError:
        return False


def _hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def target_hashes(targets, repo_root) -> dict:
    """Deterministic observed-state map for declared implementation targets.

    For each target: ``None`` if absent; ``"<sha256>"`` for a regular file;
    ``"link:<sha256>"`` for a symlink (resolved content) so a regular-file ->
    symlink replacement is detected. Used to bind PASS to the validated
    repository state, not merely to a successful exit status.
    """
    repo = Path(repo_root).resolve()
    out = {}
    for t in targets or []:
        p = repo / str(t)
        if not p.exists() and not p.is_symlink():
            out[str(t)] = None
        elif p.is_symlink():
            try:
                out[str(t)] = "link:" + _hash_file(p.resolve(strict=False))
            except OSError:
                out[str(t)] = "link:broken"
        else:
            try:
                out[str(t)] = _hash_file(p)
            except OSError:
                out[str(t)] = None
    return out


def validate_command(command, allow=None):
    """Validate a command for safe execution. Returns the shlex token list.

    Raises SafetyError on any violation. The command must:
      * be a non-empty string with no null bytes;
      * contain no shell metacharacters or control characters;
      * have a bare (no path separator, no leading dot) executable that is in
        the explicit ``allow`` list (empty allow => nothing authorized);
      * contain no absolute or traversal (``..``) path arguments.
    """
    if not isinstance(command, str):
        raise SafetyError("command must be a string")
    if not command.strip():
        raise SafetyError("empty command")
    if "\x00" in command:
        raise SafetyError("null byte in command")
    for ch in command:
        if ch in _COMMAND_REJECT_CHARS:
            raise SafetyError(f"forbidden shell character {ch!r}")
        if ch in _control_chars():
            raise SafetyError(f"forbidden control character (ord {ord(ch)})")
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        raise SafetyError(f"malformed command tokens: {e}")
    if not tokens:
        raise SafetyError("empty command")

    exe = tokens[0]
    if exe.startswith(".") or "/" in exe or "\\" in exe or os.sep in exe:
        raise SafetyError(f"executable must be a bare tool name: {exe!r}")

    # Shell interpreters are NEVER valid validation executables, even if
    # allowlisted: they enable arbitrary command execution / injection.
    _DENIED_EXE = {"sh", "bash", "dash", "zsh", "ksh", "csh", "tcsh",
                   "ash", "busybox", "fish"}
    if exe in _DENIED_EXE:
        raise SafetyError(f"shell interpreter executables are prohibited: {exe!r}")

    allow_tuple = tuple(allow or [])
    if not allow_tuple:
        raise SafetyError("no allowlist provided; no tool is authorized")
    if not exe.startswith(allow_tuple):
        raise SafetyError(f"executable {exe!r} not in allowlist {list(allow_tuple)}")

    for tok in tokens[1:]:
        if tok.startswith("/") or (len(tok) >= 2 and tok[1] == ":"):
            raise SafetyError(f"absolute path argument not allowed: {tok!r}")
        if ".." in tok.split("/"):
            raise SafetyError(f"path traversal argument not allowed: {tok!r}")
    return tokens


def validate_targets(targets, repo_root, field_name="implementation_targets"):
    """Return a list of (target, reason) violations for path confinement.

    A valid target is a repository-relative path (no absolute path, no ``..``
    component, and no symlink escape outside the repo). Existence is NOT
    required (a target may be a file to be created).
    """
    repo = Path(repo_root).resolve()
    violations = []
    for t in targets or []:
        p = str(t)
        ap = Path(p)
        if ap.is_absolute():
            violations.append((p, "absolute path not allowed")); continue
        if ".." in ap.parts:
            violations.append((p, "path traversal (..) not allowed")); continue
        if "~" in ap.parts:
            violations.append((p, "home (~) path not allowed")); continue
        if ".git" in ap.parts:
            violations.append((p, "writes inside .git are prohibited")); continue
        full = repo / p
        try:
            resolved = full.resolve(strict=False)
        except (OSError, ValueError):
            violations.append((p, "unresolvable path")); continue
        try:
            resolved.relative_to(repo)
        except ValueError:
            violations.append((p, "target escapes repository")); continue
        # symlink escape: link target points outside the repo
        if full.is_symlink():
            try:
                tgt = full.resolve(strict=False)
                tgt.relative_to(repo)
            except (ValueError, OSError):
                violations.append((p, "symlink escapes repository")); continue
    return violations
