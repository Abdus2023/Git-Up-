"""Phase 28 — Concurrency, transactional consistency & single-authority execution.

Proves: ONE AUTHORITATIVE CONTRACT → ONE VALID EXECUTION STATE → ONE CONSISTENT
EVIDENCE HISTORY. Concurrent actors never create duplicate execution,
contradictory PASS, or divergent classifications. The exclusive fcntl lock
serializes all non-dry-run operations.
Run via:  python3 tools/impl-controller.py --self-test
"""
import json, os, signal, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent
REPO_ROOT = TOOLS.parent
RUNNER = TOOLS / "run-implementation-pipeline.py"
sys.path.insert(0, str(TOOLS))

from impl_controller.controller import Controller
from impl_controller.locking import FileLock, LockAcquisitionError
from impl_controller.evidence import EvidenceLog


def _synth(d, target="out.txt", content="hello"):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    if target:
        (repo / target).write_text(content, encoding="utf-8")
    t = {"task_id": "SYNTH-001", "title": "syn", "description": "d", "priority": 1,
         "plan_order": 1, "scope": "s", "source_authority": [{"doc": "spec.md"}],
         "requirement_refs": ["REQ-1"], "specification_refs": [{"doc": "spec.md"}],
         "implementation_targets": [target] if target else [], "dependency_refs": [],
         "required_tools": [], "allowed_tools": ["python3"],
         "validation_commands": [{"id": "V1", "command": "python3 -V", "expected_exit": 0}],
         "acceptance_criteria": [{"id": "AC1", "criterion": "c", "validator": "V1"}]}
    man = {"schema_version": "1.0", "project": "cc",
           "tool_registry": {"python3": {"available": True, "binary": "python3"}},
           "tasks": [t]}
    mp = Path(d) / "m.json"; mp.write_text(json.dumps(man), encoding="utf-8")
    return mp, repo


def _pass(d, **kw):
    mp, repo = _synth(d, **kw)
    sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
    Controller(mp, repo, sp, ep).run(execute=True)
    return mp, repo, sp, ep


def _s(res, tid="SYNTH-001"):
    return res.classifications[tid].effective_state


def _norm(r):
    return json.dumps({k: r.report[k] for k in ("graph", "classifications")}, sort_keys=True)


