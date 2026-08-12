"""Command and path safety. Ambiguity is never permission (spec 16)."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from .errors import SafetyError


def path_under(path: str, spec: str) -> bool:
    """True if path is spec or a descendant. Empty spec matches nothing."""
    p = str(path or "").rstrip("/")
    s = str(spec or "").rstrip("/")
    if not s or not p:
        return False
    return p == s or p.startswith(s + "/")


def is_interpreter_residue(path: str) -> bool:
    """Interpreter residue is not a product write (ADR-0013)."""
    parts = Path(path).parts
    if "__pycache__" in parts:
        return True
    return path.endswith(".pyc") or path.endswith(".pyo")


def is_control_artifact(path: str) -> bool:
    p = str(path or "").rstrip("/")
    return p == ".git-up" or p.startswith(".git-up/")


def scope_violation_paths(paths, task, extra_ignore_prefixes=None) -> list:
    """Paths that escape implementation_targets or hit prohibited_scope.

    Residue and `.git-up/` are ignored. `prohibited_scope` wins even when the
    path sits under an allowed target (spec 07 / 10 / 16).
    """
    extra = extra_ignore_prefixes or set()
    bad = []
    targets = [t.rstrip("/") for t in (task.implementation_targets or []) if t]
    prohibited = [p.rstrip("/") for p in (task.prohibited_scope or []) if p]
    for raw in paths or []:
        path = str(raw).rstrip("/")
        if not path:
            continue
        if is_interpreter_residue(path) or is_control_artifact(path):
            continue
        if any(path == e.rstrip("/") or path.startswith(e) for e in extra):
            continue
        if any(path_under(path, p) for p in prohibited):
            bad.append(path)
            continue
        if targets and any(path_under(path, t) for t in targets):
            continue
        bad.append(path)
    return sorted(set(bad))

# spec 10 §2 / spec 16 §3: ; & | > < ` $ \ and ASCII controls.
_COMMAND_REJECT = set(";|&><`$\\")
# Shell interpreters (spec 10 §2 / 16 §3) and privilege-escalation
# frontends (spec 16 §8: MUST NOT invoke sudo / require root).
_DENIED_SHELL = {
    "sh", "bash", "dash", "zsh", "ksh", "csh", "tcsh", "ash", "busybox", "fish",
}
_DENIED_PRIVILEGE = {"sudo", "su", "doas", "pkexec"}
_DENIED_EXE = _DENIED_SHELL | _DENIED_PRIVILEGE


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
    if exe in _DENIED_SHELL:
        raise SafetyError(f"shell interpreter executables are prohibited: {exe!r}")
    if exe in _DENIED_PRIVILEGE:
        raise SafetyError(
            f"privilege-escalation executables are prohibited: {exe!r}"
        )

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
