"""Test fixtures: isolated git worktrees and contracts."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_git(repo: Path, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    run_git(path, "config", "user.email", "git-up@test")
    run_git(path, "config", "user.name", "Git-Up Test")
    run_git(path, "config", "commit.gpgsign", "false")
    return path


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def commit_all(repo: Path, msg: str = "wip"):
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", msg, "--allow-empty")


def minimal_task(**overrides) -> dict:
    task = {
        "id": "T1",
        "title": "example",
        "description": "an example task",
        "priority": 10,
        "order": 0,
        "source_authority": [{"path": "docs/SPEC.md", "anchor": "R1",
                              "requirement_id": "R1"}],
        "requirement_refs": ["R1"],
        "specification_refs": [{"path": "docs/SPEC.md", "anchor": "R1"}],
        "implementation_targets": ["src/out.txt"],
        "prohibited_scope": [],
        "dependencies": [],
        "required_tools": ["python3"],
        "allowed_tools": ["python3"],
        "validation_commands": [
            {"id": "v1", "command": "python3 -c pass", "expected_exit": 0,
             "purpose": "smoke"}
        ],
        "acceptance_criteria": [
            {"id": "c1", "statement": "smoke passes", "validator": "v1"}
        ],
        "expected_outputs": [],
        "declared_blockers": [],
        "spec_conflicts": [],
        "spec_gaps": [],
        "rejected": False,
        "deferred": False,
    }
    task.update(overrides)
    return task


def contract_doc(tasks=None, requirements=None, extra=None) -> dict:
    tasks = tasks if tasks is not None else [minimal_task()]
    doc = {
        "schema_version": "git-up.contract.v0.1",
        "policy": {
            "determinism": True,
            "timeout_seconds": 30,
            "concurrency": "exclusive",
            "failure_mode": "fail_closed",
        },
        "tools": [
            {"id": "python3", "available": True, "binary": "python3", "version": "3"},
            {"id": "bash", "available": True, "binary": "bash", "version": "5"},
        ],
        "requirements": requirements if requirements is not None else [
            {
                "id": "R1",
                "specification_refs": ["docs/SPEC.md"],
                "coverage": [{"task_id": "T1", "obligations": ["all"]}],
            }
        ],
        "tasks": tasks,
    }
    if extra:
        doc.update(extra)
    return doc


def seed_worktree(repo: Path, contract=None, spec="R1 holds.\n") -> Path:
    write(repo / "docs" / "SPEC.md", spec)
    write(repo / "src" / "out.txt", "seed\n")
    write(repo / "git-up.contract.json",
          json.dumps(contract or contract_doc(), indent=2) + "\n")
    commit_all(repo, "seed")
    return repo / "git-up.contract.json"


def make_controller(repo: Path, contract_path=None, **kwargs):
    from git_up.controller import Controller
    return Controller(
        contract_path=str(contract_path or repo / "git-up.contract.json"),
        repo_root=str(repo),
        state_path=str(repo / ".git-up" / "state.json"),
        evidence_path=str(repo / ".git-up" / "evidence.jsonl"),
        **kwargs,
    )
