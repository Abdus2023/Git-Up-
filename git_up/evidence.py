"""Append-only hash-chained evidence log (component I)."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .canonical import sha256_json
from .errors import EvidenceError

VALID_RESULTS = {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class EvidenceRecord:
    evidence_id: str
    task_id: str
    command: str
    command_id: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_status: Optional[int] = None
    result: str = "NOT_APPLICABLE"
    failure_class: Optional[str] = None
    expected_exit: int = 0
    timestamp: str = ""
    artifacts: list = field(default_factory=list)
    notes: str = ""
    contract_id: str = ""
    repository_identity: str = ""
    head: str = ""
    source_identity: str = ""
    validator: str = "git-up"
    target_hashes: dict = field(default_factory=dict)
    observed_delta: list = field(default_factory=list)
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    prev_hash: str = ""
    record_hash: str = ""

    def __post_init__(self):
        if self.result not in VALID_RESULTS:
            raise EvidenceError(f"invalid result {self.result!r}")
        if not self.timestamp:
            self.timestamp = _now()

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "task_id": self.task_id,
            "command": self.command,
            "command_id": self.command_id,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_status": self.exit_status,
            "result": self.result,
            "failure_class": self.failure_class,
            "expected_exit": self.expected_exit,
            "timestamp": self.timestamp,
            "artifacts": list(self.artifacts),
            "notes": self.notes,
            "contract_id": self.contract_id,
            "repository_identity": self.repository_identity,
            "head": self.head,
            "source_identity": self.source_identity,
            "validator": self.validator,
            "target_hashes": dict(self.target_hashes),
            "observed_delta": list(self.observed_delta),
            "stdout_truncated": bool(self.stdout_truncated),
            "stderr_truncated": bool(self.stderr_truncated),
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }

    def payload_for_hash(self) -> dict:
        d = self.to_dict()
        d.pop("record_hash", None)
        return d


class EvidenceLog:
    def __init__(self, path):
        self.path = Path(path)

    def _raw_lines(self) -> list:
        if not self.path.is_file():
            return []
        return self.path.read_bytes().splitlines()

    def _last_record_hash(self) -> str:
        for raw in reversed(self._raw_lines()):
            if raw.strip():
                try:
                    return json.loads(raw.decode("utf-8")).get("record_hash", "")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return ""
        return ""

    def _existing_ids(self) -> set:
        ids = set()
        for rec in self.read_all():
            if isinstance(rec, dict):
                eid = rec.get("evidence_id")
                if eid:
                    ids.add(eid)
        return ids

    def append(self, record: EvidenceRecord) -> EvidenceRecord:
        if not record.evidence_id:
            record.evidence_id = "EVID-" + uuid.uuid4().hex[:12].upper()
        if not record.evidence_id:
            raise EvidenceError("empty evidence_id")
        if record.evidence_id in self._existing_ids():
            raise EvidenceError(
                f"duplicate evidence_id {record.evidence_id!r}"
            )
        record.prev_hash = self._last_record_hash()
        record.record_hash = sha256_json(record.payload_for_hash())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        return record

    def read_all(self) -> list:
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
            if rec.get("prev_hash", "") != prev:
                break
            if rec.get("record_hash", "") != sha256_json(payload):
                break
            eid = rec.get("evidence_id", "")
            if not eid:
                break
            if rec.get("result") not in VALID_RESULTS:
                break
            if eid in seen_ids:
                break
            seen_ids.add(eid)
            trusted.append(rec)
            prev = rec.get("record_hash", "")
        return trusted

    def verify_integrity(self) -> dict:
        all_records = self.read_all()
        trusted = len(self.verified_records())
        total = len(all_records)
        return {
            "total_records": total,
            "trusted_records": trusted,
            "intact": trusted == total,
            "broken_at": trusted,
        }

    @staticmethod
    def is_structural_pass(rec: dict) -> bool:
        return (
            rec.get("result") == "PASS"
            and isinstance(rec.get("exit_status"), int)
            and rec.get("exit_status") == rec.get("expected_exit", 0)
            and bool(rec.get("command"))
        )

    def pass_command_ids(self, task_id: str, contract_id: str) -> set:
        return {
            r.get("command_id")
            for r in self.verified_records()
            if r.get("task_id") == task_id
            and r.get("contract_id") == contract_id
            and self.is_structural_pass(r)
        }
