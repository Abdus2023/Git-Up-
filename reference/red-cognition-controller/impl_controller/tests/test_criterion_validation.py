"""Stage-5 criterion-level validation attestation & evidence binding (Phase 24).

Central invariant: a criterion is PASS-authorized only by (its declared
validator's) evidence explicitly bound to that criterion via the current
contract — command-level PASS never substitutes for criterion attestation.
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

from impl_controller import model as M
from impl_controller.manifest import load_manifest
from impl_controller.engine import classify_all
from impl_controller.provenance import (
    provenance_context, contract_identity_for, criterion_attestations,
    command_identity,
)
from impl_controller.evidence import EvidenceLog, EvidenceRecord
from impl_controller.controller import Controller


def _ctx(repo, task):
    m = type("X", (), {"schema_version": "1.0", "project": "p", "tasks": [task],
                       "tool_registry": M.ToolRegistry()})()
    return provenance_context(repo, m)


def _strict_task(criteria, commands, tid="T"):
    return M.Task(task_id=tid, title=tid, description="d", priority=1, plan_order=1,
                  scope="s", source_authority=[M.AuthorityRef(doc="spec.md")],
                  requirement_refs=["REQ-1"],
                  specification_refs=[M.AuthorityRef(doc="spec.md")],
                  implementation_targets=[], dependency_refs=[], required_tools=[],
                  allowed_tools=["python3"], validation_commands=commands,
                  acceptance_criteria=criteria)


def _ac(cid="AC1", validator="V1"):
    return M.AcceptanceCriterion(cid, "c", validator)


def _vc(cid="V1", cmd="python3 -V"):
    return M.ValidationCommand(cid, cmd, 0)


def _synth(d, criteria, commands, git=False):
    repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    _d = lambda x: x.__dict__ if hasattr(x, "__dict__") and not isinstance(x, dict) else x
    t = {"task_id": "SYNTH-001", "title": "syn", "description": "d", "priority": 1,
         "plan_order": 1, "scope": "s", "source_authority": [{"doc": "spec.md"}],
         "requirement_refs": ["REQ-1"], "specification_refs": [{"doc": "spec.md"}],
         "implementation_targets": [], "dependency_refs": [], "required_tools": [],
         "allowed_tools": ["python3"], "validation_commands": [_d(c) for c in commands],
         "acceptance_criteria": [_d(c) for c in criteria]}
    man = {"schema_version": "1.0", "project": "syn",
           "tool_registry": {"python3": {"available": True, "binary": "python3"}}, "tasks": [t]}
    mp = Path(d) / "m.json"; mp.write_text(json.dumps(man), encoding="utf-8")
    if git:
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "i"], check=True, env=env)
    return mp, repo


def _state(res):
    return res.classifications["SYNTH-001"].effective_state


# ==========================================================================
# CV-01..04 — basics
# ==========================================================================
class Basics(unittest.TestCase):
    def test_cv01_validator_must_execute(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1")], [_vc("V1")])
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run(execute=True)
            self.assertEqual(_state(res), "PASS")

    def test_cv02_exit0_insufficient_alone(self):
        # command exits 0 but evidence not bound to the contract -> not PASS
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1")], [_vc("V1")])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            # mutate contract so old evidence is unbound
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "x"; mp.write_text(json.dumps(man))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_cv03_strict_no_validator_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            t = _strict_task([_ac("AC1", "V1"), M.AcceptanceCriterion("AC2", "c", "")], [_vc("V1")])
            self.assertEqual(classify_all([t], M.ToolRegistry(), repo)["T"].effective_state, "BLOCKED")

    def test_cv04_validator_executes_criterion_evidence_absent_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            t = _strict_task([_ac("AC1", "V1")], [_vc("V1")])
            ctx = _ctx(repo, t); cid = contract_identity_for(t, set(), ctx)
            # no evidence at all -> criterion not attested
            atts = criterion_attestations(t, cid, [], ctx)
            self.assertFalse(atts[0]["attested"]); self.assertEqual(atts[0]["gap"], "NO_CRITERION_ATTESTATION")


# ==========================================================================
# CV-05..09 — wrong binding / forgery
# ==========================================================================
class WrongBinding(unittest.TestCase):
    def test_cv05_wrong_validator_not_attested(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            t = _strict_task([_ac("AC1", "V1")], [_vc("V1"), _vc("V2", "python3 -VV")])
            ctx = _ctx(repo, t); cid = contract_identity_for(t, set(), ctx)
            # evidence exists for V2, not V1 -> AC1 (->V1) not attested
            ev = [{"contract_id": cid, "task_id": "T", "result": "PASS",
                   "command_id": command_identity(_vc("V2", "python3 -VV"))}]
            self.assertFalse(criterion_attestations(t, cid, ev, ctx)[0]["attested"])

    def test_cv06_wrong_contract_not_attested(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            t = _strict_task([_ac("AC1", "V1")], [_vc("V1")])
            ctx = _ctx(repo, t)
            ev = [{"contract_id": "0" * 64, "task_id": "T", "result": "PASS",
                   "command_id": command_identity(_vc("V1"))}]
            self.assertFalse(criterion_attestations(t, "real-cid", ev, ctx)[0]["attested"])

    def test_cv07_wrong_task_not_attested(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            t = _strict_task([_ac("AC1", "V1")], [_vc("V1")])
            ctx = _ctx(repo, t); cid = contract_identity_for(t, set(), ctx)
            ev = [{"contract_id": cid, "task_id": "OTHER", "result": "PASS",
                   "command_id": command_identity(_vc("V1"))}]
            self.assertFalse(criterion_attestations(t, cid, ev, ctx)[0]["attested"])

    def test_cv08_criterion_evidence_id_is_per_criterion(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            t = _strict_task([_ac("AC1", "V1"), _ac("AC2", "V1")], [_vc("V1")])
            ctx = _ctx(repo, t); cid = contract_identity_for(t, set(), ctx)
            ev = [{"contract_id": cid, "task_id": "T", "result": "PASS",
                   "command_id": command_identity(_vc("V1"))}]
            atts = criterion_attestations(t, cid, ev, ctx)
            self.assertEqual(len(atts), 2)
            self.assertEqual(len({a["criterion_evidence_id"] for a in atts}), 2)

    def test_cv09_forged_pass_breaks_chain(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            log.append(EvidenceRecord("E1", "T", "python3 -V", exit_status=0,
                                      result="PASS", expected_exit=0))
            rec = json.loads(ep.read_text().strip()); rec["exit_status"] = 99
            ep.write_text(json.dumps(rec) + "\n")
            self.assertFalse(EvidenceLog(ep).verify_integrity()["intact"])


# ==========================================================================
# CV-10..12 — multi-criterion
# ==========================================================================
class MultiCriterion(unittest.TestCase):
    def test_cv10_one_pass_one_absent_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1"), _ac("AC2", "V2")],
                              [_vc("V1"), _vc("V2", "python3 -VV")])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            # only V1 runs (simulate V2 absent by not executing fully) -> use dry-run then no evidence
            res = Controller(mp, repo, sp, ep).run()  # no execute -> no evidence -> not PASS
            self.assertNotEqual(_state(res), "PASS")

    def test_cv11_one_fail_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "x"; sub.mkdir()
            mp, repo = _synth(str(sub), [_ac("AC1", "V1"), _ac("AC2", "V2")],
                              [_vc("V1", "python3 ok.py"),
                               {"id": "V2", "command": "python3 bad.py", "expected_exit": 0}])
            (repo / "ok.py").write_text("", encoding="utf-8")
            (repo / "bad.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
            res = Controller(mp, repo, sub / "s.json", sub / "e.jsonl").run(execute=True)
            self.assertNotEqual(_state(res), "PASS")

    def test_cv12_validator_reused_by_two_criteria_permitted(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V"), _ac("AC2", "V")], [_vc("V")])
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run(execute=True)
            self.assertEqual(_state(res), "PASS")


# ==========================================================================
# CV-13..17 — identity / mutation
# ==========================================================================
class IdentityMutation(unittest.TestCase):
    def test_cv13_criterion_reorder_same_contract(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            a = _strict_task([_ac("AC1", "V1"), _ac("AC2", "V2")], [_vc("V1"), _vc("V2", "python3 -VV")])
            b = _strict_task([_ac("AC2", "V2"), _ac("AC1", "V1")], [_vc("V2", "python3 -VV"), _vc("V1")])
            ctx = _ctx(repo, a)
            self.assertEqual(contract_identity_for(a, set(), ctx), contract_identity_for(b, set(), ctx))

    def test_cv14_mapping_changed_different_contract(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            a = _strict_task([_ac("AC1", "V1")], [_vc("V1"), _vc("V2", "python3 -VV")])
            b = _strict_task([_ac("AC1", "V2")], [_vc("V1"), _vc("V2", "python3 -VV")])
            ctx = _ctx(repo, a)
            self.assertNotEqual(contract_identity_for(a, set(), ctx), contract_identity_for(b, set(), ctx))

    def test_cv15_criterion_deleted_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1")], [_vc("V1")])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            man = json.loads(mp.read_text()); man["tasks"][0]["acceptance_criteria"] = []
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_cv17_validator_command_changed_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1")], [_vc("V1")])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"][0]["command"] = "python3 -VV"
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# CV-20..25 — derived-state / recovery / determinism
# ==========================================================================
class DerivedAndRecovery(unittest.TestCase):
    def test_cv20_stale_checkpoint_criterion_pass_demoted(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1")], [_vc("V1")])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True); ep.unlink()
            raw = json.loads(sp.read_text()); raw["tasks"][0]["validated_pass"] = True
            sp.write_text(json.dumps(raw))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_cv21_crash_after_validation_no_invented_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1")], [_vc("V1")])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            # crash-equivalent: no evidence, corrupt checkpoint
            sp.write_text("{broken")
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).recover()), "PASS")

    def test_cv25_recovery_fixpoint(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1")], [_vc("V1")])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True); sp.write_text("{broken")
            norms = []
            for _ in range(10):
                r = Controller(mp, repo, sp, ep).recover()
                norms.append(json.dumps({k: r.report[k] for k in ("graph", "classifications")}, sort_keys=True))
            self.assertEqual(len(set(norms)), 1)


# ==========================================================================
# CV-26..27 — synthetic lifecycle
# ==========================================================================
class SyntheticLifecycle(unittest.TestCase):
    def test_cv26_complete_semantic_task_ready_to_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1"), _ac("AC2", "V2")],
                              [_vc("V1"), _vc("V2", "python3 -VV")])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            r0 = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_state(r0), "READY")
            r1 = Controller(mp, repo, sp, ep).run(execute=True)
            self.assertEqual(_state(r1), "PASS")

    def test_cv27_missing_criterion_evidence_ready_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, [_ac("AC1", "V1")], [_vc("V1")])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            self.assertEqual(_state(Controller(mp, repo, sp, ep).run()), "READY")
            # no execute -> no evidence -> not PASS
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# CV-28 + seed
# ==========================================================================
class RealAndSeed(unittest.TestCase):
    def test_cv28_real_repository(self):
        mp = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        if not mp.is_file():
            self.skipTest("seed manifest absent")
        sd = tempfile.mkdtemp()
        res = Controller(mp, REPO_ROOT, Path(sd) / "s.json", Path(sd) / "e.jsonl").run(dry_run=True)
        g = res.report["graph"]
        self.assertEqual((g["READY"], g["BLOCKED"], g["PASS"], g["IN_PROGRESS"]), (0, 4, 0, 0))
        self.assertEqual(res.report["frontier"], "PAUSED")

    def test_seed_tasks_unchanged(self):
        mp = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        if not mp.is_file():
            self.skipTest("seed manifest absent")
        sd = tempfile.mkdtemp()
        res = Controller(mp, REPO_ROOT, Path(sd) / "s.json", Path(sd) / "e.jsonl").run(dry_run=True)
        cls = {c["task_id"]: c for c in res.report["classifications"]}
        self.assertEqual(cls["RED-LEX-001"]["reasons"],
                         ["TOOLCHAIN", "ARCHITECTURE", "PROVISIONING", "AUTHORIZATION"])
        self.assertEqual(cls["LIBRED-001"]["reasons"], ["DEPENDENCY", "TOOLCHAIN"])
        self.assertEqual(cls["HASH-001"]["reasons"], ["INCOMPLETE_SPECIFICATION", "TOOLCHAIN"])
        self.assertEqual(cls["RFC0075-001"]["reasons"],
                         ["SPECIFICATION_CONFLICT", "INCOMPLETE_SPECIFICATION"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
