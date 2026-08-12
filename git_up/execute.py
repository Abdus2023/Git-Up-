"""Declared-validator execution and observation (components G, H)."""

from __future__ import annotations

import subprocess

from . import VALIDATOR_IDENTITY
from .errors import SafetyError
from .evidence import EvidenceRecord
from .identity import command_identity
from .safety import validate_command


def classify_exit(exit_status, expected_exit: int) -> str:
    if exit_status is None:
        return "BLOCKED"
    return "PASS" if exit_status == expected_exit else "FAIL"


def run_validation(task_id, vc, allow, contract_id, ctx, cwd, timeout) -> EvidenceRecord:
    stdout = stderr = ""
    exit_status = None
    result = "BLOCKED"
    notes = ""
    failure = None
    try:
        tokens = validate_command(vc.command, allow)
        proc = subprocess.run(
            tokens, cwd=str(cwd), shell=False,
            capture_output=True, text=True, timeout=timeout,
        )
        exit_status = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        result = classify_exit(exit_status, vc.expected_exit)
        if result == "FAIL":
            failure = "TEST"
    except SafetyError as e:
        stderr, result, notes = str(e), "BLOCKED", str(e)
    except subprocess.TimeoutExpired as e:
        stderr, result, failure = f"timeout: {e}", "FAIL", "TEST"
    except FileNotFoundError as e:
        stderr, result = f"tool not found: {e}", "BLOCKED"
    except Exception as e:  # pragma: no cover
        stderr, result = f"exec error: {e}", "BLOCKED"

    def clip(s: str):
        if len(s) <= 4000:
            return s, False
        return s[-4000:], True

    stdout, stdout_trunc = clip(stdout)
    stderr, stderr_trunc = clip(stderr)

    return EvidenceRecord(
        evidence_id="",
        task_id=task_id,
        command=vc.command,
        command_id=command_identity(vc),
        stdout=stdout,
        stderr=stderr,
        exit_status=exit_status,
        result=result,
        failure_class=failure,
        expected_exit=vc.expected_exit,
        notes=notes,
        contract_id=contract_id,
        repository_identity=ctx.get("repo_identity", ""),
        head=ctx.get("head", ""),
        source_identity=ctx.get("source_identity", ""),
        validator=VALIDATOR_IDENTITY,
        stdout_truncated=stdout_trunc,
        stderr_truncated=stderr_trunc,
    )


def contract_tool_set(task) -> list:
    """Authorized bare names: allowed ∪ required, first-seen order."""
    return list(dict.fromkeys(list(task.allowed_tools) + list(task.required_tools)))


def effective_allowlist(task, cli_allow) -> list:
    """Contract tools only. CLI may refine (intersect), never widen (spec 09 §5).

    ``cli_allow is None`` means no CLI refinement (use the contract set).
    A provided list is intersected with the contract set. An empty
    intersection is an empty allowlist (deny all) — never a silent
    fallback to the full contract set.
    """
    contract_tools = contract_tool_set(task)
    if cli_allow is None:
        return contract_tools
    allowed = set(contract_tools)
    return [t for t in cli_allow if t in allowed]
