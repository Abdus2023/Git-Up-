"""Repository identity and observation (component B, H)."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from .canonical import sha256_file, sha256_json
from .errors import RepositoryError
from .safety import is_control_artifact, is_interpreter_residue

IDENTITY_REL = Path(".git-up") / "repo.identity"


def controller_env() -> dict:
    """Env for Git-Up! git observation and declared validators.

    Ambient ``GIT_*`` must not redirect HEAD, porcelain, or toplevel
    (spec 06 one-worktree; spec 16 §9: environment cannot widen or
    retarget authority). User/system gitconfig is neutralized so aliases
    cannot rewrite ``status`` / ``rev-parse``. Repo-local config remains.
    """
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("GIT_"):
            del env[key]
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["LC_ALL"] = "C"
    return env


def run_git(repo_root, *args, timeout=10, text=True):
    """Run git against ``repo_root`` with a neutralized environment."""
    cmd = ["git", "-C", str(repo_root), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=text,
        timeout=timeout,
        env=controller_env(),
    )


def git_toplevel(start: Optional[Path] = None) -> Path:
    cwd = Path(start or Path.cwd())
    try:
        out = run_git(cwd, "rev-parse", "--show-toplevel", timeout=10)
        if out.returncode == 0 and (out.stdout or "").strip():
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return cwd.resolve()


def repo_head(repo_root) -> str:
    try:
        out = run_git(repo_root, "rev-parse", "HEAD", timeout=10)
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def parse_porcelain(raw: bytes) -> set:
    """Parse `git status --porcelain=v1 -z` into a set of worktree paths.

    Rename/copy records are `XY PATH\\0ORIG_PATH\\0`. Both names are observed.
    Directory markers are normalized without a trailing slash.
    """
    paths = set()
    parts = raw.split(b"\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if not entry:
            continue
        if len(entry) < 3:
            continue
        try:
            code = entry[:2].decode("ascii")
        except UnicodeDecodeError:
            code = ""
        path = entry[3:].decode("utf-8", "surrogateescape").rstrip("/")
        if path:
            paths.add(path)
        if "R" in code or "C" in code:
            if i < len(parts):
                orig = parts[i].decode("utf-8", "surrogateescape").rstrip("/")
                i += 1
                if orig:
                    paths.add(orig)
    return paths


def porcelain(repo_root) -> set:
    """Best-effort set of dirty / untracked paths (spec 06 §2.3)."""
    try:
        out = run_git(
            repo_root,
            "status", "--porcelain=v1", "-z", "--untracked-files=all",
            timeout=15, text=False,
        )
        if out.returncode != 0:
            return set()
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return parse_porcelain(out.stdout)


def read_repo_identity(repo_root) -> str:
    """Read existing identity. Does not create (dry-run safe)."""
    p = Path(repo_root).resolve() / IDENTITY_REL
    if p.is_file():
        ident = p.read_text(encoding="utf-8").strip()
        if ident:
            return ident
    return ""


def ensure_repo_identity(repo_root) -> str:
    """Create per-worktree identity. Mutating operations only."""
    existing = read_repo_identity(repo_root)
    if existing:
        return existing
    root = Path(repo_root).resolve()
    iddir = root / ".git-up"
    idfile = iddir / "repo.identity"
    try:
        iddir.mkdir(parents=True, exist_ok=True)
        ident = "repo-" + uuid.uuid4().hex
        idfile.write_text(ident, encoding="utf-8")
        return ident
    except OSError as e:
        raise RepositoryError(f"cannot create repository identity: {e}") from e


def _observe(path: Path, rel: str):
    """Spec 06 §5 plus directories: None | sha256 | link:… | dir:…"""
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        try:
            return "link:" + sha256_file(path.resolve(strict=False))
        except OSError:
            return "link:broken"
    if path.is_dir():
        entries = []
        try:
            children = sorted(path.iterdir(), key=lambda c: c.name)
        except OSError:
            return "dir:unreadable"
        for child in children:
            crel = f"{rel.rstrip('/')}/{child.name}" if rel else child.name
            if is_interpreter_residue(crel) or is_control_artifact(crel):
                continue
            entries.append([child.name, _observe(child, crel)])
        return "dir:" + sha256_json(entries)
    try:
        return sha256_file(path)
    except OSError:
        return None


def target_hashes(targets, repo_root) -> dict:
    """Observed state map: None | sha256 | link:… | dir:… (spec 06 §5).

    A directory is not absent. Hashing it as None (open() → EISDIR) made
    deleting a directory target indistinguishable from leaving it in place.
    """
    repo = Path(repo_root).resolve()
    out = {}
    for t in targets or []:
        key = str(t)
        out[key] = _observe(repo / key, key)
    return out
