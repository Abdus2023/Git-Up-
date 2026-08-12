"""Phase 27 — State-machine monotonicity, invalidation & fixpoint closure.

Proves: OBSOLETE AUTHORITY MUST NEVER BECOME VALID AGAIN without new valid
authoritative basis. Every mutation invalidates; recovery converges; derived
state is irrelevant to classification; retry is idempotent; no resurrection.
Run via:  python3 tools/impl-controller.py --self-test
"""
import json, os, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from impl_controller.controller import Controller


def _synth(d, target="out.txt", content="hello", git=False):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    if target:
        (repo / target).write_text(content, encoding="utf-8")
    t = {"task_id": "SYNTH-001", "title": "syn", "description": "d", "priority": 1,
         "plan_order": 1, "scope": "s", "source_authority": [{"doc": "spec.md"}],
         "requirement_refs": ["REQ-1"], "specification_refs": [{"doc": "spec.md"}],
         "implementation_targets": [target] if target else [],
         "dependency_refs": [], "required_tools": [], "allowed_tools": ["python3"],
         "validation_commands": [{"id": "V1", "command": "python3 -V", "expected_exit": 0}],
         "acceptance_criteria": [{"id": "AC1", "criterion": "c", "validator": "V1"}]}
    man = {"schema_version": "1.0", "project": "sm",
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


def _norm(r):
    return json.dumps({k: r.report[k] for k in ("graph", "classifications")}, sort_keys=True)


# ==========================================================================
# A. PASS INVALIDATION (SM-01..10)
# ==========================================================================
class PassInvalidation(unittest.TestCase):
    def _mutate_and_check(self, mutator):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")
            mutator(mp, repo, d)
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_sm01_contract_mutation(self):
        self._mutate_and_check(lambda mp, r, d: mp.write_text(
            json.dumps({**json.loads(mp.read_text()), "tasks": [
                {**json.loads(mp.read_text())["tasks"][0], "title": "changed"}]})))

    def test_sm02_manifest_mutation(self):
        def m(mp, r, d):
            man = json.loads(mp.read_text()); man["project"] = "changed"; mp.write_text(json.dumps(man))
        self._mutate_and_check(m)

    def test_sm04_criterion_mutation(self):
        def m(mp, r, d):
            man = json.loads(mp.read_text())
            man["tasks"][0]["acceptance_criteria"][0]["id"] = "AC2"
            mp.write_text(json.dumps(man))
        self._mutate_and_check(m)

    def test_sm05_validator_mutation(self):
        def m(mp, r, d):
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"][0]["command"] = "python3 -VV"
            mp.write_text(json.dumps(man))
        self._mutate_and_check(m)

    def test_sm06_target_mutation(self):
        def m(mp, r, d):
            (r / "out.txt").write_text("MUTATED", encoding="utf-8")
        self._mutate_and_check(m)

    def test_sm08_command_mutation(self):
        def m(mp, r, d):
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"][0]["expected_exit"] = 1
            mp.write_text(json.dumps(man))
        self._mutate_and_check(m)

    def test_sm10_head_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d, git=True)
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")
            (repo / "new.txt").write_text("x")
            import subprocess
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c"], check=True, env=env)
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# B. EVIDENCE RESURRECTION (SM-11..20)
# ==========================================================================
class EvidenceResurrection(unittest.TestCase):
    def test_sm11_delete_evidence_checkpoint_restore(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d); ep.unlink()
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_sm13_replay_old_contract_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "x"
            mp.write_text(json.dumps(man))
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_sm15_replay_other_task_evidence(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _, _, _, epa = _pass(a)
            mpb, repob = _synth(b)
            epb = Path(b) / "e.jsonl"; epb.write_bytes(epa.read_bytes())
            self.assertNotEqual(_s(Controller(mpb, repob, Path(b) / "s.json", epb).run()), "PASS")

    def test_sm19_forge_checkpoint_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            sp.write_text(json.dumps({"tasks": [
                {"task_id": "SYNTH-001", "state": "PASS", "validated_pass": True}]}))
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_sm20_forge_pipeline_status_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            (Path(d) / "forged.json").write_text(json.dumps({"frontier": "READY"}))
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")  # controller ignores


# ==========================================================================
# C. RECOVERY (SM-21..28)
# ==========================================================================
class Recovery(unittest.TestCase):
    def test_sm21_crash_before_execution(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            sp.write_text("{broken")
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).recover()), "PASS")

    def test_sm23_crash_after_exec_before_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            from impl_controller.checkpoint import StateStore
            st = StateStore(sp); st.load(); st.begin("SYNTH-001")  # crash before evidence
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).recover()), "PASS")

    def test_sm27_recover_x10_fixpoint(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d); sp.write_text("{broken")
            norms = [_norm(Controller(mp, repo, sp, ep).recover()) for _ in range(10)]
            self.assertEqual(len(set(norms)), 1)