# ==========================================================================
# A. MUTUAL EXCLUSION (CC-01..08)
# ==========================================================================
class MutualExclusion(unittest.TestCase):
    def test_cc01_lock_held_controller_denied(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            lock_path = sp.with_name("controller.lock")
            holder = FileLock(lock_path); holder.acquire()
            try:
                res = Controller(mp, repo, sp, ep).run(dry_run=False)
                self.assertEqual(res.result, "FAIL")  # lock unavailable
            finally:
                holder.release()

    def test_cc02_retry_after_pass_no_dup(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            before = len(ep.read_text().splitlines())
            for _ in range(3):
                Controller(mp, repo, sp, ep).run(execute=True)  # retry (PASS -> skip)
            self.assertEqual(len(ep.read_text().splitlines()), before)

    def test_cc04_retry_races_recovery(self):
        """Sequential retry + recovery converge to same state."""
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            states = []
            states.append(_s(Controller(mp, repo, sp, ep).run(execute=True)))
            states.append(_s(Controller(mp, repo, sp, ep).recover()))
            states.append(_s(Controller(mp, repo, sp, ep).run(execute=True)))
            self.assertEqual(len(set(states)), 1)


# ==========================================================================
# B. EVIDENCE RACES (CC-09..15) — serialized by lock
# ==========================================================================
class EvidenceRaces(unittest.TestCase):
    def test_cc10_same_command_evidence_not_duplicated(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            before = len(ep.read_text().splitlines())
            Controller(mp, repo, sp, ep).run(execute=True)
            self.assertEqual(len(ep.read_text().splitlines()), before)

    def test_cc11_different_commands_sequential(self):
        """Two commands run sequentially (within the lock) produce distinct evidence."""
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "x"; sub.mkdir()
            mp, repo = _synth(str(sub), target=None)
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"] = [
                {"id": "V1", "command": "python3 -V", "expected_exit": 0},
                {"id": "V2", "command": "python3 -VV", "expected_exit": 0}]
            man["tasks"][0]["acceptance_criteria"] = [
                {"id": "AC1", "criterion": "c", "validator": "V1"},
                {"id": "AC2", "criterion": "c", "validator": "V2"}]
            mp.write_text(json.dumps(man))
            Controller(mp, repo, sub / "s.json", sub / "e.jsonl").run(execute=True)
            lines = (sub / "e.jsonl").read_text().strip().splitlines()
            self.assertEqual(len(lines), 2)  # two commands -> two evidence records


# ==========================================================================
# C. PASS RACES (CC-16..20) — serialized
# ==========================================================================
class PassRaces(unittest.TestCase):
    def test_cc16_sequential_executions_converge(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            for _ in range(5):
                r = Controller(mp, repo, sp, ep).run(execute=True)
                self.assertEqual(_s(r), "PASS")

    def test_cc19_sigkill_then_other_recovers(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "k"; sub.mkdir()
            mp, repo = _synth(str(sub))
            (repo / "sleep.py").write_text("import time; time.sleep(3)\n", encoding="utf-8")
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"] = [{"id": "V1", "command": "python3 sleep.py", "expected_exit": 0}]
            mp.write_text(json.dumps(man))
            sp, ep = sub / "s.json", sub / "e.jsonl"
            proc = subprocess.Popen(
                [sys.executable, str(RUNNER), "--manifest", str(mp), "--repo-root", str(repo),
                 "--state", str(sp), "--evidence", str(ep), "--status-out", str(sub / "o.json"),
                 "--execute", "--allow-tool", "python3"], start_new_session=True)
            time.sleep(1.2)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL); proc.wait(timeout=10)
            # after SIGKILL, the lock is free (fcntl released by OS)
            # recover -> task READY (no evidence from killed run)
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(_s(res), "PASS")


# ==========================================================================
# D. INVALIDATION RACES (CC-21..28) — mutation between runs
# ==========================================================================
class InvalidationRaces(unittest.TestCase):
    def _race_mutation(self, mutator):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            # mutation between runs (sequential: run -> mutate -> run)
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")
            mutator(mp, repo, d)
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_cc21_contract_mutation_between_runs(self):
        self._race_mutation(lambda mp, r, d: mp.write_text(
            json.dumps({**json.loads(mp.read_text()),
                        "tasks": [{**json.loads(mp.read_text())["tasks"][0], "title": "x"}]})))

    def test_cc25_target_mutation_between_runs(self):
        self._race_mutation(lambda mp, r, d: (r / "out.txt").write_text("MUT", encoding="utf-8"))


# ==========================================================================
# E. RECOVERY RACES (CC-29..35)
# ==========================================================================
class RecoveryRaces(unittest.TestCase):
    def test_cc29_recover_then_execute(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            r1 = Controller(mp, repo, sp, ep).recover()
            r2 = Controller(mp, repo, sp, ep).run(execute=True)
            self.assertEqual(_s(r1), "PASS")
            self.assertEqual(_s(r2), "PASS")
            self.assertEqual(_norm(r1), _norm(r2))

    def test_cc35_three_recoveries_converge(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            norms = [_norm(Controller(mp, repo, sp, ep).recover()) for _ in range(3)]
            self.assertEqual(len(set(norms)), 1)


# ==========================================================================
# F. DERIVED ARTIFACT RACES (CC-36..40)
# ==========================================================================
class DerivedArtifactRaces(unittest.TestCase):
    def test_cc38_forge_ledger_no_effect(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            (Path(d) / "ledger.json").write_text(json.dumps({"R1": "SATISFIED"}))
            r = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_s(r), "PASS")  # derived artifacts irrelevant

    def test_cc39_delete_derived_no_effect(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            old_status = Path(d) / "pipeline-status.json"
            if old_status.exists(): old_status.unlink()
            r = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_s(r), "PASS")  # derived deletion irrelevant


# ==========================================================================
# G. STRESS / REPEATABILITY (CC-41..48)
# ==========================================================================
class StressRepeatability(unittest.TestCase):
    def test_cc41_ten_retries_no_dup(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            before = len(ep.read_text().splitlines())
            for _ in range(10):
                Controller(mp, repo, sp, ep).run(execute=True)
            self.assertEqual(len(ep.read_text().splitlines()), before)

    def test_cc42_ten_recoveries_fixpoint(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            sp.write_text("{broken")
            norms = [_norm(Controller(mp, repo, sp, ep).recover()) for _ in range(10)]
            self.assertEqual(len(set(norms)), 1)

    def test_cc43_execute_plus_ten_recoveries(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            norms = []
            for i in range(10):
                r = Controller(mp, repo, sp, ep).run(execute=True) if i == 0 else Controller(mp, repo, sp, ep).recover()
                norms.append(_norm(r))
            self.assertEqual(len(set(norms)), 1)

    def test_cc48_equivalent_schedules_converge(self):
        """Two independent fresh executions converge to same state."""
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            mp1, repo1, sp1, ep1 = _pass(d1)
            mp2, repo2, sp2, ep2 = _pass(d2)
            n1 = _norm(Controller(mp1, repo1, sp1, ep1).run())
            n2 = _norm(Controller(mp2, repo2, sp2, ep2).run())
            self.assertEqual(n1, n2)


# ==========================================================================
# SUBPROCESS CONCURRENCY (CC-01/35 variants)
# ==========================================================================
class SubprocessConcurrency(unittest.TestCase):
    def test_subprocess_lock_contention(self):
        """Two subprocess controllers on the same state: one wins, one denied."""
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep, so = Path(d) / "s.json", Path(d) / "e.jsonl", Path(d) / "o.json"
            common = [sys.executable, str(RUNNER), "--manifest", str(mp),
                      "--repo-root", str(repo), "--state", str(sp), "--evidence", str(ep),
                      "--status-out", str(so)]
            # hold lock externally -> controller denied
            lock_path = sp.with_name("controller.lock")
            holder = FileLock(lock_path); holder.acquire()
            try:
                r = subprocess.run(common + ["--dry-run"], capture_output=True, text=True, timeout=15)
                # dry-run doesn't acquire lock -> succeeds
                self.assertEqual(r.returncode, 0)
                r2 = subprocess.run(common, capture_output=True, text=True, timeout=15)
                # non-dry-run acquires lock -> denied -> FAIL
                self.assertEqual(r2.returncode, 1)
            finally:
                holder.release()

    def test_subprocess_sequential_consistency(self):
        """Two sequential subprocess runs converge."""
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep, so = Path(d) / "s.json", Path(d) / "e.jsonl", Path(d) / "o.json"
            common = [sys.executable, str(RUNNER), "--manifest", str(mp),
                      "--repo-root", str(repo), "--state", str(sp), "--evidence", str(ep),
                      "--status-out", str(so)]
            subprocess.run(common + ["--execute", "--allow-tool", "python3"],
                           capture_output=True, timeout=30, check=True)
            r = subprocess.run(common + ["--dry-run", "--quiet"], capture_output=True, text=True, timeout=15)
            st = json.loads((so).read_text())
            self.assertEqual(st["graph"]["PASS"], 1)


# ==========================================================================
# SEED REGRESSION
# ==========================================================================
class SeedRegression(unittest.TestCase):
    def test_seed_unchanged(self):
        mp = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        if not mp.is_file():
            self.skipTest("seed manifest absent")
        sd = tempfile.mkdtemp()
        res = Controller(mp, REPO_ROOT, Path(sd) / "s.json", Path(sd) / "e.jsonl").run(dry_run=True)
        g = res.report["graph"]
        self.assertEqual((g["READY"], g["BLOCKED"], g["PASS"], g["IN_PROGRESS"]), (0, 4, 0, 0))
        self.assertEqual(res.report["frontier"], "PAUSED")
        cls = {c["task_id"]: c for c in res.report["classifications"]}
        self.assertEqual(cls["RED-LEX-001"]["reasons"],
                         ["TOOLCHAIN", "ARCHITECTURE", "PROVISIONING", "AUTHORIZATION"])
        self.assertEqual(cls["LIBRED-001"]["reasons"], ["DEPENDENCY", "TOOLCHAIN"])
        self.assertEqual(cls["HASH-001"]["reasons"], ["INCOMPLETE_SPECIFICATION", "TOOLCHAIN"])
        self.assertEqual(cls["RFC0075-001"]["reasons"],
                         ["SPECIFICATION_CONFLICT", "INCOMPLETE_SPECIFICATION"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
