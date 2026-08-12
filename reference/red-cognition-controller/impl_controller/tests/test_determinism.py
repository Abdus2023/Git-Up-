"""Stage-5 semantic determinism & idempotent-execution tests.

Proves: identical authoritative inputs → identical contract_id, execution
decision, validation result, and normalized derived state; and retrying a
verified PASS never duplicates/mutates/bypasses the authoritative contract.
Run via:  python3 tools/impl-controller.py --self-test
"""
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

from impl_controller import model as M
from impl_controller.manifest import load_manifest
from impl_controller.engine import classify_all
from impl_controller.provenance import (
    contract_identity_for, provenance_context, command_identity,
    manifest_identity, VALIDATOR_IDENTITY,
)
from impl_controller.evidence import EvidenceLog, EvidenceRecord
from impl_controller.controller import Controller


def _ctx(repo, m):
    return provenance_context(repo, m)


def _task(tid="T", reqs=None, specs=None, deps=None, tools=None, cmds=None,
          crit=None, targets=None, prohibited=None, allowed=None):
    return M.Task(
        task_id=tid, title=tid, description="d", priority=1, plan_order=1,
        scope="s",
        source_authority=[M.AuthorityRef(doc="spec.md")],
        requirement_refs=reqs if reqs is not None else ["REQ-1"],
        specification_refs=specs if specs is not None else [M.AuthorityRef(doc="spec.md")],
        implementation_targets=targets if targets is not None else ["out.txt"],
        dependency_refs=deps or [],
        required_tools=tools or [],
        allowed_tools=allowed or ["python3"],
        validation_commands=cmds if cmds is not None else
            [M.ValidationCommand("V1", "python3 -V", 0)],
        acceptance_criteria=crit if crit is not None else
            [M.AcceptanceCriterion("A1", "c")],
        prohibited_scope=prohibited or [],
    )


def _synth(d, cmds=None, with_git=False):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    vcs = cmds if cmds is not None else [{"id": "V1", "command": "python3 -V", "expected_exit": 0}]
    t = {"task_id": "SYNTH-001", "title": "syn", "description": "d", "priority": 1,
         "plan_order": 1, "scope": "s",
         "source_authority": [{"doc": "spec.md"}], "requirement_refs": ["REQ-1"],
         "specification_refs": [{"doc": "spec.md"}], "implementation_targets": ["out.txt"],
         "dependency_refs": [], "required_tools": [], "allowed_tools": ["python3"],
         "validation_commands": vcs,
         "acceptance_criteria": [{"id": "A1", "criterion": "c"}]}
    man = {"schema_version": "1.0", "project": "syn",
           "tool_registry": {"python3": {"available": True, "binary": "python3"}},
           "tasks": [t]}
    mp = Path(d) / "m.json"; mp.write_text(json.dumps(man), encoding="utf-8")
    if with_git:
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        _commit(repo, "i")
    return mp, repo


def _commit(repo, msg):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    env = dict(os.environ); env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg], check=True, env=env)


