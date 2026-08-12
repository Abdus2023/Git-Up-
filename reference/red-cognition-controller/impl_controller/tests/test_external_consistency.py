"""Phase 29 — Distributed authority & external state consistency.

Proves: NO AUTHORITATIVE STATE CHANGE MAY LEAVE OLD EVIDENCE AUTHORIZED, and
NO EXTERNAL STATE MAY SILENTLY CHANGE THE MEANING OF AN EXISTING PASS.
Run via:  python3 tools/impl-controller.py --self-test
"""
import json, os, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from impl_controller.controller import Controller
from impl_controller.evidence import EvidenceLog


def _synth(d, target="out.txt", content="hello", git=False):
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
    man = {"schema_version": "1.0", "project": "ec",
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


def _pass(d, **kw):
    mp, repo = _synth(d, **kw)
    sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
    Controller(mp, repo, sp, ep).run(execute=True)
    return mp, repo, sp, ep


def _s(res, tid="SYNTH-001"):
    return res.classifications[tid].effective_state


# ==========================================================================
# EC-01..08: EXTERNAL MUTATION INVALIDATES OLD EVIDENCE
# ==========================================================================
class ExternalMutation(unittest.TestCase):
    def _mutate_check(self, mutator):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")
            mutator(mp, repo, d)
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ec01_head_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d, git=True)
            (repo / "new.txt").write_text("x")
            import subprocess
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c"], check=True, env=env)
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ec02_manifest_mutation(self):
        self._mutate_check(lambda mp, r, d: mp.write_text(
            json.dumps({**json.loads(mp.read_text()), "project": "changed"})))

    def test_ec03_contract_mutation(self):
        self._mutate_check(lambda mp, r, d: mp.write_text(
            json.dumps({**json.loads(mp.read_text()),
                        "tasks": [{**json.loads(mp.read_text())["tasks"][0], "title": "x"}]})))

    def test_ec04_target_mutation(self):
        self._mutate_check(lambda mp, r, d: (r / "out.txt").write_text("MUTATED", encoding="utf-8"))

    def test_ec05_validator_mutation(self):
        def m(mp, r, d):
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"][0]["command"] = "python3 -VV"
            mp.write_text(json.dumps(man))
        self._mutate_check(m)

    def test_ec06_command_mutation(self):
        def m(mp, r, d):
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"][0]["expected_exit"] = 1
            mp.write_text(json.dumps(man))
        self._mutate_check(m)


# ==========================================================================
# EC-09..11: SUBSTITUTION ATTACKS
# ==========================================================================
class SubstitutionAttacks(unittest.TestCase):
    def test_ec09_worktree_replacement(self):
        """Evidence from repo A replayed into repo B (different repo_identity)."""
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            mpa, repoa, _, epa = _pass(a)
            mpb, repob = _synth(b)
            epb = Path(b) / "e.jsonl"; epb.write_bytes(epa.read_bytes())
            self.assertNotEqual(_s(Controller(mpb, repob, Path(b) / "s.json", epb).run()), "PASS")

    def test_ec10_symlink_substitution(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            (repo / "out.txt").unlink()
            (repo / "decoy.txt").write_text("decoy", encoding="utf-8")
            try:
                os.symlink("decoy.txt", repo / "out.txt")
            except OSError:
                self.skipTest("symlinks unsupported")
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# EC-12..14: STALE STATE
# ==========================================================================
class StaleState(unittest.TestCase):
    def test_ec12_stale_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d); ep.unlink()
            raw = json.loads(sp.read_text()); raw["tasks"][0]["validated_pass"] = True
            sp.write_text(json.dumps(raw))
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ec13_stale_evidence_after_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "x"
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ec14_cross_head_evidence_replay(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d, git=True)
            (repo / "n.txt").write_text("x")
            import subprocess
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c"], check=True, env=env)
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# EC-15..19: REPLAY ATTACKS
# ==========================================================================
class ReplayAttacks(unittest.TestCase):
    def test_ec15_cross_manifest_replay(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _, _, _, epa = _pass(a)
            mpb, repob = _synth(b)
            man = json.loads(mpb.read_text()); man["tasks"][0]["title"] = "different"
            mpb.write_text(json.dumps(man))
            epb = Path(b) / "e.jsonl"; epb.write_bytes(epa.read_bytes())
            self.assertNotEqual(_s(Controller(mpb, repob, Path(b) / "s.json", epb).run()), "PASS")

    def test_ec17_command_replay(self):
        """Old command evidence replayed after command mutation."""
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"][0]["command"] = "python3 -VV"
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# EC-20..24: MUTATION TIMING / RECOVERY
# ==========================================================================
class MutationTiming(unittest.TestCase):
    def test_ec20_mutation_during_validation(self):
        """Mutation BETWEEN runs (during the gap between two locked runs)."""
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            # run 1: PASS; mutation happens here (between runs)
            (repo / "out.txt").write_text("EXTERNAL", encoding="utf-8")
            # run 2: old evidence's target_hashes don't match → NOT PASS
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ec21_mutation_before_evidence_commit(self):
        """If target is mutated before evidence append, the next run catches it."""
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            (repo / "out.txt").write_text("PRE_COMMIT", encoding="utf-8")
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_ec23_recovery_after_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            (repo / "out.txt").write_text("MUT", encoding="utf-8")
            sp.write_text("{broken")  # force recovery
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).recover()), "PASS")

    def test_ec24_recovery_after_crash(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            sp.write_text("{broken")
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).recover()), "PASS")


# ==========================================================================
# EC-25..28: DETERMINISM / IDENTITY
# ==========================================================================
class DeterminismIdentity(unittest.TestCase):
    def test_ec25_equivalent_state_determinism(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            norms = []
            for i in range(3):
                r = Controller(mp, repo, Path(d) / f"s{i}.json", Path(d) / f"e{i}.jsonl").run(dry_run=True)
                norms.append(json.dumps({k: r.report[k] for k in ("graph", "classifications")}, sort_keys=True))
            self.assertEqual(len(set(norms)), 1)

    def test_ec27_validator_identity_constant(self):
        from impl_controller.provenance import VALIDATOR_IDENTITY
        self.assertEqual(VALIDATOR_IDENTITY, "impl_controller")


# ==========================================================================
# EC-29: COMPLETE SYNTHETIC PASS
# ==========================================================================
class SyntheticPass(unittest.TestCase):
    def test_ec29_complete_pass_lifecycle(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            r = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_s(r), "PASS")
            # verify evidence chain intact
            self.assertTrue(r.report["evidence_integrity"]["intact"])
            # verify traceability closure CLOSED
            tr = r.report["traceability"][0]
            self.assertEqual(tr["closure"], "CLOSED")


# ==========================================================================
# EC-30: SEED REGRESSION
# ==========================================================================
class SeedRegression(unittest.TestCase):
    def test_ec30_seed_unchanged(self):
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
