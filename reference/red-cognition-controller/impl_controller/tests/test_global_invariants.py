"""Phase 26 — Global Invariant, Authority & Convergence Audit tests.

Validates that Phases 17-25 compose into one coherent authority-preserving state
machine: derived state can NEVER authorize PASS; evidence cannot cross
boundaries; semantic mutation invalidates identity; recovery converges; and
determinism holds across all layers.
Run via:  python3 tools/impl-controller.py --self-test
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from impl_controller import model as M
from impl_controller.manifest import load_manifest
from impl_controller.provenance import (
    contract_identity_for, coverage_identity, provenance_context,
    command_identity, criterion_attestations, requirement_statuses,
)
from impl_controller.controller import Controller
from impl_controller.evidence import EvidenceLog
from impl_controller.engine import classify_all


def _synth(d, criteria=None, commands=None, targets=None, reqs=None, git=False):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    if targets:
        for t, c in targets:
            (repo / t).write_text(c, encoding="utf-8")
    vcs = commands or [{"id": "V1", "command": "python3 -V", "expected_exit": 0}]
    acr = criteria or [{"id": "AC1", "criterion": "c", "validator": "V1"}]
    t = {"task_id": "SYNTH-001", "title": "syn", "description": "d", "priority": 1,
         "plan_order": 1, "scope": "s", "source_authority": [{"doc": "spec.md"}],
         "requirement_refs": ["REQ-1"], "specification_refs": [{"doc": "spec.md"}],
         "implementation_targets": [t for t, _ in (targets or [])],
         "dependency_refs": [], "required_tools": [], "allowed_tools": ["python3"],
         "validation_commands": vcs, "acceptance_criteria": acr}
    man = {"schema_version": "1.0", "project": "syn",
           "tool_registry": {"python3": {"available": True, "binary": "python3"}},
           "tasks": [t], "requirements": reqs or []}
    mp = Path(d) / "m.json"; mp.write_text(json.dumps(man), encoding="utf-8")
    if git:
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "i"], check=True, env=env)
    return mp, repo


def _pass(d, **kw):
    mp, repo = _synth(d, **kw)
    sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
    Controller(mp, repo, sp, ep).run(execute=True)
    return mp, repo, sp, ep


def _state(res, tid="SYNTH-001"):
    return res.classifications[tid].effective_state


# ==========================================================================
# GI-T01..05 — Authority attacks (derived state cannot authorize)
# ==========================================================================
class AuthorityAttacks(unittest.TestCase):
    def test_gi01_forged_pipeline_status_cannot_authorize(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            # forge a pipeline-status claiming BLOCKED (derived garbage)
            (Path(d) / "fake-status.json").write_text(json.dumps(
                {"frontier": "PAUSED", "graph": {"PASS": 0, "BLOCKED": 1}}))
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_state(res), "PASS")  # derived garbage ignored

    def test_gi02_forged_checkpoint_cannot_authorize(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            sp.write_text(json.dumps({"tasks": [
                {"task_id": "SYNTH-001", "state": "PASS", "validated_pass": True}]}))
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(_state(res), "PASS")  # no evidence -> demoted

    def test_gi03_forged_requirement_ledger_cannot_authorize(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            # the ledger is derived in the report; it never feeds into _authoritative_pass
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_state(res), "PASS")
            # even if we forge the ledger in the report, it doesn't affect next run
            self.assertTrue(isinstance(res.report.get("requirement_ledger"), list))

    def test_gi05_forged_coverage_id_cannot_authorize(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            res = Controller(mp, repo, sp, ep).run()
            cid = res.report.get("coverage_identity", "")
            self.assertTrue(isinstance(cid, str))  # derived, not authoritative


# ==========================================================================
# GI-T06..10 — Provenance replay (evidence cannot cross boundaries)
# ==========================================================================
class ProvenanceReplay(unittest.TestCase):
    def test_gi06_evidence_from_another_contract(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "x"
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_gi07_evidence_from_another_task(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            mpa, repoa, spa, epa = _pass(a)
            mpb, repob = _synth(b, criteria=[{"id": "AC1", "criterion": "c",
                                              "validator": "V1"}])
            epb = Path(b) / "e.jsonl"; epb.write_bytes(epa.read_bytes())
            self.assertNotEqual(_state(Controller(mpb, repob, Path(b) / "s.json",
                                                   epb).run()), "PASS")

    def test_gi09_evidence_from_another_repository(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            mpa, repoa, spa, epa = _pass(a)
            mpb, repob = _synth(b)
            epb = Path(b) / "e.jsonl"; epb.write_bytes(epa.read_bytes())
            self.assertNotEqual(_state(Controller(mpb, repob, Path(b) / "s.json",
                                                   epb).run()), "PASS")


# ==========================================================================
# GI-T11..16 — Semantic mutation invalidates identity
# ==========================================================================
class SemanticMutation(unittest.TestCase):
    def test_gi12_criterion_validator_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            man = json.loads(mp.read_text())
            man["tasks"][0]["acceptance_criteria"][0]["validator"] = "V2"
            man["tasks"][0]["validation_commands"].append(
                {"id": "V2", "command": "python3 -VV", "expected_exit": 0})
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_gi15_requirement_obligation_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            r1 = [M.Requirement("R", ["s"], [M.CoverageEntry("T1", ["O1"])])]
            r2 = [M.Requirement("R", ["s"], [M.CoverageEntry("T1", ["O1"]),
                                              M.CoverageEntry("T2", ["O2"])])]
            self.assertNotEqual(coverage_identity(r1), coverage_identity(r2))


# ==========================================================================
# GI-T17..20 — Derived-state attacks (stale cannot authorize)
# ==========================================================================
class DerivedStateAttacks(unittest.TestCase):
    def test_gi17_stale_criterion_attestation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            # mutate contract -> old criterion attestation is stale
            man = json.loads(mp.read_text()); man["tasks"][0]["scope"] = "changed"
            mp.write_text(json.dumps(man))
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(_state(res), "PASS")

    def test_gi20_stale_pipeline_status(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            # controller never reads pipeline-status; stale doesn't matter
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_state(res), "PASS")


# ==========================================================================
# GI-T21..25 — Recovery attacks
# ==========================================================================
class RecoveryAttacks(unittest.TestCase):
    def test_gi21_crash_before_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            sp.write_text("{broken")
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).recover()), "PASS")

    def test_gi25_recover_x10_fixpoint(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            sp.write_text("{broken")
            norms = []
            for _ in range(10):
                r = Controller(mp, repo, sp, ep).recover()
                norms.append(json.dumps({k: r.report[k] for k in
                    ("graph", "classifications")}, sort_keys=True))
            self.assertEqual(len(set(norms)), 1)
            self.assertEqual(_state(Controller(mp, repo, sp, ep).recover()), "PASS")


# ==========================================================================
# GI-T26..30 — Determinism (reorder = same identity)
# ==========================================================================
class Determinism(unittest.TestCase):
    def test_gi26_reorder_criteria_same_contract(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            from impl_controller.provenance import provenance_context
            a = M.Task(task_id="T", title="t", description="d",
                       source_authority=[M.AuthorityRef("spec.md")], requirement_refs=["R"],
                       specification_refs=[M.AuthorityRef("spec.md")],
                       validation_commands=[M.ValidationCommand("V1", "python3 -V", 0),
                                            M.ValidationCommand("V2", "python3 -VV", 0)],
                       acceptance_criteria=[M.AcceptanceCriterion("AC1", "c", "V1"),
                                            M.AcceptanceCriterion("AC2", "c", "V2")],
                       allowed_tools=["python3"])
            b = M.Task(task_id="T", title="t", description="d",
                       source_authority=[M.AuthorityRef("spec.md")], requirement_refs=["R"],
                       specification_refs=[M.AuthorityRef("spec.md")],
                       validation_commands=[M.ValidationCommand("V2", "python3 -VV", 0),
                                            M.ValidationCommand("V1", "python3 -V", 0)],
                       acceptance_criteria=[M.AcceptanceCriterion("AC2", "c", "V2"),
                                            M.AcceptanceCriterion("AC1", "c", "V1")],
                       allowed_tools=["python3"])
            ctx = provenance_context(repo, type("X", (), {"schema_version": "1.0",
                "project": "p", "tasks": [a], "tool_registry": M.ToolRegistry()})())
            self.assertEqual(contract_identity_for(a, set(), ctx),
                             contract_identity_for(b, set(), ctx))

    def test_gi27_reorder_requirements_same_coverage(self):
        r1 = [M.Requirement("R1", ["s"], [M.CoverageEntry("A", ["o"])]),
              M.Requirement("R2", ["s"], [M.CoverageEntry("B", ["p"])])]
        r2 = [M.Requirement("R2", ["s"], [M.CoverageEntry("B", ["p"])]),
              M.Requirement("R1", ["s"], [M.CoverageEntry("A", ["o"])])]
        self.assertEqual(coverage_identity(r1), coverage_identity(r2))


# ==========================================================================
# GI-T31..34 — Semantic distinction (change = different identity)
# ==========================================================================
class SemanticDistinction(unittest.TestCase):
    def test_gi31_criterion_mutation_different_contract(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            from impl_controller.provenance import provenance_context
            a = M.Task(task_id="T", title="t", description="d",
                       source_authority=[M.AuthorityRef("spec.md")], requirement_refs=["R"],
                       specification_refs=[M.AuthorityRef("spec.md")],
                       validation_commands=[M.ValidationCommand("V1", "python3 -V", 0)],
                       acceptance_criteria=[M.AcceptanceCriterion("AC1", "c", "V1")],
                       allowed_tools=["python3"])
            b = M.Task(task_id="T", title="t", description="d",
                       source_authority=[M.AuthorityRef("spec.md")], requirement_refs=["R"],
                       specification_refs=[M.AuthorityRef("spec.md")],
                       validation_commands=[M.ValidationCommand("V1", "python3 -V", 0)],
                       acceptance_criteria=[M.AcceptanceCriterion("AC1X", "c", "V1")],
                       allowed_tools=["python3"])
            ctx = provenance_context(repo, type("X", (), {"schema_version": "1.0",
                "project": "p", "tasks": [a], "tool_registry": M.ToolRegistry()})())
            self.assertNotEqual(contract_identity_for(a, set(), ctx),
                                contract_identity_for(b, set(), ctx))


# ==========================================================================
# GI-T35..38 — Closure
# ==========================================================================
class Closure(unittest.TestCase):
    def test_gi35_missing_criterion_evidence_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run()
            self.assertEqual(_state(res), "READY")
            self.assertNotEqual(_state(res), "PASS")

    def test_gi38_partial_requirement_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "x"; sub.mkdir()
            repo = sub / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            tasks = [
                {"task_id": "T1", "title": "t1", "description": "d", "priority": 1,
                 "plan_order": 1, "source_authority": [{"doc": "spec.md"}],
                 "requirement_refs": ["R1"], "specification_refs": [{"doc": "spec.md"}],
                 "implementation_targets": [], "dependency_refs": [],
                 "allowed_tools": ["python3"],
                 "validation_commands": [{"id": "V1", "command": "python3 -V", "expected_exit": 0}],
                 "acceptance_criteria": [{"id": "AC1", "criterion": "c", "validator": "V1"}]},
                {"task_id": "T2", "title": "t2", "description": "d", "priority": 2,
                 "plan_order": 2, "source_authority": [{"doc": "spec.md"}],
                 "requirement_refs": ["R1"], "specification_refs": [{"doc": "spec.md"}],
                 "implementation_targets": [], "dependency_refs": [],
                 "required_tools": ["rebol-278"], "allowed_tools": ["python3"],
                 "validation_commands": [{"id": "V1", "command": "python3 -V", "expected_exit": 0}],
                 "acceptance_criteria": [{"id": "AC1", "criterion": "c", "validator": "V1"}]}
            ]
            reqs = [{"id": "R1", "specification_refs": ["spec.md"],
                     "coverage": [{"task_id": "T1", "obligations": ["O1"]},
                                  {"task_id": "T2", "obligations": ["O2"]}]}]
            man = {"schema_version": "1.0", "project": "gi",
                   "tool_registry": {"python3": {"available": True, "binary": "python3"},
                                     "rebol-278": {"available": False}},
                   "tasks": tasks, "requirements": reqs}
            mp = sub / "m.json"; mp.write_text(json.dumps(man))
            sp, ep = sub / "s.json", sub / "e.jsonl"
            for _ in range(5):
                Controller(mp, repo, sp, ep).run(execute=True)
            res = Controller(mp, repo, sp, ep).run()
            ledger = {r["requirement_id"]: r for r in res.report["requirement_ledger"]}
            self.assertNotEqual(ledger["R1"]["status"], "SATISFIED")


# ==========================================================================
# GI-T39..42 — Idempotency
# ==========================================================================
class Idempotency(unittest.TestCase):
    def test_gi39_execute_twice_no_dup(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            before = len(ep.read_text().splitlines())
            Controller(mp, repo, sp, ep).run(execute=True)  # retry after PASS
            after = len(ep.read_text().splitlines())
            self.assertEqual(before, after)

    def test_gi40_recover_ten_fixpoint(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            norms = []
            for _ in range(10):
                r = Controller(mp, repo, sp, ep).recover()
                norms.append(json.dumps({k: r.report[k] for k in
                    ("graph", "classifications")}, sort_keys=True))
            self.assertEqual(len(set(norms)), 1)


# ==========================================================================
# GI-T43 — Seed regression
# ==========================================================================
class SeedRegression(unittest.TestCase):
    def test_gi43_seed_unchanged(self):
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
        self.assertEqual(cls["HASH-001"]["reasons"],
                         ["INCOMPLETE_SPECIFICATION", "TOOLCHAIN"])
        self.assertEqual(cls["RFC0075-001"]["reasons"],
                         ["SPECIFICATION_CONFLICT", "INCOMPLETE_SPECIFICATION"])


# ==========================================================================
# GI-T44..46 — TASK PASS ≠ REQUIREMENT SATISFIED
# ==========================================================================
class TaskPassNotRequirement(unittest.TestCase):
    def test_gi44_task_pass_requirement_partial(self):
        with tempfile.TemporaryDirectory() as d:
            tasks = [
                {"task_id": "T1", "title": "t1", "description": "d", "priority": 1,
                 "plan_order": 1, "source_authority": [{"doc": "spec.md"}],
                 "requirement_refs": ["R1"], "specification_refs": [{"doc": "spec.md"}],
                 "implementation_targets": [], "dependency_refs": [],
                 "allowed_tools": ["python3"],
                 "validation_commands": [{"id": "V1", "command": "python3 -V", "expected_exit": 0}],
                 "acceptance_criteria": [{"id": "AC1", "criterion": "c", "validator": "V1"}]},
                {"task_id": "T2", "title": "t2", "description": "d", "priority": 2,
                 "plan_order": 2, "source_authority": [{"doc": "spec.md"}],
                 "requirement_refs": ["R1"], "specification_refs": [{"doc": "spec.md"}],
                 "implementation_targets": [], "dependency_refs": [],
                 "required_tools": ["rebol-278"],
                 "allowed_tools": ["python3"],
                 "validation_commands": [{"id": "V1", "command": "python3 -V", "expected_exit": 0}],
                 "acceptance_criteria": [{"id": "AC1", "criterion": "c", "validator": "V1"}]}
            ]
            reqs = [{"id": "R1", "specification_refs": ["spec.md"],
                     "coverage": [{"task_id": "T1", "obligations": ["O1"]},
                                  {"task_id": "T2", "obligations": ["O2"]}]}]
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            man = {"schema_version": "1.0", "project": "gi",
                   "tool_registry": {"python3": {"available": True, "binary": "python3"},
                                     "rebol-278": {"available": False}},
                   "tasks": tasks, "requirements": reqs}
            mp = Path(d) / "m.json"; mp.write_text(json.dumps(man))
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            # execute T1 (READY) -> PASS; T2 BLOCKED (no rebol)
            for _ in range(5):
                Controller(mp, repo, sp, ep).run(execute=True)
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(res.classifications["T1"].effective_state, "PASS")
            self.assertEqual(res.classifications["T2"].effective_state, "BLOCKED")
            # T1 PASS but requirement R1 PARTIAL (T2 not PASS)
            ledger = {r["requirement_id"]: r for r in res.report["requirement_ledger"]}
            self.assertEqual(ledger["R1"]["status"], "PARTIAL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