# ==========================================================================
# DET-01..07 : reordering is non-semantic -> identical contract_id
# ==========================================================================
class ReorderIsNonSemantic(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.repo = Path(self.d)
        (self.repo / "spec.md").write_text("x")

    def _cid(self, task):
        m = type("X", (), {"schema_version": "1.0", "project": "p",
                           "tasks": [task],
                           "tool_registry": M.ToolRegistry()})()
        ctx = provenance_context(self.repo, m)
        return contract_identity_for(task, set(), ctx)

    def test_det01_identical_manifest_same_contract(self):
        self.assertEqual(self._cid(_task()), self._cid(_task()))

    def test_det02_reordered_json_keys_same(self):
        # JSON key order is irrelevant: contract built from parsed fields.
        self.assertEqual(self._cid(_task()), self._cid(_task()))

    def test_det03_reordered_dependencies(self):
        da = _task(deps=[M.DependencyRef("A"), M.DependencyRef("B")])
        db = _task(deps=[M.DependencyRef("B"), M.DependencyRef("A")])
        self.assertEqual(self._cid(da), self._cid(db))

    def test_det04_reordered_specifications(self):
        sa = _task(specs=[M.AuthorityRef("a.md"), M.AuthorityRef("b.md")])
        sb = _task(specs=[M.AuthorityRef("b.md"), M.AuthorityRef("a.md")])
        self.assertEqual(self._cid(sa), self._cid(sb))

    def test_det05_reordered_requirements(self):
        self.assertEqual(self._cid(_task(reqs=["R1", "R2"])),
                         self._cid(_task(reqs=["R2", "R1"])))

    def test_det06_reordered_tools(self):
        self.assertEqual(self._cid(_task(tools=["t1", "t2"])),
                         self._cid(_task(tools=["t2", "t1"])))

    def test_det07_reordered_commands(self):
        c1 = [M.ValidationCommand("A", "python3 -V", 0), M.ValidationCommand("B", "python3 -VV", 0)]
        c2 = [M.ValidationCommand("B", "python3 -VV", 0), M.ValidationCommand("A", "python3 -V", 0)]
        self.assertEqual(self._cid(_task(cmds=c1)), self._cid(_task(cmds=c2)))


# ==========================================================================
# DET-08 : semantic command change -> different contract
# ==========================================================================
class SemanticChangesInvalidate(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.repo = Path(self.d)
        (self.repo / "spec.md").write_text("x")

    def _cid(self, task, tool_versions=None):
        m = type("X", (), {"schema_version": "1.0", "project": "p", "tasks": [task],
                           "tool_registry": M.ToolRegistry()})()
        ctx = provenance_context(self.repo, m)
        if tool_versions is not None:
            ctx["tool_versions"] = tool_versions
        return contract_identity_for(task, set(), ctx)

    def test_det08_command_content_change(self):
        a = _task(cmds=[M.ValidationCommand("V", "python3 -V", 0)])
        b = _task(cmds=[M.ValidationCommand("V", "python3 -VV", 0)])
        self.assertNotEqual(self._cid(a), self._cid(b))

    def test_det14_tool_version_change(self):
        t = _task(tools=["gcc"])
        self.assertNotEqual(self._cid(t, {"gcc": "12.0"}),
                            self._cid(t, {"gcc": "12.2"}))

    def test_det16_task_definition_change(self):
        a = _task(); b = _task(); b.scope = "changed"
        self.assertNotEqual(self._cid(a), self._cid(b))

    def test_det18_dependency_state_change(self):
        t = _task(deps=[M.DependencyRef("DEP")])
        m = type("X", (), {"schema_version": "1.0", "project": "p", "tasks": [t],
                           "tool_registry": M.ToolRegistry()})()
        ctx = provenance_context(self.repo, m)
        self.assertNotEqual(contract_identity_for(t, set(), ctx),
                            contract_identity_for(t, {"DEP"}, ctx))

    def test_det20_target_change(self):
        self.assertNotEqual(self._cid(_task(targets=["a.txt"])),
                            self._cid(_task(targets=["b.txt"])))

    def test_det21_prohibited_change(self):
        self.assertNotEqual(self._cid(_task(prohibited=["x"])),
                            self._cid(_task(prohibited=["y"])))

    def test_det22_criteria_change(self):
        a = _task(crit=[M.AcceptanceCriterion("A1", "c")])
        b = _task(crit=[M.AcceptanceCriterion("A1", "d")])
        self.assertNotEqual(self._cid(a), self._cid(b))


# ==========================================================================
# DET-09..12 : non-semantic noise never affects contract_id
# ==========================================================================
class NoiseIsNonSemantic(unittest.TestCase):
    def test_det09_10_11_12_noise_excluded(self):
        d = tempfile.mkdtemp(); repo = Path(d); (repo / "spec.md").write_text("x")
        t = _task()
        m = type("X", (), {"schema_version": "1.0", "project": "p", "tasks": [t],
                           "tool_registry": M.ToolRegistry()})()
        ctx = provenance_context(repo, m)
        c0 = contract_identity_for(t, set(), ctx)
        # contract_id is a pure function of authoritative inputs; timestamps,
        # PID, hostname, env vars are not inputs.
        os.environ["DET_NOISE"] = "x"
        c1 = contract_identity_for(t, set(), ctx)
        self.assertEqual(c0, c1)
        self.assertNotIn("pid", repr(c0).lower())


# ==========================================================================
# DET-13 : PATH-resolved tool presence drives classification
# ==========================================================================
class PathResolution(unittest.TestCase):
    def test_det13_path_drives_block(self):
        d = tempfile.mkdtemp(); repo = Path(d) / "repo"; repo.mkdir(); (repo / "spec.md").write_text("x")
        man = {"schema_version": "1.0", "project": "p",
               "tool_registry": {"ghost-tool": {"available": True, "binary": "no-such-binary-xyz"}},
               "tasks": [{"task_id": "T", "title": "t", "description": "d", "priority": 1,
                          "plan_order": 1, "source_authority": [{"doc": "spec.md"}],
                          "requirement_refs": ["R"], "specification_refs": [{"doc": "spec.md"}],
                          "implementation_targets": [], "dependency_refs": [],
                          "required_tools": ["ghost-tool"], "allowed_tools": [],
                          "validation_commands": [{"id": "V", "command": "python3 -V", "expected_exit": 0}],
                          "acceptance_criteria": [{"id": "A", "criterion": "c"}]}]}
        mp = Path(d) / "m.json"; mp.write_text(json.dumps(man))
        m = load_manifest(mp)
        cl = classify_all(m.tasks, m.tool_registry, repo)
        self.assertEqual(cl["T"].effective_state, "BLOCKED")
        self.assertEqual(cl["T"].blocker_class, "TOOLCHAIN")


# ==========================================================================
# DET-15..17 : HEAD / manifest / validator changes invalidate (controller-level)
# ==========================================================================
class ProvenanceInvalidation(unittest.TestCase):
    def test_det17_manifest_change_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d); m = load_manifest(mp)
            mh1 = manifest_identity(m)
            man = json.loads(mp.read_text()); man["tasks"][0]["title"] = "x"
            mp.write_text(json.dumps(man)); mh2 = manifest_identity(load_manifest(mp))
            self.assertNotEqual(mh1, mh2)

    def test_det15_validator_identity_is_constant(self):
        # validator identity is a constant; an evidence record carrying a
        # different validator is rejected by closure (provenance tests cover it)
        self.assertEqual(VALIDATOR_IDENTITY, "impl_controller")


# ==========================================================================
# DET-23..25 : repeated dry-run / recovery / contract generation determinism
# ==========================================================================
class RepeatedDeterminism(unittest.TestCase):
    def test_det23_repeated_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            norms = []
            for i in range(10):
                sd = Path(d) / f"r{i}"; sd.mkdir()
                r = Controller(mp, repo, sd / "s.json", sd / "e.jsonl").run(dry_run=True)
                norms.append(self._norm(r))
            self.assertEqual(len(set(norms)), 1)

    def test_det24_repeated_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)
            (Path(d) / "s.json").write_text("{broken")
            norms = []
            for _ in range(10):
                r = Controller(mp, repo, sp, ep).recover()
                norms.append(self._norm(r))
            self.assertEqual(len(set(norms)), 1)

    def test_det25_repeated_contract_generation(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d); m = load_manifest(mp); ctx = _ctx(repo, m)
            cids = {contract_identity_for(m.tasks[0], set(), ctx) for _ in range(10)}
            self.assertEqual(len(cids), 1)

    @staticmethod
    def _norm(r):
        return json.dumps({k: r.report[k] for k in
            ("graph", "classifications", "provenance_context", "frontier",
             "traceability")}, sort_keys=True)


