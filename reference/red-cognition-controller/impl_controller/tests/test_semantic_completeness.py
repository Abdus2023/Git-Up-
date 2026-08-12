"""Stage-5 specification-to-execution semantic-completeness tests.

Central invariant: a task may become READY only when its executable contract is
demonstrably sufficient to cover the authoritative acceptance criteria it claims
(opt-in criterion<->validator coverage; missing semantics is never inferred).
Run via:  python3 tools/impl-controller.py --self-test
"""
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

from impl_controller.manifest import load_manifest
from impl_controller.engine import classify_all, _coverage_gaps
from impl_controller.provenance import contract_identity_for, provenance_context
from impl_controller.controller import Controller


def _synth(d, criteria, commands, targets=None, git=False):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    if targets:
        for t, c in targets:
            (repo / t).write_text(c, encoding="utf-8")
    t = {"task_id": "SYNTH-001", "title": "syn", "description": "d", "priority": 1,
         "plan_order": 1, "scope": "s",
         "source_authority": [{"doc": "spec.md"}], "requirement_refs": ["REQ-1"],
         "specification_refs": [{"doc": "spec.md"}],
         "implementation_targets": [t for t, _ in (targets or [])],
         "dependency_refs": [], "required_tools": [], "allowed_tools": ["python3"],
         "validation_commands": commands,
         "acceptance_criteria": criteria}
    man = {"schema_version": "1.0", "project": "syn",
           "tool_registry": {"python3": {"available": True, "binary": "python3"}},
           "tasks": [t]}
    mp = Path(d) / "m.json"; mp.write_text(json.dumps(man), encoding="utf-8")
    if git:
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "i"], check=True, env=env)
    return mp, repo


def _cmd(cid="V1", c="python3 -V"):
    return {"id": cid, "command": c, "expected_exit": 0}


def _crit(cid="AC1", validator="V1"):
    return {"id": cid, "criterion": "c", "validator": validator}


def _state(res):
    return res.classifications["SYNTH-001"].effective_state


# ==========================================================================
# Presence checks (re-proven)
# ==========================================================================
class Presence(unittest.TestCase):
    def test_sc01_missing_requirement_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_crit()], [_cmd()])
            m = load_manifest(mp); m.tasks[0].requirement_refs = []
            cl = classify_all(m.tasks, m.tool_registry, repo)
            self.assertEqual(cl["SYNTH-001"].effective_state, "BLOCKED")

    def test_sc10_spec_only_pathexistence_still_requires_coverage(self):
        # spec ref present; with a declared validator the coverage is enforced
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_crit(validator="NOPE")], [_cmd()])
            m = load_manifest(mp)
            self.assertTrue(_coverage_gaps(m.tasks[0]))


# ==========================================================================
# Opt-in semantic coverage (strict mode)
# ==========================================================================
class StrictCoverage(unittest.TestCase):
    def test_sc_strict_covered_ready(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_crit("AC1", "V1"), _crit("AC2", "V2")],
                              [_cmd("V1"), _cmd("V2", "python3 -VV")])
            cl = classify_all(load_manifest(mp).tasks, load_manifest(mp).tool_registry, repo)
            self.assertEqual(cl["SYNTH-001"].effective_state, "READY")

    def test_sc03_criterion_without_validator_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_crit("AC1", "V1"), _crit("AC2", "")], [_cmd("V1")])
            m = load_manifest(mp)
            self.assertTrue(_coverage_gaps(m.tasks[0]))
            self.assertEqual(classify_all(m.tasks, m.tool_registry, repo)["SYNTH-001"].effective_state, "BLOCKED")

    def test_sc07_orphan_validator_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_crit("AC1", "V1")], [_cmd("V1"), _cmd("V2")])
            m = load_manifest(mp)
            self.assertTrue(any("no semantic purpose" in g for g in _coverage_gaps(m.tasks[0])))

    def test_sc03b_validator_not_a_command_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_crit("AC1", "GHOST")], [_cmd("V1")])
            m = load_manifest(mp)
            self.assertTrue(_coverage_gaps(m.tasks[0]))


# ==========================================================================
# Non-strict (legacy) tasks retain presence-based contract (grandfathered)
# ==========================================================================
class LegacyContract(unittest.TestCase):
    def test_sc_legacy_no_validators_not_strict(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d,
                [{"id": "AC1", "criterion": "c"}],   # no validator field
                [_cmd()])
            m = load_manifest(mp)
            self.assertEqual(_coverage_gaps(m.tasks[0]), [])  # legacy: no coverage asserted
            self.assertEqual(classify_all(m.tasks, m.tool_registry, repo)["SYNTH-001"].effective_state, "READY")


