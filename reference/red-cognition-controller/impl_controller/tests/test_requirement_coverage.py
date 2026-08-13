"""Stage-5 cross-task requirement coverage & ledger closure (Phase 25).

Central invariant: TASK PASS does NOT imply REQUIREMENT SATISFIED. The
requirement ledger is DERIVED from authoritative task PASS state — it can never
authorize PASS. Coverage is explicitly declared, never inferred.
Run via:  python3 tools/impl-controller.py --self-test
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from impl_controller.provenance import coverage_identity, requirement_statuses
from impl_controller.controller import Controller


def _manifest(tasks, requirements=None):
    return {"schema_version": "1.0", "project": "rc",
            "tool_registry": {"python3": {"available": True, "binary": "python3"},
                              "rebol-278": {"available": False}},
            "tasks": tasks, "requirements": requirements or []}


def _task(tid, blocked=False):
    t = {"task_id": tid, "title": tid, "description": "d", "priority": 1,
         "plan_order": 1, "source_authority": [{"doc": "spec.md"}],
         "requirement_refs": ["REQ-1"], "specification_refs": [{"doc": "spec.md"}],
         "implementation_targets": [], "dependency_refs": [],
         "allowed_tools": ["python3"],
         "validation_commands": [{"id": "V1", "command": "python3 -V", "expected_exit": 0}],
         "acceptance_criteria": [{"id": "A1", "criterion": "c"}]}
    if blocked:
        t["required_tools"] = ["rebol-278"]
    return t


def _req(rid, task_ids):
    return {"id": rid, "specification_refs": ["spec.md"],
            "coverage": [{"task_id": t, "obligations": [f"OBL-{t}"]} for t in task_ids]}


def _setup(d, tasks, requirements):
    repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
    mp = Path(d) / "m.json"
    mp.write_text(json.dumps(_manifest(tasks, requirements)))
    return mp, repo


def _execute_all(mp, repo, d):
    """Execute tasks until none are READY."""
    sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
    for _ in range(10):
        res = Controller(mp, repo, sp, ep).run(execute=True)
        if not res.ready_queue:
            break
    return sp, ep


def _ledger(res):
    return {r["requirement_id"]: r for r in res.report["requirement_ledger"]}


# ==========================================================================
class CoverageIdentity(unittest.TestCase):
    def test_rc09_reorder_same_identity(self):
        from impl_controller.model import Requirement, CoverageEntry
        r1 = [Requirement("R", ["s"], [CoverageEntry("A", ["o"]), CoverageEntry("B", ["p"])])]
        r2 = [Requirement("R", ["s"], [CoverageEntry("B", ["p"]), CoverageEntry("A", ["o"])])]
        self.assertEqual(coverage_identity(r1), coverage_identity(r2))

    def test_rc10_mutated_different_identity(self):
        from impl_controller.model import Requirement, CoverageEntry
        r1 = [Requirement("R", ["s"], [CoverageEntry("A", ["o"])])]
        r2 = [Requirement("R", ["s"], [CoverageEntry("A", ["o"]), CoverageEntry("B", ["p"])])]
        self.assertNotEqual(coverage_identity(r1), coverage_identity(r2))


# ==========================================================================
class RequirementLedger(unittest.TestCase):
    def test_rc01_no_tasks_no_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1")], [_req("R1", [])])
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertEqual(_ledger(res)["R1"]["status"], "NO_COVERAGE")

    def test_rc25_single_pass_satisfied(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1")], [_req("R1", ["T1"])])
            _execute_all(mp, repo, d)
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertEqual(_ledger(res)["R1"]["status"], "SATISFIED")

    def test_rc03_pass_plus_blocked_partial(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1"), _task("T2", blocked=True)],
                              [_req("R1", ["T1", "T2"])])
            _execute_all(mp, repo, d)
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertEqual(_ledger(res)["R1"]["status"], "PARTIAL")

    def test_rc26_multi_partial(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1"), _task("T2", blocked=True)],
                              [_req("R1", ["T1", "T2"])])
            _execute_all(mp, repo, d)
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertEqual(_ledger(res)["R1"]["status"], "PARTIAL")

    def test_rc27_all_pass_satisfied(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1"), _task("T2")], [_req("R1", ["T1", "T2"])])
            _execute_all(mp, repo, d)
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertEqual(_ledger(res)["R1"]["status"], "SATISFIED")

    def test_rc28_one_invalidated_partial(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1"), _task("T2")], [_req("R1", ["T1", "T2"])])
            _execute_all(mp, repo, d)
            res0 = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertEqual(_ledger(res0)["R1"]["status"], "SATISFIED")
            (repo / "spec.md").unlink()  # invalidate all authority
            res1 = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertNotEqual(_ledger(res1)["R1"]["status"], "SATISFIED")

    def test_rc02_pass_does_not_imply_satisfied_for_other_req(self):
        # T1 PASS satisfies R1 but NOT R2 (which covers T2 not T1)
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1")], [_req("R1", ["T1"]), _req("R2", ["T2"])])
            _execute_all(mp, repo, d)
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertEqual(_ledger(res)["R1"]["status"], "SATISFIED")
            self.assertEqual(_ledger(res)["R2"]["status"], "BLOCKED")  # T2 not in manifest

    def test_rc15_no_pass_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1", blocked=True)], [_req("R1", ["T1"])])
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertEqual(_ledger(res)["R1"]["status"], "BLOCKED")

    def test_rc22_retry_no_duplicate_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1")], [_req("R1", ["T1"])])
            sp, ep = _execute_all(mp, repo, d)
            ledgers = []
            for _ in range(3):
                res = Controller(mp, repo, sp, ep).run()
                ledgers.append(json.dumps(_ledger(res), sort_keys=True))
            self.assertEqual(len(set(ledgers)), 1)


# ==========================================================================
class RequirementStatusDerived(unittest.TestCase):
    def test_rc11_ledger_is_derived_not_authoritative(self):
        # forging the report (derived) doesn't change task PASS
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _setup(d, [_task("T1", blocked=True)], [_req("R1", ["T1"])])
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            # T1 is BLOCKED -> ledger says BLOCKED
            self.assertEqual(_ledger(res)["R1"]["status"], "BLOCKED")
            # the ledger never authorized T1 to PASS
            self.assertNotEqual(res.classifications["T1"].effective_state, "PASS")


# ==========================================================================
class RealRepository(unittest.TestCase):
    def test_rc30_real_repository(self):
        mp = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        if not mp.is_file():
            self.skipTest("seed manifest absent")
        sd = tempfile.mkdtemp()
        res = Controller(mp, REPO_ROOT, Path(sd) / "s.json", Path(sd) / "e.jsonl").run(dry_run=True)
        g = res.report["graph"]
        self.assertEqual((g["READY"], g["BLOCKED"], g["PASS"], g["IN_PROGRESS"]), (0, 4, 0, 0))
        self.assertEqual(res.report["frontier"], "PAUSED")
        # seed has no requirements section -> empty ledger
        self.assertEqual(res.report["requirement_ledger"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
