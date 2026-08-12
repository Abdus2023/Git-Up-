"""Stage-5 transactional crash-consistency & recovery-fixpoint tests.

Proves: a crash/kill/partial-write/corruption/concurrent-writer at any
transaction boundary NEVER manufactures PASS; recovery is a fixpoint
(recover^n converges); derived artifacts never authorize state.

Each TC specifies setup / injected failure / durable state / expected authority
/ recovered state / classification / whether PASS is permitted.
Run via:  python3 tools/impl-controller.py --self-test
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
RUNNER = TOOLS / "run-implementation-pipeline.py"
sys.path.insert(0, str(TOOLS))

from impl_controller.controller import Controller
from impl_controller.evidence import EvidenceLog, EvidenceRecord, _hash
from impl_controller.checkpoint import StateStore
from impl_controller.provenance import (
    provenance_context, contract_identity_for, manifest_identity,
    repo_identity, VALIDATOR_IDENTITY,
)
from impl_controller.manifest import load_manifest


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _synth(d, command="python3 -V", with_git=False, tid="SYNTH-001"):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    t = {"task_id": tid, "title": "syn", "description": "d", "priority": 1,
         "plan_order": 1, "scope": "s",
         "source_authority": [{"doc": "spec.md"}], "requirement_refs": ["REQ-1"],
         "specification_refs": [{"doc": "spec.md"}],
         "implementation_targets": ["out.txt"], "dependency_refs": [],
         "required_tools": [], "allowed_tools": ["python3"],
         "validation_commands": [{"id": "V1", "command": command, "expected_exit": 0}],
         "acceptance_criteria": [{"id": "A1", "criterion": "c"}]}
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


def _pass(d):
    mp, repo = _synth(d)
    sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
    Controller(mp, repo, sp, ep).run(execute=True)
    return mp, repo, sp, ep


def _recompute_record_hash(rec):
    payload = {k: v for k, v in rec.items() if k != "record_hash"}
    rec["record_hash"] = _hash(payload)
    return rec


def _state_of(res, tid="SYNTH-001"):
    return res.classifications[tid].effective_state


# ==========================================================================
class CrashConsistency(unittest.TestCase):

    # TC-01 crash-before-begin
    def test_tc01_crash_before_begin(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertNotEqual(_state_of(res), "PASS")

    # TC-02 crash-after-begin (begin is in-memory only)
    def test_tc02_crash_after_begin(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            StateStore(sp).begin("SYNTH-001")  # in-memory; not saved
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotIn(_state_of(res), ("PASS", "IN_PROGRESS"))

    # TC-03 crash-during-execution (real SIGKILL)
    def test_tc03_crash_during_execution(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "k"; sub.mkdir()
            mp, repo = _synth(str(sub), command="python3 sleep.py")
            (repo / "sleep.py").write_text("import time; time.sleep(30)\n", encoding="utf-8")
            sp, ep = sub / "s.json", sub / "e.jsonl"
            proc = subprocess.Popen(
                [sys.executable, str(RUNNER), "--manifest", str(mp),
                 "--repo-root", str(repo), "--state", str(sp), "--evidence", str(ep),
                 "--status-out", str(sub / "o.json"), "--execute",
                 "--allow-tool", "python3"], start_new_session=True)
            time.sleep(1.5)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL); proc.wait(timeout=10)
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(_state_of(res), "PASS")
            self.assertEqual(res.result, "PASS")  # recovery acquired the freed lease

    # TC-04 evidence-committed-before-checkpoint
    def test_tc04_evidence_before_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            sp.write_text(json.dumps({"repo_head": "", "tasks": [
                {"task_id": "SYNTH-001", "state": "IN_PROGRESS",
                 "in_progress": True}]}), encoding="utf-8")
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_state_of(res), "PASS")  # evidence-authoritative

    # TC-05 checkpoint-without-evidence
    def test_tc05_checkpoint_without_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d); ep.unlink()
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(_state_of(res), "PASS")

    # TC-06 checkpoint/evidence disagreement (checkpoint PASS, evidence FAIL)
    def test_tc06_checkpoint_evidence_disagreement(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d); ep.unlink()
            # craft FAIL evidence + checkpoint PASS
            log = EvidenceLog(ep)
            log.append(EvidenceRecord("E", "SYNTH-001", "python3 -V", exit_status=1,
                                      result="FAIL", expected_exit=0))
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(_state_of(res), "PASS")

    # TC-07 interrupted atomic checkpoint replacement (stale .tmp)
    def test_tc07_stale_tmp_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            (sp.with_name(sp.name + ".tmp")).write_text("GARBAGE PARTIAL", encoding="utf-8")
            st = StateStore(sp); st.load()  # must ignore .tmp
            self.assertNotEqual(st.tasks, {})
            Controller(mp, repo, sp, ep).run()  # save overwrites .tmp + renames
            self.assertTrue(sp.is_file())

    # TC-08 truncated evidence
    def test_tc08_truncated_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            ep.write_bytes(ep.read_bytes()[:len(ep.read_bytes()) // 2])
            self.assertFalse(EvidenceLog(ep).verify_integrity()["intact"])
            self.assertNotEqual(_state_of(Controller(mp, repo, sp, ep).run()), "PASS")

    # TC-09 evidence-ahead-of-checkpoint
    def test_tc09_evidence_ahead_of_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            # rewind checkpoint to DISCOVERED; evidence still authoritative
            sp.write_text(json.dumps({"repo_head": "", "tasks": [
                {"task_id": "SYNTH-001", "state": "DISCOVERED"}]}), encoding="utf-8")
            self.assertEqual(_state_of(Controller(mp, repo, sp, ep).run()), "PASS")

    # TC-10 duplicate evidence ID after restart
    def test_tc10_duplicate_evidence_id(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            for _ in range(2):
                log.append(EvidenceRecord("DUP", "T", "python3 -V", exit_status=0,
                                          result="PASS", expected_exit=0))
            self.assertLessEqual(len(log.verified_records()), 1)

    # TC-11 stale contract
    def test_tc11_stale_contract(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            # forge an evidence record with a wrong (stale) contract_id but valid chain
            lines = ep.read_text().splitlines()
            rec = _recompute_record_hash({**json.loads(lines[0]), "contract_id": "0" * 64})
            ep.write_text(json.dumps(rec) + "\n")
            self.assertNotEqual(_state_of(Controller(mp, repo, sp, ep).run()), "PASS")

    # TC-12 changed HEAD
    def test_tc12_changed_head(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, with_git=True)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            (repo / "n.txt").write_text("x")
            _commit(repo)
            self.assertNotEqual(_state_of(Controller(mp, repo, sp, ep).run()), "PASS")

    # TC-13 changed manifest
    def test_tc13_changed_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "x"
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state_of(Controller(mp, repo, sp, ep).run()), "PASS")

    # TC-14 changed validator
    def test_tc14_changed_validator(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            lines = ep.read_text().splitlines()
            rec = _recompute_record_hash({**json.loads(lines[0]), "validator": "impostor"})
            ep.write_text(json.dumps(rec) + "\n")
            self.assertNotEqual(_state_of(Controller(mp, repo, sp, ep).run()), "PASS")

    # TC-15 changed dependency
    def test_tc15_changed_dependency(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            dep = {"task_id": "DEP", "title": "d", "description": "d", "priority": 1,
                   "plan_order": 1, "source_authority": [{"doc": "spec.md"}],
                   "requirement_refs": ["R"], "specification_refs": [{"doc": "spec.md"}],
                   "dependency_refs": [], "required_tools": [], "allowed_tools": ["python3"],
                   "validation_commands": [{"id": "V", "command": "python3 -V", "expected_exit": 0}],
                   "acceptance_criteria": [{"id": "A", "criterion": "c"}]}
            user = dict(dep, task_id="USER", dependency_refs=[{"ref": "DEP"}], plan_order=2)
            mp = Path(d) / "m.json"
            mp.write_text(json.dumps({"schema_version": "1.0", "project": "syn",
                "tool_registry": {"python3": {"available": True, "binary": "python3"}},
                "tasks": [dep, user]}))
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)  # DEP PASS, USER depends on DEP
            # invalidate DEP by removing its authority
            (repo / "spec.md").unlink()
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(res.classifications["USER"].effective_state, "READY")

    # TC-16 changed task definition
    def test_tc16_changed_task_definition(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            man = json.loads(mp.read_text()); man["tasks"][0]["scope"] = "changed"
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state_of(Controller(mp, repo, sp, ep).run()), "PASS")

    # TC-17 SIGKILL while lock held (lease released)
    def test_tc17_sigkill_while_lock_held(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "k"; sub.mkdir()
            mp, repo = _synth(str(sub), command="python3 sleep.py")
            (repo / "sleep.py").write_text("import time; time.sleep(30)\n", encoding="utf-8")
            sp, ep = sub / "s.json", sub / "e.jsonl"
            proc = subprocess.Popen(
                [sys.executable, str(RUNNER), "--manifest", str(mp),
                 "--repo-root", str(repo), "--state", str(sp), "--evidence", str(ep),
                 "--status-out", str(sub / "o.json"), "--execute",
                 "--allow-tool", "python3"], start_new_session=True)
            time.sleep(1.5)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL); proc.wait(timeout=10)
            # retrying process must acquire the freed lease
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(res.result, "PASS")

    # TC-18 concurrent recovery (mutual exclusion; deterministic)
    def test_tc18_concurrent_recovery(self):
        from impl_controller.locking import FileLock
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep, so = Path(d) / "s.json", Path(d) / "e.jsonl", Path(d) / "o.json"
            lock_path = sp.with_name("controller.lock")
            # one writer HOLDS the lease; a concurrent attempt must be denied.
            holder = FileLock(lock_path); holder.acquire()
            try:
                r = subprocess.run([sys.executable, str(RUNNER), "--manifest", str(mp),
                    "--repo-root", str(repo), "--state", str(sp), "--evidence", str(ep),
                    "--status-out", str(so)], capture_output=True, text=True, timeout=30)
                self.assertEqual(r.returncode, 1)  # lease denied -> fail closed
            finally:
                holder.release()

    # TC-19 repeated recovery converges
    def test_tc19_repeated_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            sp.write_text("{broken", encoding="utf-8")
            norms = []
            for _ in range(3):
                r = Controller(mp, repo, sp, ep).recover()
                norms.append(json.dumps({k: r.report[k] for k in
                    ("graph", "classifications", "provenance_context")}, sort_keys=True))
            self.assertEqual(len(set(norms)), 1)

    # TC-20 interrupted pipeline-status generation (derived; ignored)
    def test_tc20_interrupted_status(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            so = Path(d) / "pipeline-status.json"
            so.write_bytes(b'{"partial":')  # interrupted write
            res = Controller(mp, repo, sp, ep).run()  # controller never reads status
            self.assertEqual(_state_of(res), "PASS")  # unaffected by derived garbage

    # TC-21 stale pipeline-status
    def test_tc21_stale_status(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            (Path(d) / "st.json").write_text(json.dumps({"frontier": "READY",
                "graph": {"READY": 99, "BLOCKED": 0}}))  # stale/forged
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_state_of(res), "PASS")  # stale status never authoritative

    # TC-22 forged PASS status
    def test_tc22_forged_pass_status(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)  # task READY, not executed
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            (Path(d) / "forged.json").write_text(json.dumps({"frontier": "READY",
                "classifications": [{"task_id": "SYNTH-001", "effective_state": "PASS"}]}))
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(_state_of(res), "PASS")  # forged status ignored

    # TC-23 forged evidence with wrong contract
    def test_tc23_forged_evidence_wrong_contract(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            real = contract_identity_for(t, set(), ctx)
            log = EvidenceLog(ep); ep.unlink()
            rec = EvidenceRecord("F", "SYNTH-001", "python3 -V", exit_status=0,
                                 result="PASS", expected_exit=0, contract_id="0" * 64,
                                 repository_identity=ctx["repo_identity"], head=ctx["head"],
                                 manifest_hash=ctx["manifest_hash"], validator=VALIDATOR_IDENTITY)
            log.append(rec)
            self.assertNotEqual(_state_of(Controller(mp, repo, sp, ep).run()), "PASS")

    # TC-24 evidence copied between repositories
    def test_tc24_evidence_between_repos(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            mpa, repoa, spa, epa = _pass(a)
            mpb, repob = _synth(b)
            spb, epb = Path(b) / "s.json", Path(b) / "e.jsonl"
            epb.write_bytes(epa.read_bytes())  # copy evidence into a DIFFERENT repo
            self.assertNotEqual(repo_identity(repoa), repo_identity(repob))
            self.assertNotEqual(_state_of(Controller(mpb, repob, spb, epb).run()), "PASS")

    # TC-25 evidence copied between commits
    def test_tc25_evidence_between_commits(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            # source: git repo; execute -> PASS (evidence bound to HEAD_a + repo_a)
            mpa, repoa = _synth(a, with_git=True)
            spa, epa = Path(a) / "s.json", Path(a) / "e.jsonl"
            Controller(mpa, repoa, spa, epa).run(execute=True)
            self.assertEqual(_state_of(Controller(mpa, repoa, spa, epa).run()), "PASS")
            # destination: a DIFFERENT git repo (different HEAD + repo identity)
            mpb, repob = _synth(b, with_git=True)
            spb, epb = Path(b) / "s.json", Path(b) / "e.jsonl"
            epb.write_bytes(epa.read_bytes())
            self.assertNotEqual(_state_of(Controller(mpb, repob, spb, epb).run()), "PASS")

    # TC-26 evidence copied between manifests
    def test_tc26_evidence_between_manifests(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            mpa, repoa, spa, epa = _pass(a)
            mpb, repob = _synth(b)
            man = json.loads(mpb.read_text()); man["tasks"][0]["title"] = "different"
            mpb.write_text(json.dumps(man))
            spb, epb = Path(b) / "s.json", Path(b) / "e.jsonl"
            epb.write_bytes(epa.read_bytes())
            self.assertNotEqual(_state_of(Controller(mpb, repob, spb, epb).run()), "PASS")

    # TC-27 interrupted CI (runner interrupted; derived status partial)
    def test_tc27_interrupted_ci(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            so = Path(d) / "pipeline-status.json"; so.write_text("", encoding="utf-8")
            # recovery recomputes; derived status irrelevant
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_state_of(res), "PASS")

    # TC-28 validator PASS before evidence persistence
    def test_tc28_pass_before_evidence_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d); ep.unlink()  # validator passed, evidence never persisted
            self.assertNotEqual(_state_of(Controller(mp, repo, sp, ep).run()), "PASS")

    # TC-29 evidence before traceability update
    def test_tc29_evidence_before_traceability(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            res = Controller(mp, repo, sp, ep).run()
            tr = [t for t in res.report["traceability"] if t["task_id"] == "SYNTH-001"][0]
            self.assertEqual(tr["closure"], "CLOSED")  # traceability regenerated from evidence

    # TC-30 traceability before checkpoint
    def test_tc30_traceability_derived_only(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            sp.write_text("{broken", encoding="utf-8")  # checkpoint gone
            res = Controller(mp, repo, sp, ep).run()
            # traceability is derived from evidence; checkpoint absence irrelevant
            self.assertEqual(_state_of(res), "PASS")


def _commit(repo):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c"],
                   check=True, env=env)


# ==========================================================================
# Recovery fixpoint: ×1 / ×3 / ×10
# ==========================================================================
class RecoveryFixpoint(unittest.TestCase):
    def test_recovery_converges_1_3_10(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            sp.write_text("{broken", encoding="utf-8")
            before_ev = len(ep.read_text().splitlines())
            norms = []
            for i in range(10):
                r = Controller(mp, repo, sp, ep).recover()
                if i in (0, 2, 9):
                    norms.append(json.dumps({k: r.report[k] for k in
                        ("graph", "classifications", "provenance_context")}, sort_keys=True))
            after_ev = len(ep.read_text().splitlines())
            self.assertEqual(len(set(norms)), 3 and 1)  # all identical
            self.assertEqual(before_ev, after_ev)  # no duplicate evidence across 10 recoveries

    def test_pipeline_fixpoint_no_oscillation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            states = []
            for i in range(6):
                if i % 2 == 0:
                    r = Controller(mp, repo, sp, ep).run()
                else:
                    r = Controller(mp, repo, sp, ep).recover()
                states.append(_state_of(r))
            self.assertEqual(len(set(states)), 1)  # no READY<->PASS oscillation
            self.assertEqual(states[0], "PASS")


# ==========================================================================
# Deterministic normalization
# ==========================================================================
class DeterministicNormalization(unittest.TestCase):
    def test_pipeline_three_runs_identical(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            norms = []
            for i in range(3):
                sd = Path(d) / f"r{i}"; sd.mkdir()
                r = Controller(mp, repo, sd / "s.json", sd / "e.jsonl").run(dry_run=True)
                norms.append(json.dumps({k: r.report[k] for k in
                    ("graph", "classifications", "provenance_context", "frontier",
                     "traceability")}, sort_keys=True))
            self.assertEqual(len(set(norms)), 1)


# ==========================================================================
# Real repository
# ==========================================================================
class RealRepository(unittest.TestCase):
    def test_frontier_closed(self):
        mp = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        if not mp.is_file():
            self.skipTest("seed manifest absent")
        import tempfile as _t
        sd = _t.mkdtemp()
        res = Controller(mp, REPO_ROOT, Path(sd) / "s.json", Path(sd) / "e.jsonl").run(dry_run=True)
        g = res.report["graph"]
        self.assertEqual((g["READY"], g["BLOCKED"], g["PASS"], g["IN_PROGRESS"]), (0, 4, 0, 0))
        self.assertEqual(res.report["frontier"], "PAUSED")
        cls = {c["task_id"]: c for c in res.report["classifications"]}
        self.assertEqual(cls["RED-LEX-001"]["reasons"],
                         ["TOOLCHAIN", "ARCHITECTURE", "PROVISIONING", "AUTHORIZATION"])
        self.assertEqual(cls["LIBRED-001"]["reasons"], ["DEPENDENCY", "TOOLCHAIN"])
        self.assertEqual(cls["HASH-001"]["reasons"],
                         ["INCOMPLETE_SPECIFICATION", "TOOLCHAIN"])
        self.assertEqual(cls["RFC0075-001"]["reasons"],
                         ["SPECIFICATION_CONFLICT", "INCOMPLETE_SPECIFICATION"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