# ==========================================================================
# PASS requires every covered criterion's validator to pass
# ==========================================================================
class PassCoverage(unittest.TestCase):
    def test_sc14_partial_validator_fail_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "x"; sub.mkdir()
            mp, repo = _synth(str(sub),
                [_crit("AC1", "V1"), _crit("AC2", "V2")],
                [_cmd("V1", "python3 ok.py"),
                 {"id": "V2", "command": "python3 bad.py", "expected_exit": 0}])
            (repo / "ok.py").write_text("", encoding="utf-8")
            (repo / "bad.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
            res = Controller(mp, repo, sub / "s.json", sub / "e.jsonl").run(execute=True)
            self.assertNotEqual(_state(res), "PASS")


# ==========================================================================
# Semantic mutation invalidates prior evidence
# ==========================================================================
class SemanticMutation(unittest.TestCase):
    def _pass(self, d):
        mp, repo = _synth(d, [_crit("AC1", "V1")], [_cmd("V1")])
        sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
        Controller(mp, repo, sp, ep).run(execute=True)
        return mp, repo, sp, ep

    def test_sc_mutation_validator_remap_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = self._pass(d)
            self.assertEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")
            # remap the criterion to a different validator -> contract_id changes
            man = json.loads(mp.read_text())
            man["tasks"][0]["acceptance_criteria"][0]["validator"] = "V2"
            man["tasks"][0]["validation_commands"].append(_cmd("V2", "python3 -VV"))
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_sc_recovery_after_mutation_then_restore(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = self._pass(d)
            man0 = mp.read_text()
            # mutate (weaken coverage): drop the validator -> strict mode off, but
            # also drop the command so validation_commands coverage changes contract
            man = json.loads(man0); man["tasks"][0]["validation_commands"] = []
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).recover()), "PASS")
            # restore exact contract -> evidence reusable (contract_id matches)
            mp.write_text(man0)
            self.assertEqual(_state(Controller(mp, repo, sp, ep).recover()), "PASS")


# ==========================================================================
# Determinism of semantic identity
# ==========================================================================
class SemanticDeterminism(unittest.TestCase):
    def test_semantic_equivalent_same_contract(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            from impl_controller import model as M
            t1 = M.Task(task_id="T", title="t", description="d",
                        source_authority=[M.AuthorityRef("spec.md")], requirement_refs=["R"],
                        specification_refs=[M.AuthorityRef("spec.md")],
                        validation_commands=[M.ValidationCommand("V1", "python3 -V", 0)],
                        acceptance_criteria=[M.AcceptanceCriterion("AC1", "c", "V1")],
                        allowed_tools=["python3"])
            t2 = M.Task(task_id="T", title="t", description="d",
                        source_authority=[M.AuthorityRef("spec.md")], requirement_refs=["R"],
                        specification_refs=[M.AuthorityRef("spec.md")],
                        validation_commands=[M.ValidationCommand("V1", "python3 -V", 0)],
                        acceptance_criteria=[M.AcceptanceCriterion("AC1", "c", "V1")],
                        allowed_tools=["python3"])
            ctx = provenance_context(repo, load_manifest.__self__ if False else type("X", (), {"schema_version":"1.0","project":"p","tasks":[t1],"tool_registry":M.ToolRegistry()})())
            self.assertEqual(contract_identity_for(t1, set(), ctx),
                             contract_identity_for(t2, set(), ctx))

    def test_semantic_different_validator_different_contract(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            from impl_controller import model as M
            base = dict(task_id="T", title="t", description="d",
                        source_authority=[M.AuthorityRef("spec.md")], requirement_refs=["R"],
                        specification_refs=[M.AuthorityRef("spec.md")],
                        validation_commands=[M.ValidationCommand("V1", "python3 -V", 0),
                                             M.ValidationCommand("V2", "python3 -VV", 0)],
                        allowed_tools=["python3"])
            ta = M.Task(acceptance_criteria=[M.AcceptanceCriterion("AC1", "c", "V1")], **base)
            tb = M.Task(acceptance_criteria=[M.AcceptanceCriterion("AC1", "c", "V2")], **base)
            ctx = provenance_context(repo, type("X", (), {"schema_version":"1.0","project":"p","tasks":[ta],"tool_registry":M.ToolRegistry()})())
            self.assertNotEqual(contract_identity_for(ta, set(), ctx),
                                contract_identity_for(tb, set(), ctx))


# ==========================================================================
# Real repository (frontier unchanged)
# ==========================================================================
class RealRepository(unittest.TestCase):
    def test_frontier_closed(self):
        mp = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        if not mp.is_file():
            self.skipTest("seed manifest absent")
        sd = tempfile.mkdtemp()
        res = Controller(mp, REPO_ROOT, Path(sd) / "s.json", Path(sd) / "e.jsonl").run(dry_run=True)
        g = res.report["graph"]
        self.assertEqual((g["READY"], g["BLOCKED"], g["PASS"], g["IN_PROGRESS"]), (0, 4, 0, 0))
        self.assertEqual(res.report["frontier"], "PAUSED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
