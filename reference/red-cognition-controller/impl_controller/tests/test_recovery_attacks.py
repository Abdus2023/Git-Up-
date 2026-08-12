"""Stage-5 failure-injection & transactional-recovery adversarial tests.

Central invariant: a crash/kill/timeout/partial-write/concurrent-execution/
corrupted-checkpoint/corrupted-evidence/interrupted-validation MUST NEVER
manufacture PASS. Recovery is evidence-authoritative, deterministic, and
idempotent. Run via:  python3 tools/impl-controller.py --self-test
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from impl_controller.controller import Controller
from impl_controller.evidence import EvidenceLog, EvidenceRecord
from impl_controller.checkpoint import StateStore
from impl_controller.locking import FileLock, LockAcquisitionError
from impl_controller.provenance import provenance_context, contract_identity_for
from impl_controller.manifest import load_manifest


def _synth(d, with_git=False, command="python3 -V", expected=0):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    t = {
        "task_id": "SYNTH-001", "title": "syn", "description": "d",
        "priority": 1, "plan_order": 1, "scope": "s",
        "source_authority": [{"doc": "spec.md"}],
        "requirement_refs": ["REQ-1"],
        "specification_refs": [{"doc": "spec.md"}],
        "implementation_targets": ["out.txt"],
        "dependency_refs": [], "required_tools": [],
        "allowed_tools": ["python3"],
        "validation_commands": [{"id": "V1", "command": command,
                                 "expected_exit": expected}],
        "acceptance_criteria": [{"id": "A1", "criterion": "c"}],
    }
    man = {"schema_version": "1.0", "project": "syn",
           "tool_registry": {"python3": {"available": True, "binary": "python3"}},
           "tasks": [t]}
    mp = Path(d) / "m.json"; mp.write_text(json.dumps(man), encoding="utf-8")
    if with_git:
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        env = dict(os.environ); env.update({
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "i"],
                       check=True, env=env)
    return mp, repo


def _pass_baseline(d):
    """Run a clean execute to PASS; return (mp, repo, sp, ep)."""
    mp, repo = _synth(d)
    sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
    Controller(mp, repo, sp, ep).run(execute=True)
    return mp, repo, sp, ep


# ==========================================================================
# A — Crash before/during execution (no PASS, recoverable)
# ==========================================================================
class A_CrashBeforeDuring(unittest.TestCase):
    def test_in_progress_not_persisted_no_false_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            # simulate: begin() ran (in-memory only), process died before save
            st = StateStore(sp); st.load(); st.begin("SYNTH-001")  # not saved
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")
            self.assertIn(res.classifications["SYNTH-001"].effective_state,
                          ("READY", "BLOCKED"))

    def test_executor_nonzero_exit_no_pass(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "x"; sub.mkdir()
            mp, repo = _synth(str(sub), command="python3 fail.py")
            (repo / "fail.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
            sp, ep = sub / "s.json", sub / "e.jsonl"
            res = Controller(mp, repo, sp, ep).run(execute=True)
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")


# ==========================================================================
# C — Crash during evidence commit / checkpoint
# ==========================================================================
class C_EvidenceCheckpointCommit(unittest.TestCase):
    def test_truncated_evidence_line_breaks_chain(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            data = ep.read_bytes()
            ep.write_bytes(data[:len(data) // 2])  # truncate mid-record
            log = EvidenceLog(ep)
            self.assertFalse(log.verify_integrity()["intact"])
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")

    def test_evidence_committed_checkpoint_not(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            # rewind checkpoint to pre-execute; keep evidence
            sp.write_text(json.dumps({"repo_head": "", "tasks": [
                {"task_id": "SYNTH-001", "state": "IN_PROGRESS",
                 "in_progress": True}]}), encoding="utf-8")
            res = Controller(mp, repo, sp, ep).run()
            # evidence is authoritative -> recovers to PASS (true positive)
            self.assertEqual(res.classifications["SYNTH-001"].effective_state, "PASS")

    def test_checkpoint_pass_evidence_lost_demoted(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            ep.unlink()  # evidence lost; checkpoint still claims PASS
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")


# ==========================================================================
# D — Crash during checkpoint (corruption)
# ==========================================================================
class D_CheckpointCorruption(unittest.TestCase):
    def test_truncated_checkpoint_rebuilt(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            sp.write_bytes(sp.read_bytes()[:20])  # truncated
            st = StateStore(sp); st.load()
            self.assertEqual(st.tasks, {})  # rejected -> clean

    def test_invalid_json_checkpoint_rebuilt(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            sp.write_text("{not json", encoding="utf-8")
            st = StateStore(sp); st.load()
            self.assertEqual(st.tasks, {})

    def test_checkpoint_pass_without_evidence_demoted(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            ep.unlink()
            # checkpoint still claims validated_pass
            raw = json.loads(sp.read_text())
            raw["tasks"][0]["validated_pass"] = True
            raw["tasks"][0]["state"] = "PASS"
            sp.write_text(json.dumps(raw), encoding="utf-8")
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")


# ==========================================================================
# E — Crash after validation / stale contract
# ==========================================================================
class E_AfterValidation(unittest.TestCase):
    def test_validator_pass_dies_before_evidence_no_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            # wipe evidence (validator passed but evidence never committed)
            ep.unlink()
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")

    def test_stale_contract_pass_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            self.assertEqual(Controller(mp, repo, sp, ep).run().classifications[
                "SYNTH-001"].effective_state, "PASS")
            # mutate manifest -> contract_id changes -> stale evidence
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "x"
            mp.write_text(json.dumps(man))
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")


# ==========================================================================
# F — Recovery determinism / idempotence
# ==========================================================================
class F_Recovery(unittest.TestCase):
    def test_restart_after_in_progress(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            ep.unlink()  # leave an interrupted IN_PROGRESS-like state
            sp.write_text(json.dumps({"repo_head": "", "tasks": [
                {"task_id": "SYNTH-001", "state": "IN_PROGRESS",
                 "in_progress": True}]}), encoding="utf-8")
            states = []
            for _ in range(3):
                r = Controller(mp, repo, sp, ep).run()
                states.append(r.classifications["SYNTH-001"].effective_state)
            self.assertEqual(len(set(states)), 1)
            self.assertNotIn("PASS", states)

    def test_idempotent_recovery_no_duplicate_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            before = sum(1 for _ in ep.open())
            for _ in range(3):
                Controller(mp, repo, sp, ep).recover()
            after = sum(1 for _ in ep.open())
            self.assertEqual(before, after)  # no duplicate evidence
            self.assertEqual(Controller(mp, repo, sp, ep).run().classifications[
                "SYNTH-001"].effective_state, "PASS")


# ==========================================================================
# Phase 3 — Concurrency / lease failure (incl. SIGKILL)
# ==========================================================================
class ConcurrencyLease(unittest.TestCase):
    def test_sigkill_releases_lock(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "k"; sub.mkdir()
            ms, rs = _synth(str(sub), command="python3 sleep.py")
            (rs / "sleep.py").write_text("import time; time.sleep(30)\n", encoding="utf-8")
            spk, epk = sub / "s.json", sub / "e.jsonl"
            proc = subprocess.Popen(
                [sys.executable, str(TOOLS / "run-implementation-pipeline.py"),
                 "--manifest", str(ms), "--repo-root", str(rs),
                 "--state", str(spk), "--evidence", str(epk),
                 "--status-out", str(sub / "o.json"),
                 "--execute", "--allow-tool", "python3"],
                start_new_session=True)
            time.sleep(1.5)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=10)
            # the lock file may remain, but the flock died with the process
            # -> a new controller MUST be able to acquire the lease and recover
            res = Controller(ms, rs, spk, epk).run()
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")
            self.assertEqual(res.result, "PASS")  # recovery succeeded (lease acquirable)


# ==========================================================================
# Phase 8 — Evidence duplication
# ==========================================================================
class EvidenceDuplication(unittest.TestCase):
    def test_duplicate_id_same_payload_one_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            for _ in range(2):
                log.append(EvidenceRecord("DUP", "T", "python3 -V",
                          exit_status=0, result="PASS", expected_exit=0))
            # duplicate evidence_id -> chain stops at the duplicate
            self.assertLessEqual(log.verify_integrity()["trusted_records"], 1)

    def test_duplicate_id_different_payload_integrity_failure(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            log.append(EvidenceRecord("DUP", "T", "python3 -V", exit_status=0,
                                      result="PASS", expected_exit=0))
            # craft a second record with same id, different stdout, valid chain
            log.append(EvidenceRecord("DUP", "T", "python3 -V", exit_status=0,
                                      result="PASS", expected_exit=0))
            # mutate second record's stdout but keep its (now stale) hash
            lines = ep.read_text().splitlines()
            rec = json.loads(lines[1]); rec["stdout"] = "DIFFERENT"
            ep.write_text(lines[0] + "\n" + json.dumps(rec) + "\n")
            self.assertFalse(EvidenceLog(ep).verify_integrity()["intact"])


# ==========================================================================
# Phase 9 — Partial file corruption
# ==========================================================================
class Corruption(unittest.TestCase):
    def _with_log(self, d, content_bytes):
        ep = Path(d) / "e.jsonl"; ep.write_bytes(content_bytes)
        return EvidenceLog(ep)

    def test_zero_byte_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(self._with_log(d, b"").verify_integrity()["intact"])

    def test_half_json_object(self):
        with tempfile.TemporaryDirectory() as d:
            log = self._with_log(d, b'{"evidence_id":"E","task_id":"T",')
            self.assertFalse(log.verify_integrity()["intact"])

    def test_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            log = self._with_log(d, b'\xff\xfe\x00\n')
            self.assertFalse(log.verify_integrity()["intact"])

    def test_malformed_record_hash(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            log.append(EvidenceRecord("E", "T", "python3 -V", exit_status=0,
                                      result="PASS", expected_exit=0))
            rec = json.loads(ep.read_text().strip()); rec["record_hash"] = "0" * 64
            ep.write_text(json.dumps(rec) + "\n")
            self.assertFalse(EvidenceLog(ep).verify_integrity()["intact"])

    def test_incorrect_prev_hash(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            for _ in range(2):
                log.append(EvidenceRecord("E", "T", "python3 -V", exit_status=0,
                                          result="PASS", expected_exit=0))
            lines = ep.read_text().splitlines()
            rec = json.loads(lines[1]); rec["prev_hash"] = "deadbeef"
            ep.write_text(lines[0] + "\n" + json.dumps(rec) + "\n")
            self.assertLess(EvidenceLog(ep).verify_integrity()["trusted_records"], 2)


# ==========================================================================
# Phase 6 — State machine invariants
# ==========================================================================
class StateMachine(unittest.TestCase):
    def test_no_ready_to_pass_direct(self):
        from impl_controller.checkpoint import ALLOWED_TRANSITIONS
        # PASS is not directly reachable from READY
        self.assertNotIn("PASS", ALLOWED_TRANSITIONS.get("READY", set()))

    def test_checkpoint_validated_pass_not_auto_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            ep.unlink()
            raw = json.loads(sp.read_text())
            raw["tasks"][0]["validated_pass"] = True
            raw["tasks"][0]["state"] = "PASS"
            sp.write_text(json.dumps(raw), encoding="utf-8")
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")

    def test_executor_exit_zero_not_auto_pass(self):
        # an executor that exits 0 but whose evidence is removed -> not PASS
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            ep.unlink()
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")


# ==========================================================================
# Phase 12 — Provenance preservation across recovery
# ==========================================================================
class ProvenancePreservation(unittest.TestCase):
    def test_recovered_pass_provenance_consistent(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            # corrupt checkpoint, recover
            sp.write_text("{broken", encoding="utf-8")
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(res.classifications["SYNTH-001"].effective_state, "PASS")
            pc = res.report["provenance_context"]
            self.assertTrue(pc["repository_identity"] and pc["manifest_hash"])
            tr = [t for t in res.report["traceability"] if t["task_id"] == "SYNTH-001"][0]
            self.assertEqual(tr["closure"], "CLOSED")


# ==========================================================================
# Phase 14 — Deterministic recovery from identical failure state
# ==========================================================================
class DeterministicRecovery(unittest.TestCase):
    def test_three_recoveries_identical(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass_baseline(d)
            sp.write_text("{broken", encoding="utf-8")  # corrupted checkpoint
            norms = []
            for _ in range(3):
                r = Controller(mp, repo, sp, ep).recover()
                norms.append(json.dumps({k: r.report[k] for k in
                    ("graph", "classifications", "provenance_context")},
                    sort_keys=True))
            self.assertEqual(len(set(norms)), 1)


# ==========================================================================
# Phase 13 — Real repository
# ==========================================================================
class RealRepository(unittest.TestCase):
    def test_frontier_unchanged(self):
        mp = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        if not mp.is_file():
            self.skipTest("seed manifest absent")
        import tempfile as _t
        sd = _t.mkdtemp()
        c = Controller(mp, REPO_ROOT, Path(sd) / "s.json", Path(sd) / "e.jsonl")
        res = c.run(dry_run=True)
        self.assertEqual(res.report["graph"]["READY"], 0)
        self.assertEqual(res.report["graph"]["BLOCKED"], 4)
        self.assertEqual(res.report["frontier"], "PAUSED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
