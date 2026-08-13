"""I-EVID-1, I-EVID-2 — hash chain integrity."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.canonical import sha256_json
from git_up.errors import EvidenceError
from git_up.evidence import VALID_RESULTS, EvidenceLog, EvidenceRecord


def _rec(**kw):
    base = dict(
        evidence_id="", task_id="T1", command="python3 -c pass",
        command_id="x", result="PASS", exit_status=0, expected_exit=0,
    )
    base.update(kw)
    return EvidenceRecord(**base)


class ChainTests(unittest.TestCase):
    def test_I_EVID_1_broken_chain_untrusted_tail(self):
        with tempfile.TemporaryDirectory() as td:
            log = EvidenceLog(Path(td) / "evidence.jsonl")
            log.append(_rec())
            log.append(_rec())
            data = log.path.read_bytes()
            # flip a byte in the first record
            mutated = bytearray(data)
            idx = mutated.find(b"python3")
            self.assertGreater(idx, 0)
            mutated[idx] = ord("P")
            log.path.write_bytes(bytes(mutated))
            trusted = log.verified_records()
            self.assertEqual(trusted, [])
            integ = log.verify_integrity()
            self.assertFalse(integ["intact"])

    def test_I_EVID_2_duplicate_id_breaks_trust(self):
        with tempfile.TemporaryDirectory() as td:
            log = EvidenceLog(Path(td) / "evidence.jsonl")
            a = log.append(_rec(evidence_id="EVID-SAME"))
            # append a second record then rewrite its id to collide after hash
            b = log.append(_rec(evidence_id="EVID-OTHER"))
            text = log.path.read_text(encoding="utf-8")
            # force second evidence_id to match first WITHOUT repairing hash
            # (hash mismatch also breaks; instead append a hand-crafted line
            # with same id and a matching hash of its own payload)
            from git_up.canonical import sha256_json
            import json
            rec = json.loads(text.splitlines()[-1])
            rec["evidence_id"] = "EVID-SAME"
            payload = {k: v for k, v in rec.items() if k != "record_hash"}
            rec["record_hash"] = sha256_json(payload)
            lines = text.splitlines()
            lines[-1] = json.dumps(rec, ensure_ascii=False)
            log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            trusted = log.verified_records()
            self.assertEqual(len(trusted), 1)
            self.assertEqual(trusted[0]["evidence_id"], "EVID-SAME")

    def test_structural_pass_requires_exit(self):
        rec = {"result": "PASS", "exit_status": None, "expected_exit": 0,
               "command": "x"}
        self.assertFalse(EvidenceLog.is_structural_pass(rec))

    def test_empty_evidence_id_breaks_trust(self):
        with tempfile.TemporaryDirectory() as td:
            log = EvidenceLog(Path(td) / "evidence.jsonl")
            rec = {
                "evidence_id": "",
                "task_id": "T1",
                "command": "python3 -c pass",
                "command_id": "x",
                "result": "PASS",
                "exit_status": 0,
                "expected_exit": 0,
                "prev_hash": "",
            }
            rec["record_hash"] = sha256_json(rec)
            log.path.write_text(
                __import__("json").dumps(rec) + "\n", encoding="utf-8",
            )
            self.assertEqual(log.verified_records(), [])
            self.assertFalse(log.verify_integrity()["intact"])

    def test_unknown_result_breaks_trust(self):
        with tempfile.TemporaryDirectory() as td:
            log = EvidenceLog(Path(td) / "evidence.jsonl")
            rec = {
                "evidence_id": "EVID-GREEN",
                "task_id": "T1",
                "command": "python3 -c pass",
                "command_id": "x",
                "result": "GREEN",
                "exit_status": 0,
                "expected_exit": 0,
                "prev_hash": "",
            }
            rec["record_hash"] = sha256_json(rec)
            log.path.write_text(
                __import__("json").dumps(rec) + "\n", encoding="utf-8",
            )
            self.assertEqual(log.verified_records(), [])
            self.assertNotIn("GREEN", VALID_RESULTS)

    def test_append_duplicate_id_refused(self):
        with tempfile.TemporaryDirectory() as td:
            log = EvidenceLog(Path(td) / "evidence.jsonl")
            log.append(_rec(evidence_id="EVID-SAME"))
            before = log.path.read_text(encoding="utf-8")
            with self.assertRaises(EvidenceError) as ctx:
                log.append(_rec(evidence_id="EVID-SAME"))
            self.assertIn("duplicate", str(ctx.exception))
            self.assertEqual(log.path.read_text(encoding="utf-8"), before)
            self.assertEqual(len(log.verified_records()), 1)


if __name__ == "__main__":
    unittest.main()
