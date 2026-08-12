"""Provenance & traceability-closure adversarial tests (Stage-5).

Validates the complete provenance chain: requirement -> specification -> task ->
contract -> execution -> validation -> evidence -> repository state ->
traceability. Central invariant: a successful command alone is NEVER
sufficient for PASS. Run via:  python3 tools/impl-controller.py --self-test
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
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from impl_controller import provenance as P
from impl_controller.provenance import (
    manifest_identity, contract_identity_for, closure_gaps, repo_identity,
    repo_head, provenance_context, default_context, command_identity,
    VALIDATOR_IDENTITY,
)
from impl_controller.manifest import load_manifest
from impl_controller.evidence import EvidenceLog, EvidenceRecord
from impl_controller.controller import Controller
from impl_controller.model import TaskState


def _synth(d, with_git=False, task_over=None):
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
        "validation_commands": [{"id": "V1", "command": "python3 -V",
                                 "expected_exit": 0}],
        "acceptance_criteria": [{"id": "A1", "criterion": "c"}],
    }
    if task_over:
        t.update(task_over)
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


def _write_manifest(d, man):
    mp = Path(d) / "m.json"; mp.write_text(json.dumps(man), encoding="utf-8")
    return mp


# ==========================================================================
# A — Requirement identity
# ==========================================================================
class A_Requirement(unittest.TestCase):
    def test_missing_requirement_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, task_over={"requirement_refs": []})
            m = load_manifest(mp)
            from impl_controller.engine import classify_all
            cl = classify_all(m.tasks, m.tool_registry, repo)
            self.assertEqual(cl["SYNTH-001"].effective_state, "BLOCKED")

    def test_requirement_absent_authority_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp)
            ctx = provenance_context(repo, m)
            t = m.tasks[0]
            # requirement present but its authority doc missing on disk
            (repo / "spec.md").unlink()
            self.assertTrue(closure_gaps(t, contract_identity_for(t, set(), ctx),
                                         [{"contract_id": "x", "task_id": "SYNTH-001",
                                           "result": "PASS"}], ctx))


# ==========================================================================
# B — Specification identity
# ==========================================================================
class B_Specification(unittest.TestCase):
    def test_spec_removed_after_planning_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            cid = contract_identity_for(t, set(), ctx)
            (repo / "spec.md").unlink()
            gaps = closure_gaps(t, cid, [], ctx)
            self.assertTrue(gaps)

    def test_spec_outside_repo_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, task_over={"specification_refs": [{"doc": "../etc/passwd"}]})
            m = load_manifest(mp)
            from impl_controller.engine import classify_all
            cl = classify_all(m.tasks, m.tool_registry, repo)
            self.assertEqual(cl["SYNTH-001"].effective_state, "BLOCKED")

    def test_spec_is_directory_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            (repo / "spec.md").unlink(); (repo / "spec.md").mkdir()
            m = load_manifest(mp)
            from impl_controller.engine import classify_all
            cl = classify_all(m.tasks, m.tool_registry, repo)
            self.assertEqual(cl["SYNTH-001"].effective_state, "BLOCKED")


# ==========================================================================
# C — Task identity / contract integrity
# ==========================================================================
class C_TaskContract(unittest.TestCase):
    def test_contract_id_task_specific(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m)
            t1 = m.tasks[0]
            from impl_controller.model import Task
            t2 = Task(task_id="OTHER", title="o", description="d",
                      source_authority=t1.source_authority, requirement_refs=["R"],
                      specification_refs=t1.specification_refs,
                      validation_commands=t1.validation_commands,
                      acceptance_criteria=t1.acceptance_criteria,
                      allowed_tools=["python3"])
            self.assertNotEqual(contract_identity_for(t1, set(), ctx),
                                contract_identity_for(t2, set(), ctx))

    def test_contract_reused_for_another_task_not_pass(self):
        # evidence bound to task A's contract cannot satisfy task B
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            c1 = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl")
            c1.run(execute=True)  # SYNTH-001 PASS
            ev = c1.log.verified_records()[0]
            # replay that evidence under a DIFFERENT task id by tampering task_id
            ev2 = dict(ev); ev2["task_id"] = "IMPOSTOR"
            self.assertNotEqual(ev2["task_id"], "SYNTH-001")
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            gaps = closure_gaps(t, contract_identity_for(t, set(), ctx), [ev2], ctx)
            self.assertTrue(gaps)  # task_id/contract binding mismatch


# ==========================================================================
# D — Evidence identity
# ==========================================================================
class D_Evidence(unittest.TestCase):
    def test_evidence_contract_mismatch_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            real_cid = contract_identity_for(t, set(), ctx)
            bogus = {"contract_id": "0" * 64, "task_id": "SYNTH-001",
                     "result": "PASS", "validator": VALIDATOR_IDENTITY}
            self.assertTrue(closure_gaps(t, real_cid, [bogus], ctx))

    def test_evidence_nonexistent_task_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            m = load_manifest(mp); ctx = provenance_context(repo, m)
            # evidence for a task not in the manifest
            rec = EvidenceRecord("E", "GHOST", "python3 -V", exit_status=0,
                                 result="PASS", expected_exit=0,
                                 contract_id="x", repository_identity=ctx["repo_identity"],
                                 head=ctx["head"], manifest_hash=ctx["manifest_hash"],
                                 validator=VALIDATOR_IDENTITY)
            log.append(rec)
            self.assertEqual(log.validated_pass(), {"GHOST"})  # structurally valid
            # but no manifest task GHOST -> controller ignores it
            c = Controller(mp, repo, Path(d) / "s.json", ep)
            res = c.run(dry_run=False)
            self.assertEqual(res.classifications["SYNTH-001"].effective_state, "READY")


# ==========================================================================
# E — Contract integrity (manifest/command mutation)
# ==========================================================================
class E_ContractIntegrity(unittest.TestCase):
    def test_manifest_change_invalidates_contract(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            cid0 = contract_identity_for(t, set(), ctx)
            # mutate the manifest (change a task field)
            man = json.loads(mp.read_text())
            man["tasks"][0]["description"] = "changed"
            mp.write_text(json.dumps(man))
            m2 = load_manifest(mp); ctx2 = provenance_context(repo, m2); t2 = m2.tasks[0]
            cid1 = contract_identity_for(t2, set(), ctx2)
            self.assertNotEqual(cid0, cid1)

    def test_command_change_invalidates_contract(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            cid0 = contract_identity_for(t, set(), ctx)
            t.validation_commands[0].command = "python3 -VV"
            cid1 = contract_identity_for(t, set(), ctx)
            self.assertNotEqual(cid0, cid1)


# ==========================================================================
# F — Repository provenance (head/repo binding)
# ==========================================================================
class F_RepositoryProvenance(unittest.TestCase):
    def test_head_change_invalidates_contract(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, with_git=True)
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            cid0 = contract_identity_for(t, set(), ctx)
            # advance HEAD
            (repo / "new.txt").write_text("x")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t"})
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c"],
                           check=True, env=env)
            ctx2 = provenance_context(repo, m)
            cid1 = contract_identity_for(t, set(), ctx2)
            self.assertNotEqual(cid0, cid1)

    def test_repo_identity_per_repo(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ra = Path(a) / "ra"; ra.mkdir(); rb = Path(b) / "rb"; rb.mkdir()
            self.assertNotEqual(repo_identity(ra), repo_identity(rb))
            self.assertEqual(repo_identity(ra), repo_identity(ra))  # stable


# ==========================================================================
# G — Validation binding
# ==========================================================================
class G_ValidationBinding(unittest.TestCase):
    def test_pass_mismatched_exit_untrusted(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            log.append(EvidenceRecord("E", "T", "false", exit_status=2,
                                      result="PASS", expected_exit=0))
            self.assertEqual(log.validated_pass(), set())

    def test_validator_identity_mismatch_gap(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            cid = contract_identity_for(t, set(), ctx)
            ev = {"contract_id": cid, "task_id": "SYNTH-001", "result": "PASS",
                  "validator": "impostor"}
            gaps = closure_gaps(t, cid, [ev], ctx)
            self.assertIn("evidence validator identity mismatch", gaps)


# ==========================================================================
# H — Traceability closure
# ==========================================================================
class H_Closure(unittest.TestCase):
    def test_complete_chain_closes(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            cid = contract_identity_for(t, set(), ctx)
            ev = [{"contract_id": cid, "task_id": "SYNTH-001", "result": "PASS",
                   "validator": VALIDATOR_IDENTITY,
                   "command_id": command_identity(t.validation_commands[0])}]
            self.assertEqual(closure_gaps(t, cid, ev, ctx), [])

    def test_missing_specification_edge_open(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, task_over={"specification_refs": []})
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            cid = contract_identity_for(t, set(), ctx)
            self.assertTrue(closure_gaps(t, cid, [], ctx))

    def test_no_evidence_edge_open(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m); t = m.tasks[0]
            cid = contract_identity_for(t, set(), ctx)
            self.assertTrue(closure_gaps(t, cid, [], ctx))


# ==========================================================================
# Phase 10 — Replay resistance (end-to-end via controller)
# ==========================================================================
class ReplayResistance(unittest.TestCase):
    def _execute_to_pass(self, d, with_git=False):
        mp, repo = _synth(d, with_git=with_git)
        c = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl")
        res = c.run(execute=True)
        return mp, repo, res

    def test_replay_evidence_into_mutated_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, res = self._execute_to_pass(d)
            self.assertEqual(res.classifications["SYNTH-001"].effective_state, "PASS")
            # mutate manifest -> contract_id changes -> prior evidence no longer binds
            man = json.loads(mp.read_text()); man["tasks"][0]["description"] = "x"
            mp.write_text(json.dumps(man))
            c2 = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl")
            res = c2.run(dry_run=False)
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")

    def test_replay_evidence_into_advanced_head(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, res = self._execute_to_pass(d, with_git=True)
            self.assertEqual(res.classifications["SYNTH-001"].effective_state, "PASS")
            (repo / "n.txt").write_text("x")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t"})
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c"],
                           check=True, env=env)
            c2 = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl")
            res = c2.run(dry_run=False)
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")


# ==========================================================================
# Phase 12 — Synthetic end-to-end + per-component mutation
# ==========================================================================
class SyntheticMutation(unittest.TestCase):
    def test_full_lifecycle_then_each_mutation_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, res = self._lifecycle(d)
            self.assertEqual(res.classifications["SYNTH-001"].effective_state, "PASS")

            # mutate manifest
            self._check_invalid(d, mp, repo, mut_manifest=True, mut_spec=False,
                                mut_command=False)
            # mutate specification (authority)
            self._check_invalid(d, mp, repo, mut_manifest=False, mut_spec=True,
                                mut_command=False)
            # mutate command
            self._check_invalid(d, mp, repo, mut_manifest=False, mut_spec=False,
                                mut_command=True)

    def _lifecycle(self, d):
        mp, repo = _synth(d, with_git=True)
        c = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl")
        res = c.run(execute=True)
        if not (repo / "spec.md").exists():
            (repo / "spec.md").write_text("# spec\n")
        return mp, repo, res

    def _check_invalid(self, d, mp, repo, mut_manifest, mut_spec, mut_command):
        for f in (Path(d) / "s.json", Path(d) / "e.jsonl"):
            if f.exists():
                f.unlink()
        if not (repo / "spec.md").exists():
            (repo / "spec.md").write_text("# spec\n")
        c0 = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl")
        base = c0.run(execute=True)
        baseline = base.classifications["SYNTH-001"].effective_state
        if mut_manifest:
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "changed"
            mp.write_text(json.dumps(man))
        if mut_spec:
            (repo / "spec.md").unlink()
        if mut_command:
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"][0]["command"] = "python3 -VV"
            mp.write_text(json.dumps(man))
        c1 = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl")
        res = c1.run(dry_run=False)
        self.assertEqual(baseline, "PASS")
        self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS",
                            f"mutation did not invalidate PASS "
                            f"(manifest={mut_manifest},spec={mut_spec},cmd={mut_command})")
        if mut_spec and not (repo / "spec.md").exists():
            (repo / "spec.md").write_text("# spec\n")
        if mut_manifest or mut_command:
            man = json.loads(mp.read_text())
            man["tasks"][0]["title"] = "syn"
            man["tasks"][0]["validation_commands"][0]["command"] = "python3 -V"
            mp.write_text(json.dumps(man))


# ==========================================================================
# Phase 11 — Determinism (3-run comparison)
# ==========================================================================
class Determinism(unittest.TestCase):
    def test_three_runs_identical(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            m = load_manifest(mp); ctx = provenance_context(repo, m)
            mh = manifest_identity(m)
            t = m.tasks[0]; cid = contract_identity_for(t, set(), ctx)
            norms = []
            for i in range(3):
                sd = Path(d) / f"r{i}"; sd.mkdir()
                c = Controller(mp, repo, sd / "s.json", sd / "e.jsonl")
                res = c.run(dry_run=True)
                n = json.dumps({k: res.report[k] for k in
                                ("graph", "classifications", "frontier",
                                 "provenance_context")}, sort_keys=True)
                norms.append(n)
            self.assertEqual(len(set(norms)), 1)
            self.assertEqual(manifest_identity(load_manifest(mp)), mh)
            self.assertEqual(
                contract_identity_for(load_manifest(mp).tasks[0], set(),
                                       provenance_context(repo, load_manifest(mp))),
                cid)


# ==========================================================================
# Phase 13 — Real repository (non-product)
# ==========================================================================
class RealRepository(unittest.TestCase):
    def test_real_frontier_unchanged(self):
        mp = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        if not mp.is_file():
            self.skipTest("seed manifest absent")
        import tempfile as _t
        sd = _t.mkdtemp()
        c = Controller(mp, REPO_ROOT, Path(sd) / "s.json", Path(sd) / "e.jsonl")
        res = c.run(dry_run=True)
        self.assertEqual(res.frontier, "PAUSED")
        self.assertEqual(res.report["graph"]["READY"], 0)
        self.assertEqual(res.report["graph"]["BLOCKED"], 4)
        for tid in ("RED-LEX-001", "LIBRED-001", "HASH-001", "RFC0075-001"):
            self.assertEqual(res.classifications[tid].effective_state, "BLOCKED")
        # provenance context present; traceability carries contract_ids + closure
        self.assertIn("manifest_hash", res.report["provenance_context"])
        for tr in res.report["traceability"]:
            self.assertIn("contract_id", tr)
            self.assertEqual(tr["closure"], "OPEN")  # blocked tasks: no evidence edge


if __name__ == "__main__":
    unittest.main(verbosity=2)