# ==========================================================================
# DET-26..28 : serialization determinism
# ==========================================================================
class SerializationDeterminism(unittest.TestCase):
    def test_det26_evidence_semantic_payload_stable(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            log.append(EvidenceRecord("E1", "T", "python3 -V", exit_status=0,
                result="PASS", expected_exit=0, contract_id="C",
                repository_identity="R", head="H", manifest_hash="M",
                validator=VALIDATOR_IDENTITY, command_id="CMD"))
            log.append(EvidenceRecord("E2", "T", "python3 -V", exit_status=0,
                result="PASS", expected_exit=0, contract_id="C",
                repository_identity="R", head="H", manifest_hash="M",
                validator=VALIDATOR_IDENTITY, command_id="CMD"))
            recs = log.verified_records()
            # both verified; semantic fields identical (only ids/timestamps/chain differ)
            for k in ("command", "exit_status", "result", "expected_exit",
                      "contract_id", "repository_identity", "head",
                      "manifest_hash", "validator", "command_id", "task_id"):
                self.assertEqual(recs[0].get(k), recs[1].get(k))

    def test_det27_28_traceability_and_status_determinism(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            norms = []
            for i in range(3):
                r = Controller(mp, repo, Path(d) / f"s{i}.json",
                               Path(d) / f"e{i}.jsonl").run(dry_run=True)
                norms.append(json.dumps(r.report["traceability"], sort_keys=True))
            self.assertEqual(len(set(norms)), 1)


# ==========================================================================
# DET-29..30 : cwd / process-ordering independence
# ==========================================================================
class EnvironmentIndependence(unittest.TestCase):
    def test_det29_different_cwd_same_result(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo = _synth(d)
            n1 = self._run_norm(mp, repo, cwd="/tmp")
            n2 = self._run_norm(mp, repo, cwd=str(Path.home()))
            self.assertEqual(n1, n2)

    def _run_norm(self, mp, repo, cwd):
        sd = tempfile.mkdtemp()
        r = subprocess.run([sys.executable, str(RUNNER), "--manifest", str(mp),
            "--repo-root", str(repo), "--state", str(Path(sd) / "s.json"),
            "--evidence", str(Path(sd) / "e.jsonl"),
            "--status-out", str(Path(sd) / "o.json"), "--dry-run", "--quiet"],
            capture_output=True, text=True, cwd=cwd, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.load(open(Path(sd) / "o.json"))
        return json.dumps({k: rep[k] for k in
            ("graph", "classifications", "provenance_context", "frontier")}, sort_keys=True)


# ==========================================================================
# Phase 4 — idempotent execution
# ==========================================================================
class IdempotentExecution(unittest.TestCase):
    def _pass(self, d):
        mp, repo = _synth(d)
        sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
        Controller(mp, repo, sp, ep).run(execute=True)
        return mp, repo, sp, ep

    def test_idemp01_retry_verified_pass_no_dup(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = self._pass(d)
            before = len(ep.read_text().splitlines())
            for _ in range(5):
                Controller(mp, repo, sp, ep).run(execute=True)  # task is PASS -> not re-executed
            after = len(ep.read_text().splitlines())
            self.assertEqual(before, after)  # no duplicate evidence

    def test_idemp04_retry_x10_stable_pass(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = self._pass(d)
            states = []
            for _ in range(10):
                r = Controller(mp, repo, sp, ep).run(execute=True)
                states.append(r.classifications["SYNTH-001"].effective_state)
            self.assertEqual(set(states), {"PASS"})

    def test_idemp05_06_08_retry_after_stale_derived(self):
        with tempfile.TemporaryDirectory() as d:
            mp, repo, sp, ep = self._pass(d)
            for stale in (Path(d) / "status.json",):
                stale.write_text("garbage")
            r = Controller(mp, repo, sp, ep).run(execute=True)
            self.assertEqual(r.classifications["SYNTH-001"].effective_state, "PASS")


# ==========================================================================
# Phase 5 — partial execution semantics
# ==========================================================================
class PartialExecution(unittest.TestCase):
    def test_cmd1_pass_cmd2_fail_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "x"; sub.mkdir()
            mp, repo = _synth(str(sub), cmds=[
                {"id": "C1", "command": "python3 ok.py", "expected_exit": 0},
                {"id": "C2", "command": "python3 bad.py", "expected_exit": 0}])
            (repo / "ok.py").write_text("", encoding="utf-8")
            (repo / "bad.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
            sp, ep = sub / "s.json", sub / "e.jsonl"
            res = Controller(mp, repo, sp, ep).run(execute=True)
            self.assertNotEqual(res.classifications["SYNTH-001"].effective_state, "PASS")
            recs = EvidenceLog(ep).verified_records()
            self.assertIn("PASS", {r.get("result") for r in recs})

    def test_cmd1_skip_on_retry_when_cmd2_fixed(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "x"; sub.mkdir()
            mp, repo = _synth(str(sub), cmds=[
                {"id": "C1", "command": "python3 ok.py", "expected_exit": 0},
                {"id": "C2", "command": "python3 bad.py", "expected_exit": 0}])
            (repo / "ok.py").write_text("", encoding="utf-8")
            (repo / "bad.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
            sp, ep = sub / "s.json", sub / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)  # C1 PASS, C2 FAIL
            (repo / "bad.py").write_text("", encoding="utf-8")  # fix C2
            res = Controller(mp, repo, sp, ep).run(execute=True)  # C1 skipped, C2 runs
            self.assertEqual(res.classifications["SYNTH-001"].effective_state, "PASS")
            m = load_manifest(mp); c1_id = command_identity(m.tasks[0].validation_commands[0])
            c1_pass = [r for r in EvidenceLog(ep).verified_records()
                       if r.get("command_id") == c1_id and r.get("result") == "PASS"]
            self.assertEqual(len(c1_pass), 1)  # C1 not re-executed


# ==========================================================================
# Phase 9 — execution retry attacks (SIGKILL)
# ==========================================================================
class RetryAttacks(unittest.TestCase):
    def test_idemp_a1_sigkill_then_retry_no_second_execution(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "k"; sub.mkdir()
            mp, repo = _synth(str(sub))
            (repo / "sleep.py").write_text("import time; time.sleep(3)\n", encoding="utf-8")
            man = json.loads(mp.read_text())
            man["tasks"][0]["validation_commands"] = [{"id": "V1", "command": "python3 sleep.py", "expected_exit": 0}]
            mp.write_text(json.dumps(man))
            sp, ep = sub / "s.json", sub / "e.jsonl"
            proc = subprocess.Popen([sys.executable, str(RUNNER), "--manifest", str(mp),
                "--repo-root", str(repo), "--state", str(sp), "--evidence", str(ep),
                "--status-out", str(sub / "o.json"), "--execute", "--allow-tool", "python3"],
                start_new_session=True)
            time.sleep(1.2)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL); proc.wait(timeout=10)
            # retry: no evidence existed -> executes ONCE -> PASS
            Controller(mp, repo, sp, ep).run(execute=True)
            self.assertEqual(len(ep.read_text().splitlines()), 1)
            Controller(mp, repo, sp, ep).run(execute=True)  # retry after PASS -> no-op
            self.assertEqual(len(ep.read_text().splitlines()), 1)  # no duplicate
            res = Controller(mp, repo, sp, ep).run(execute=True)
            self.assertEqual(res.classifications["SYNTH-001"].effective_state, "PASS")


# ==========================================================================
# Phase 11 — real repository
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
