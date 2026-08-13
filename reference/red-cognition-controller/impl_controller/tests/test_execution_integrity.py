"""Stage-5 execution-result integrity & validator-trust tests.

Central invariant: a successful exit status alone is NEVER sufficient for PASS;
PASS is bound to the validator's observed target state and any declared required
outputs. Run via:  python3 tools/impl-controller.py --self-test
"""
import hashlib
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
from impl_controller.evidence import EvidenceLog
from impl_controller.safety import target_hashes, validate_targets
from impl_controller.manifest import load_manifest, ManifestError
from impl_controller.provenance import provenance_context, contract_identity_for


def _sha(content):
    return hashlib.sha256(content.encode()).hexdigest()


def _synth(d, target=None, target_content=None, expected_outputs=None,
           cmds=None, tid="SYNTH-001", git=False):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    if target is not None:
        (repo / target).write_text(target_content or "x", encoding="utf-8")
    vcs = cmds if cmds is not None else [{"id": "V1", "command": "python3 -V", "expected_exit": 0}]
    t = {"task_id": tid, "title": "syn", "description": "d", "priority": 1,
         "plan_order": 1, "scope": "s",
         "source_authority": [{"doc": "spec.md"}], "requirement_refs": ["REQ-1"],
         "specification_refs": [{"doc": "spec.md"}],
         "implementation_targets": [target] if target else [],
         "dependency_refs": [], "required_tools": [], "allowed_tools": ["python3"],
         "validation_commands": vcs,
         "acceptance_criteria": [{"id": "A1", "criterion": "c"}]}
    if expected_outputs is not None:
        t["expected_outputs"] = expected_outputs
    man = {"schema_version": "1.0", "project": "syn",
           "tool_registry": {"python3": {"available": True, "binary": "python3"}},
           "tasks": [t]}
    mp = Path(d) / "m.json"; mp.write_text(json.dumps(man), encoding="utf-8")
    if git:
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "i"], check=True, env=env)
    return mp, repo


def _state(res, tid="SYNTH-001"):
    return res.classifications[tid].effective_state


# ==========================================================================
# Positive result verification (expected_outputs)
# ==========================================================================
class ExpectedOutputs(unittest.TestCase):
    def test_ei01_exit0_required_artifact_absent(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, expected_outputs=[{"path": "out.txt", "sha256": _sha("y")}])
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run(execute=True)
            self.assertNotEqual(_state(res), "PASS")  # out.txt absent

    def test_ei02_exit0_wrong_artifact_hash(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="WRONG",
                              expected_outputs=[{"path": "out.txt", "sha256": _sha("RIGHT")}])
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run(execute=True)
            self.assertNotEqual(_state(res), "PASS")

    def test_ei01b_exit0_correct_artifact_passes(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="RIGHT",
                              expected_outputs=[{"path": "out.txt", "sha256": _sha("RIGHT")}])
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run(execute=True)
            self.assertEqual(_state(res), "PASS")

    def test_ei02b_required_output_disappears_after_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="RIGHT",
                              expected_outputs=[{"path": "out.txt", "sha256": _sha("RIGHT")}])
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            (repo / "out.txt").unlink()
            res = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(_state(res), "PASS")


# ==========================================================================
# Target-state result integrity (observed target_hashes must still hold)
# ==========================================================================
class TargetStateIntegrity(unittest.TestCase):
    def test_ei03_declared_target_deleted_after_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="hello")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            self.assertEqual(_state(Controller(mp, repo, sp, ep).run(execute=True)), "PASS")
            (repo / "out.txt").unlink()
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ei13_target_hash_differs_after_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="hello")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            (repo / "out.txt").write_text("MUTATED", encoding="utf-8")
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ei05_target_replaced_with_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="hello")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            (repo / "out.txt").unlink()
            (repo / "decoy.txt").write_text("decoy", encoding="utf-8")
            try:
                os.symlink("decoy.txt", repo / "out.txt")
            except OSError:
                self.skipTest("symlinks unsupported")
            # symlink content differs from the original -> target_hashes mismatch
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ei12_contradictory_delta_invalidates(self):
        # target present at validation, removed afterward -> not PASS (EI-03 variant)
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="x")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            (repo / "out.txt").write_text("totally-different", encoding="utf-8")
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# Scope / path integrity (re-proven through integrity lens)
# ==========================================================================
class ScopeIntegrity(unittest.TestCase):
    def test_ei04_undeclared_write_fails(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="allowed.txt", target_content="", git=True,
                cmds=[{"id": "V1", "command": "python3 evil.py", "expected_exit": 0}])
            (repo / "evil.py").write_text("open('evil.txt','w').write('x')\n", encoding="utf-8")
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run(execute=True)
            self.assertNotEqual(_state(res), "PASS")

    def test_ei20_target_scope_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
            self.assertTrue(validate_targets(["../escape.txt"], repo))