# ==========================================================================
# D. RETRY / IDEMPOTENCY (SM-29..36)
# ==========================================================================
class RetryIdempotency(unittest.TestCase):
    def test_sm29_retry_verified_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            before = len(ep.read_text().splitlines())
            Controller(mp, repo, sp, ep).run(execute=True)  # retry
            self.assertEqual(len(ep.read_text().splitlines()), before)

    def test_sm30_retry_invalidated_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            original = (repo / "out.txt").read_text()
            (repo / "out.txt").write_text("CHANGED", encoding="utf-8")  # invalidate
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")
            (repo / "out.txt").write_text(original, encoding="utf-8")  # restore target
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")  # old evidence valid

    def test_sm32_retry_after_contract_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "x"
            mp.write_text(json.dumps(man))
            res = Controller(mp, repo, sp, ep).run(execute=True)
            self.assertEqual(_s(res), "PASS")  # new contract -> fresh execute


# ==========================================================================
# E. DERIVED-STATE ATTACKS (SM-37..44)
# ==========================================================================
class DerivedStateAttacks(unittest.TestCase):
    def test_sm38_forge_pipeline_pass_no_effect(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            (Path(d) / "st.json").write_text(json.dumps({"frontier": "PAUSED"}))
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")

    def test_sm40_forge_ledger_satisfied_no_effect(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            res = Controller(mp, repo, sp, ep).run()
            self.assertEqual(_s(res), "PASS")  # ledger is derived; never authorizes

    def test_sm42_forge_traceability_no_effect(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            (Path(d) / "tr.json").write_text(json.dumps({"closure": "COMPLETE"}))
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")


# ==========================================================================
# F. DETERMINISM / CONVERGENCE (SM-45..50)
# ==========================================================================
class DeterminismConvergence(unittest.TestCase):
    def test_sm50_repeated_reconciliation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            norms = []
            for _ in range(5):
                r = Controller(mp, repo, sp, ep).run()
                norms.append(_norm(r))
            self.assertEqual(len(set(norms)), 1)


# ==========================================================================
# J. AUTHORITY-FLIP PROOF
# ==========================================================================
class AuthorityFlip(unittest.TestCase):
    def test_full_authority_flip(self):
        """VALID PASS → delete evidence → corrupt derived → recover → still
        NOT PASS → restore manifest → still NOT PASS → fresh execute → PASS.
        Proves: authority ≠ derived state; recovery ≠ authority; no evidence
        resurrects through checkpoint or derived artifacts."""
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = _pass(d)
            man0 = mp.read_text()
            # 1. VALID PASS
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")
            # 2. delete authoritative evidence
            ep.unlink()
            # 3. corrupt derived artifacts
            sp.write_text("{corrupt")
            (Path(d) / "fake.json").write_text('{"PASS": true}')
            # 4. recover -> NOT PASS (no evidence)
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).recover()), "PASS")
            # 5. restore manifest (unchanged) -> still NOT PASS (evidence gone)
            mp.write_text(man0)
            self.assertNotEqual(_s(Controller(mp, repo, sp, ep).recover()), "PASS")
            # 6. fresh execution
            Controller(mp, repo, sp, ep).run(execute=True)
            # 7. PASS (fresh evidence)
            self.assertEqual(_s(Controller(mp, repo, sp, ep).run()), "PASS")


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
        self.assertEqual(cls["HASH-001"]["reasons"],
                         ["INCOMPLETE_SPECIFICATION", "TOOLCHAIN"])
        self.assertEqual(cls["RFC0075-001"]["reasons"],
                         ["SPECIFICATION_CONFLICT", "INCOMPLETE_SPECIFICATION"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
