"""Evidence model and tamper-evident append-only evidence log.

Evidence records are the only acceptable proof of validation. A PASS is never
trusted unless: the JSONL hash chain is intact up to that record, AND the
record is structurally valid (result == PASS, exit_status is an int equal to
expected_exit, command non-empty). Tampering with, removing, or appending a
malformed record breaks the chain and every subsequent record is untrusted
(fail closed).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .safety import validate_command, SafetyError

VALID_RESULTS = {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}


class EvidenceError(ValueError):
    pass


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


@dataclass
class EvidenceRecord:
    evidence_id: str
    task_id: str
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_status: Optional[int] = None
    result: str = "NOT_APPLICABLE"   # PASS | FAIL | BLOCKED | NOT_APPLICABLE
    failure_class: Optional[str] = None
    timestamp: str = ""
    artifacts: list = field(default_factory=list)  # [{"path","sha256","bytes"}]
    notes: str = ""
    expected_exit: int = 0
    # ---- provenance binding (cryptographically chained below) ----
    contract_id: str = ""
    repository_identity: str = ""
    head: str = ""
    manifest_hash: str = ""
    validator: str = ""
    command_id: str = ""
    target_hashes: dict = field(default_factory=dict)   # observed target state
    observed_delta: list = field(default_factory=list)   # sorted changed paths
    prev_hash: str = ""
    record_hash: str = ""

    def __post_init__(self):
        if self.result not in VALID_RESULTS:
            raise EvidenceError(f"invalid result {self.result!r}")
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def payload_for_hash(self) -> dict:
        """Fields hashed for integrity (excludes record_hash, includes prev_hash)."""
        d = self.to_dict()
        d.pop("record_hash", None)
        return d

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "task_id": self.task_id,
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_status": self.exit_status,
            "result": self.result,
            "failure_class": self.failure_class,
            "timestamp": self.timestamp,
            "artifacts": list(self.artifacts),
            "notes": self.notes,
            "expected_exit": self.expected_exit,
            "contract_id": self.contract_id,
            "repository_identity": self.repository_identity,
            "head": self.head,
            "manifest_hash": self.manifest_hash,
            "validator": self.validator,
            "command_id": self.command_id,
            "target_hashes": dict(self.target_hashes),
            "observed_delta": list(self.observed_delta),
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_artifact(path, repo_root: Optional[Path] = None) -> dict:
    p = Path(path)
    if not p.is_file():
        raise EvidenceError(f"artifact not found: {p}")
    rel = p.resolve()
    try:
        rel = rel.relative_to(Path(repo_root).resolve()) if repo_root else p
    except ValueError:
        rel = p
    return {"path": str(rel).replace("\\", "/"), "sha256": _sha256_file(p),
            "bytes": p.stat().st_size}


class EvidenceLog:
    """Append-only, tamper-evident JSONL evidence log."""

    def __init__(self, path):
        self.path = Path(path)

    # ---- writing -----------------------------------------------------------
    def _last_record_hash(self) -> str:
        for raw in reversed(self._raw_lines()):
            if raw.strip():
                try:
                    return json.loads(raw.decode("utf-8")).get("record_hash", "")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return ""  # corrupt tail -> chain reset (fail closed on read)
        return ""

    def append(self, record: EvidenceRecord) -> EvidenceRecord:
        if not record.evidence_id:
            record.evidence_id = "EVID-" + uuid.uuid4().hex[:12].upper()
        record.prev_hash = self._last_record_hash()
        record.record_hash = _hash(record.payload_for_hash())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Durable append: the evidence becomes authoritative only once flushed
        # and fsynced to disk. A checkpoint may reference it only afterwards.
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass  # fsync best-effort on some filesystems
        return record

    # ---- reading -----------------------------------------------------------
    def _raw_lines(self) -> list:
        """Raw byte lines; never raises on bad encoding (fail-closed readers)."""
        if not self.path.is_file():
            return []
        return self.path.read_bytes().splitlines()

    def read_all(self) -> list:
        """All parsed records (UNVERIFIED). Use verified_records() for trust."""
        out = []
        for raw in self._raw_lines():
            if not raw.strip():
                continue
            try:
                out.append(json.loads(raw.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                out.append({"_malformed": raw.decode("utf-8", errors="replace")})
        return out

    def verified_records(self) -> list:
        """Records whose hash chain is intact from the genesis record, with no
        duplicate evidence_id.

        The first record's prev_hash must be "" and its record_hash must match.
        Any break (tamper, missing line, malformed JSON/UTF-8, wrong hash,
        duplicate evidence_id) stops the trusted stream; that record and all
        later ones are excluded.
        """
        trusted = []
        prev = ""
        seen_ids = set()
        for raw in self._raw_lines():
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                break
            if not isinstance(rec, dict):
                break
            payload = {k: v for k, v in rec.items() if k != "record_hash"}
            expected_hash = _hash(payload)
            if rec.get("prev_hash", "") != prev:
                break
            if rec.get("record_hash", "") != expected_hash:
                break
            eid = rec.get("evidence_id", "")
            if eid and eid in seen_ids:
                break  # duplicate evidence_id -> integrity failure
            seen_ids.add(eid)
            trusted.append(rec)
            prev = rec.get("record_hash", "")
        return trusted

    def verify_integrity(self) -> dict:
        """Return a structural integrity report: trusted count, total, breaks."""
        all_records = self.read_all()
        total = len(all_records)
        trusted = len(self.verified_records())
        return {"total_records": total, "trusted_records": trusted,
                "intact": trusted == total, "broken_at": trusted}

    @staticmethod
    def _is_valid_pass(rec: dict) -> bool:
        return (rec.get("result") == "PASS"
                and isinstance(rec.get("exit_status"), int)
                and rec.get("exit_status") == rec.get("expected_exit", 0)
                and bool(rec.get("command")))

    def validated_pass(self) -> set:
        """task_ids with at least one chain-verified, structurally-valid PASS."""
        return {r["task_id"] for r in self.verified_records()
                if self._is_valid_pass(r)}

    def for_task(self, task_id: str) -> list:
        return [r for r in self.verified_records() if r.get("task_id") == task_id]

    def pass_command_ids(self, task_id: str, contract_id: str) -> set:
        """command_ids with verified PASS evidence for (task_id, contract_id)."""
        return {r.get("command_id") for r in self.verified_records()
                if r.get("task_id") == task_id
                and r.get("contract_id") == contract_id
                and r.get("result") == "PASS"}


def classify_exit(command: str, exit_status: Optional[int],
                  expected_exit: int = 0) -> str:
    if exit_status is None:
        return "BLOCKED"
    return "PASS" if exit_status == expected_exit else "FAIL"


def safe_command(command: str, allow: list) -> None:
    """Reject unsafe commands (delegates to safety.validate_command).

    Empty allowlist => no tool is authorized (fail closed).
    Raises EvidenceError on any violation.
    """
    try:
        validate_command(command, allow)
    except SafetyError as e:
        raise EvidenceError(str(e)) from e