# ==========================================================================
# Validator binding (re-proven)
# ==========================================================================
class ValidatorBinding(unittest.TestCase):
    def test_ei19_validator_command_modified_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="x")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"][0]["command"] = "python3 -VV"
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ei09_contract_change_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="x")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "x"
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# Observation tampering (target_hashes are part of the hash chain)
# ==========================================================================
class ObservationTampering(unittest.TestCase):
    def test_ei31_target_hashes_tampered_breaks_chain(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="x")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            # tamper the recorded target_hashes without fixing record_hash
            lines = ep.read_text().splitlines()
            rec = json.loads(lines[0]); rec["target_hashes"] = {"out.txt": "forged"}
            ep.write_text(json.dumps(rec) + "\n")
            self.assertFalse(EvidenceLog(ep).verify_integrity()["intact"])
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# Multi-command / partial execution (re-proven)
# ==========================================================================
class PartialExecution(unittest.TestCase):
    def test_ei17_first_pass_second_fail_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "x"; sub.mkdir()
            mp, repo = _synth(str(sub),
                cmds=[{"id": "C1", "command": "python3 ok.py", "expected_exit": 0},
                      {"id": "C2", "command": "python3 bad.py", "expected_exit": 0}])
            (repo / "ok.py").write_text("", encoding="utf-8")
            (repo / "bad.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
            res = Controller(mp, repo, sub / "s.json", sub / "e.jsonl").run(execute=True)
            self.assertNotEqual(_state(res), "PASS")


# ==========================================================================
# Stale checkpoint / traceability (re-proven)
# ==========================================================================
class StaleAndClosure(unittest.TestCase):
    def test_ei25_stale_checkpoint_pass_demoted(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="x")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True); ep.unlink()
            raw = json.loads(sp.read_text()); raw["tasks"][0]["validated_pass"] = True
            sp.write_text(json.dumps(raw))
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ei34_incomplete_traceability_open(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)  # no target, no execute
            res = Controller(mp, repo, Path(d) / "s.json", Path(d) / "e.jsonl").run(dry_run=True)
            tr = [t for t in res.report["traceability"] if t["task_id"] == "SYNTH-001"][0]
            self.assertEqual(tr["closure"], "OPEN")


# ==========================================================================
# Determinism & convergence
# ==========================================================================
class DeterminismAndConvergence(unittest.TestCase):
    def test_ei35_repeated_validation_determinism(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="x")
            norms = []
            for i in range(3):
                r = Controller(mp, repo, Path(d) / f"s{i}.json", Path(d) / f"e{i}.jsonl").run(dry_run=True)
                norms.append(json.dumps({k: r.report[k] for k in
                    ("graph", "classifications", "provenance_context")}, sort_keys=True))
            self.assertEqual(len(set(norms)), 1)

    def test_ei36_execute_validate_recover_validate_converges(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="x")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            states = []
            states.append(_state(Controller(mp, repo, sp, ep).run(execute=True)))
            states.append(_state(Controller(mp, repo, sp, ep).recover()))
            states.append(_state(Controller(mp, repo, sp, ep).run()))
            self.assertEqual(len(set(states)), 1)
            self.assertEqual(states[0], "PASS")


# ==========================================================================
# Crash between execution and observation/validation (re-proven via recovery)
# ==========================================================================
class CrashBoundaries(unittest.TestCase):
    def test_ei37_38_39_crash_never_manufactures_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="x")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            # crash-equivalent: no evidence + corrupt checkpoint -> no PASS
            sp.write_text("{broken")
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).recover()), "PASS")

    def test_ei40_recovery_cannot_manufacture_observation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d, target="out.txt", target_content="x")
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)  # PASS
            (repo / "out.txt").unlink()  # destroy the result
            sp.write_text("{broken")     # force recovery
            # recovery cannot re-establish PASS: the observed target state is gone
            self.assertNotEqual(_state(Controller(mp, repo, sp, ep).recover()), "PASS")


# ==========================================================================
# Real repository
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
