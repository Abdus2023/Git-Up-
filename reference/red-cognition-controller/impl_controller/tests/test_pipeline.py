"""Integration tests for the implementation pipeline (Stage-5) contract.

Exercises the runner end-to-end on synthetic tasks (planner -> controller ->
executor -> validator -> status) and against the real repository, and asserts
the blocker-immutability + traceability-handoff properties.

Run via:  python3 tools/impl-controller.py --self-test
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent
RUNNER = TOOLS / "run-implementation-pipeline.py"
REPO_ROOT = TOOLS.parent
PY = sys.executable


def _run(args, **kw):
    return subprocess.run([PY, str(RUNNER)] + args, capture_output=True,
                          text=True, **kw)


def _synth(d):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    man = {
        "schema_version": "1.0", "project": "syn",
        "tool_registry": {"python3": {"available": True}},
        "tasks": [{
            "task_id": "SYNTH-001", "title": "syn", "description": "d",
            "priority": 1, "plan_order": 1, "scope": "s",
            "source_authority": [{"doc": "spec.md"}],
            "requirement_refs": ["REQ-1"],
            "specification_refs": [{"doc": "spec.md"}],
            "implementation_targets": ["out.txt"],
            "dependency_refs": [], "required_tools": [],
            "allowed_tools": ["python3"],
            "validation_commands": [{"id": "V1", "command": "python3 -V",
                                     "expected_exit": 0}],
            "acceptance_criteria": [{"id": "A1", "criterion": "c"}],
        }],
    }
    mp = Path(d) / "m.json"; mp.write_text(json.dumps(man), encoding="utf-8")
    return mp, repo


class P_SyntheticLifecycle(unittest.TestCase):
    def test_end_to_end_and_traceability(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            st = Path(d) / "state.json"; ev = Path(d) / "ev.jsonl"
            so = Path(d) / "status.json"
            # execute lifecycle
            r = _run(["--manifest", str(mp), "--repo-root", str(repo),
                      "--state", str(st), "--evidence", str(ev),
                      "--status-out", str(so), "--execute", "--allow-tool",
                      "python3", "--quiet"], cwd=str(REPO_ROOT))
            self.assertEqual(r.returncode, 0, r.stderr)
            status = json.loads(so.read_text())
            # stage contract
            self.assertEqual(status["planner"]["status"], "OK")
            self.assertTrue(status["stages"]["executor"]["attempted"])
            self.assertEqual(status["stages"]["validator"]["pass"], 1)
            self.assertEqual(status["stages"]["validator"]["fail"], 0)
            self.assertTrue(status["evidence_integrity"]["intact"])
            # lifecycle: PASS via verified evidence
            self.assertEqual(status["classifications"][0]["effective_state"], "PASS")
            # traceability handoff carries the full chain
            tr = status["traceability"][0]
            self.assertEqual(tr["task_id"], "SYNTH-001")
            self.assertEqual(tr["status"], "PASS")
            self.assertEqual(tr["requirement_refs"], ["REQ-1"])
            self.assertIn("spec.md", tr["source_authority"])
            self.assertEqual(tr["validation_commands"], ["V1"])
            self.assertTrue(tr["evidence_refs"])  # evidence linked

    def test_drift_invalidates_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            st = Path(d) / "state.json"; ev = Path(d) / "ev.jsonl"
            so = Path(d) / "status.json"
            _run(["--manifest", str(mp), "--repo-root", str(repo), "--state",
                  str(st), "--evidence", str(ev), "--status-out", str(so),
                  "--execute", "--allow-tool", "python3", "--quiet"],
                 cwd=str(REPO_ROOT))
            (repo / "spec.md").unlink()           # authority drift
            r2 = _run(["--manifest", str(mp), "--repo-root", str(repo),
                       "--state", str(st), "--evidence", str(ev),
                       "--status-out", str(so), "--quiet"], cwd=str(REPO_ROOT))
            self.assertEqual(r2.returncode, 0)
            status = json.loads(so.read_text())
            self.assertEqual(status["classifications"][0]["effective_state"], "BLOCKED")
            self.assertNotEqual(status["classifications"][0]["effective_state"], "PASS")


class P_PlannerGate(unittest.TestCase):
    def test_bad_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir()
            mp = Path(d) / "m.json"
            mp.write_text(json.dumps({"schema_version": "1.0", "project": "x",
                                       "tool_registry": {}, "tasks": []}),
                          encoding="utf-8")
            r = _run(["--manifest", str(mp), "--repo-root", str(repo),
                      "--state", str(Path(d) / "s.json"),
                      "--status-out", str(Path(d) / "o.json"), "--quiet"],
                     cwd=str(REPO_ROOT))
            self.assertEqual(r.returncode, 2, r.stdout)


class P_RealRepo(unittest.TestCase):
    def setUp(self):
        self.manifest = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        self.assume = self.manifest.is_file()

    def _dry(self, d):
        so = Path(d) / "status.json"
        r = _run(["--manifest", str(self.manifest), "--repo-root", str(REPO_ROOT),
                  "--state", str(Path(d) / "s.json"),
                  "--evidence", str(Path(d) / "e.jsonl"),
                  "--status-out", str(so), "--dry-run", "--quiet"],
                 cwd=str(REPO_ROOT))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(so.read_text())

    def test_real_frontier_paused(self):
        if not self.assume:
            self.skipTest("seed manifest absent")
        with tempfile.TemporaryDirectory() as d:
            st = self._dry(d)
            self.assertEqual(st["frontier"], "PAUSED")
            self.assertEqual(st["graph"]["READY"], 0)
            self.assertGreaterEqual(st["graph"]["BLOCKED"], 4)
            for tid in ("RED-LEX-001", "LIBRED-001", "HASH-001", "RFC0075-001"):
                cls = {c["task_id"]: c for c in st["classifications"]}
                self.assertEqual(cls[tid]["effective_state"], "BLOCKED", tid)

    def test_blockers_immutable_across_runs(self):
        if not self.assume:
            self.skipTest("seed manifest absent")
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            s1 = self._dry(d1); s2 = self._dry(d2)
            c1 = {c["task_id"]: c for c in s1["classifications"]}
            c2 = {c["task_id"]: c for c in s2["classifications"]}
            for tid in ("RED-LEX-001", "LIBRED-001", "HASH-001", "RFC0075-001"):
                self.assertEqual(c1[tid]["effective_state"], "BLOCKED")
                self.assertEqual(c1[tid]["reasons"], c2[tid]["reasons"],
                                 f"{tid} classifications must be immutable")

    def test_traceability_handoff_complete(self):
        if not self.assume:
            self.skipTest("seed manifest absent")
        with tempfile.TemporaryDirectory() as d:
            st = self._dry(d)
            self.assertEqual(len(st["traceability"]), 4)
            for tr in st["traceability"]:
                self.assertTrue(tr["requirement_refs"], tr["task_id"])
                self.assertTrue(tr["source_authority"], tr["task_id"])
                self.assertEqual(tr["status"], "BLOCKED")
                self.assertTrue(tr["blocker_reasons"], tr["task_id"])
            self.assertTrue(st["evidence_integrity"]["intact"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
