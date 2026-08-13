"""Pipeline-boundary adversarial validation (Stage-5).

Treats Planner -> Controller -> Executor -> Validator -> Evidence ->
Traceability as the security/correctness boundary. 20 attacks; each asserts
an invariant. Run via:  python3 tools/impl-controller.py --self-test
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
sys.path.insert(0, str(TOOLS))

from impl_controller.controller import Controller                       # noqa
from impl_controller.manifest import load_manifest, ManifestError       # noqa
from impl_controller.engine import classify_all, authority_problems    # noqa
from impl_controller.evidence import EvidenceLog, EvidenceRecord        # noqa
from impl_controller.safety import validate_command, SafetyError        # noqa
from impl_controller.contract import build_execution_contract           # noqa
from impl_controller.model import TaskState                             # noqa


def _run(args, cwd=None):
    return subprocess.run([PY, str(RUNNER)] + args, capture_output=True,
                          text=True, cwd=cwd or str(REPO_ROOT))


def _synth_repo(d, with_git=False):
    repo = Path(d) / "repo"; repo.mkdir()
    (repo / "spec.md").write_text("# spec\n", encoding="utf-8")
    (repo / "spec2.md").write_text("# spec2\n", encoding="utf-8")
    if with_git:
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        env = dict(os.environ); env.update({
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "i"],
                       check=True, env=env)
    return repo


def _manifest(tasks, tools=None):
    return {"schema_version": "1.0", "project": "t",
            "tool_registry": tools or {"python3": {"available": True}},
            "tasks": tasks}


def _task(tid="T", **o):
    b = {"task_id": tid, "title": tid, "description": "d", "priority": 1,
         "plan_order": 1, "scope": "s",
         "source_authority": [{"doc": "spec.md"}],
         "requirement_refs": ["REQ-1"],
         "specification_refs": [{"doc": "spec.md"}],
         "dependency_refs": [], "required_tools": [],
         "allowed_tools": ["python3"],
         "validation_commands": [{"id": "V1", "command": "python3 -V",
                                  "expected_exit": 0}],
         "acceptance_criteria": [{"id": "A1", "criterion": "c"}]}
    b.update(o); return b


def _write(d, obj):
    p = Path(d) / "m.json"; p.write_text(json.dumps(obj), encoding="utf-8")
    return p


class PipelineAttacks(unittest.TestCase):

    # 1. planner produces malformed manifest
    def test_01_malformed_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            mp = Path(d) / "m.json"; mp.write_text("{bad json", encoding="utf-8")
            r = _run(["--manifest", str(mp), "--repo-root", str(repo),
                      "--status-out", str(Path(d) / "o.json"), "--quiet"])
            self.assertEqual(r.returncode, 2)

    # 2. planner references nonexistent authority
    def test_02_nonexistent_authority(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            mp = _write(d, _manifest([_task("T", source_authority=[{"doc": "ghost.md"}])]))
            m = load_manifest(mp)
            cl = classify_all(m.tasks, m.tool_registry, repo)
            self.assertEqual(cl["T"].effective_state, "BLOCKED")
            self.assertEqual(cl["T"].blocker_class, "INSUFFICIENT_TASK_DEFINITION")

    # 3. planner references authority outside repository
    def test_03_authority_outside_repo(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            mp = _write(d, _manifest([_task("T", source_authority=[{"doc": "../etc/passwd"}])]))
            m = load_manifest(mp)
            cl = classify_all(m.tasks, m.tool_registry, repo)
            self.assertEqual(cl["T"].effective_state, "BLOCKED")
            self.assertIn("INSUFFICIENT_TASK_DEFINITION", cl["T"].reasons)

    # 4. planner attempts to alter an immutable blocker (falsify tool availability)
    def test_04_alter_immutable_blocker(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            # planner LIES: claims rebol-278 available and strips declared blockers
            tools = {"rebol-278": {"available": True, "detail": "claimed present"}}
            t = _task("T", required_tools=["rebol-278"], declared_blockers=[])
            mp = _write(d, _manifest([t], tools=tools))
            m = load_manifest(mp)
            cl = classify_all(m.tasks, m.tool_registry, repo)
            # invariant: rebol is NOT actually present -> still BLOCKED (TOOLCHAIN)
            self.assertEqual(cl["T"].effective_state, "BLOCKED",
                             "falsified tool availability must not unblock")
            self.assertIn("TOOLCHAIN", cl["T"].reasons)

    # 5. planner injects an undeclared dependency
    def test_05_undeclared_dependency(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            mp = _write(d, _manifest([_task("T", dependency_refs=[{"ref": "GHOST"}])]))
            with self.assertRaises(ManifestError):
                load_manifest(mp)

    # 6. controller emits a contract for a non-READY task
    def test_06_contract_for_non_ready(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            t = _task("T", required_tools=["rebol-278"])
            mp = _write(d, _manifest([t], tools={"rebol-278": {"available": False}}))
            m = load_manifest(mp)
            cl = classify_all(m.tasks, m.tool_registry, repo)
            with self.assertRaises(ValueError):
                build_execution_contract(m.tasks[0], cl, m.tool_registry)

    # 7. executor attempts a command outside its allowlist
    def test_07_command_outside_allowlist(self):
        with self.assertRaises((SafetyError, Exception)):
            validate_command("wget http://x", ["python3"])

    # 8. executor attempts shell interpretation
    def test_08_shell_interpretation(self):
        for bad in ["sh -c true", "python3 -V; rm x", "python3 -V$(rm x)",
                    "python3 -V | cat", "python3 -V > /tmp/x"]:
            with self.assertRaises((SafetyError, Exception), msg=bad):
                validate_command(bad, ["python3", "sh"])

    # 9. executor writes outside declared target scope
    def test_09_write_outside_scope(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d, with_git=True)
            t = _task("T", implementation_targets=["allowed.txt"],
                      validation_commands=[{"id": "V1",
                          "command": "python3 -c \"open('evil.txt','w').write('x')\"",
                          "expected_exit": 0}])
            mp = _write(d, _manifest([t]))
            r = _run(["--manifest", str(mp), "--repo-root", str(repo),
                      "--state", str(Path(d) / "s.json"),
                      "--evidence", str(Path(d) / "e.jsonl"),
                      "--status-out", str(Path(d) / "o.json"),
                      "--execute", "--allow-tool", "python3", "--quiet"])
            status = json.loads((Path(d) / "o.json").read_text())
            # invariant: out-of-scope write must NOT yield PASS
            cls = {c["task_id"]: c for c in status["classifications"]}
            self.assertNotEqual(cls["T"]["effective_state"], "PASS",
                                "out-of-scope write must not become PASS")

    # 10. validator reports PASS with inconsistent exit status
    def test_10_pass_inconsistent_exit(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            log.append(EvidenceRecord("E1", "T", "false", exit_status=2,
                                      result="PASS", expected_exit=0))
            self.assertEqual(log.validated_pass(), set())  # not trusted

    # 11. evidence truncated, reordered, duplicated, tampered
    def test_11a_truncated(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            log.append(EvidenceRecord("E1", "T", "python3 -V", exit_status=0,
                                      result="PASS", expected_exit=0))
            log.append(EvidenceRecord("E2", "T", "python3 -V", exit_status=0,
                                      result="PASS", expected_exit=0))
            data = ep.read_bytes()
            ep.write_bytes(data[:len(data) // 2])  # truncate mid-record
            log2 = EvidenceLog(ep)
            self.assertLessEqual(log2.verify_integrity()["trusted_records"], 1)

    def test_11b_reordered(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            for i in range(3):
                log.append(EvidenceRecord(f"E{i}", "T", "python3 -V",
                          exit_status=0, result="PASS", expected_exit=0))
            lines = ep.read_text().splitlines()
            ep.write_text("\n".join([lines[1], lines[0], lines[2]]) + "\n")
            self.assertLess(EvidenceLog(ep).verify_integrity()["trusted_records"], 3)

    def test_11c_duplicated(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            log.append(EvidenceRecord("E1", "T", "python3 -V", exit_status=0,
                                      result="PASS", expected_exit=0))
            lines = ep.read_text().splitlines()
            ep.write_text("\n".join([lines[0], lines[0]]) + "\n")  # duplicate
            self.assertLessEqual(EvidenceLog(ep).verify_integrity()["trusted_records"], 1)

    def test_11d_tampered(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"; log = EvidenceLog(ep)
            log.append(EvidenceRecord("E1", "T", "python3 -V", exit_status=0,
                                      result="PASS", expected_exit=0))
            rec = json.loads(ep.read_text().strip())
            rec["stdout"] = "TAMPERED"
            ep.write_text(json.dumps(rec) + "\n")
            self.assertFalse(EvidenceLog(ep).verify_integrity()["intact"])

    # 12. traceability contains a requirement with no specification
    def test_12_requirement_without_specification(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            t = _task("T", requirement_refs=["REQ-1"], specification_refs=[])
            mp = _write(d, _manifest([t]))
            m = load_manifest(mp)
            cl = classify_all(m.tasks, m.tool_registry, repo)
            self.assertEqual(cl["T"].effective_state, "BLOCKED")
            self.assertIn("INSUFFICIENT_TASK_DEFINITION", cl["T"].reasons)

    # 13. traceability contains a task with no requirement
    def test_13_task_without_requirement(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            t = _task("T", requirement_refs=[])
            mp = _write(d, _manifest([t]))
            m = load_manifest(mp)
            cl = classify_all(m.tasks, m.tool_registry, repo)
            self.assertEqual(cl["T"].effective_state, "BLOCKED")

    # 14. task PASS occurs while its authority subsequently changes
    def test_14_pass_then_authority_changes(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            mp = _write(d, _manifest([_task("T")]))
            sp, ep, so = Path(d) / "s.json", Path(d) / "e.jsonl", Path(d) / "o.json"
            c = Controller(mp, repo, sp, ep)
            c.run(execute=True)  # PASS
            (repo / "spec.md").unlink()
            c2 = Controller(mp, repo, sp, ep)
            r = c2.run()
            self.assertNotEqual(r.classifications["T"].effective_state, "PASS")

    # 15. dependency PASS subsequently becomes invalid
    def test_15_dependency_pass_invalidated(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            dep = _task("DEP"); user = _task("USER", dependency_refs=[{"ref": "DEP"}])
            mp = _write(d, _manifest([dep, user]))
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            Controller(mp, repo, sp, ep).run(execute=True)  # DEP -> PASS
            # invalidate DEP by removing its evidence-backed authority
            (repo / "spec.md").unlink()
            r = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(r.classifications["USER"].effective_state, "READY")

    # 16. pipeline interrupted between execution and evidence recording
    def test_16_interrupt_exec_to_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            mp = _write(d, _manifest([_task("T")]))
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            # simulate: begin() ran, evidence never written, no save
            from impl_controller.checkpoint import StateStore
            st = StateStore(sp); st.load(); st.begin("T"); st.save("h")
            r = Controller(mp, repo, sp, ep).run()
            self.assertNotEqual(r.classifications["T"].effective_state, "PASS")

    # 17. pipeline interrupted between evidence and checkpoint
    def test_17_interrupt_evidence_to_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            mp = _write(d, _manifest([_task("T")]))
            sp, ep = Path(d) / "s.json", Path(d) / "e.jsonl"
            # run a real execute to write evidence + checkpoint
            Controller(mp, repo, sp, ep).run(execute=True)
            # now rewind the CHECKPOINT to pre-execute while keeping evidence
            sp.write_text(json.dumps({"repo_head": "h", "tasks": [
                {"task_id": "T", "state": "IN_PROGRESS", "in_progress": True}]}),
                encoding="utf-8")
            r = Controller(mp, repo, sp, ep).run()
            # evidence is authoritative -> task recovers to PASS (true positive)
            self.assertEqual(r.classifications["T"].effective_state, "PASS")
            self.assertFalse(r.classifications["T"].ready)

    # 18. two pipeline processes attempt the same READY task
    def test_18_concurrent_same_task(self):
        from impl_controller.locking import FileLock
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            mp = _write(d, _manifest([_task("T")]))
            sp, ep, so = Path(d) / "s.json", Path(d) / "e.jsonl", Path(d) / "o.json"
            lock_path = Path(d) / "controller.lock"   # controller.lock = state dir
            # one process HOLDS the lease; a second attempt must be denied
            holder = FileLock(lock_path); holder.acquire()
            try:
                r = _run(["--manifest", str(mp), "--repo-root", str(repo),
                          "--state", str(sp), "--evidence", str(ep),
                          "--status-out", str(so), "--execute", "--allow-tool",
                          "python3", "--quiet"])
                self.assertEqual(r.returncode, 1,
                                 "second lease must be denied while held")
            finally:
                holder.release()

    # 19. CI runs with a different working directory
    def test_19_different_working_directory(self):
        so = Path(tempfile.mkdtemp()) / "o.json"
        # run from /tmp, NO --manifest: defaults must resolve against --repo-root
        r = _run(["--repo-root", str(REPO_ROOT), "--dry-run",
                  "--state", str(Path(tempfile.mkdtemp()) / "s.json"),
                  "--evidence", str(Path(tempfile.mkdtemp()) / "e.jsonl"),
                  "--status-out", str(so), "--quiet"], cwd="/tmp")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(so.exists())
        st = json.loads(so.read_text())
        self.assertEqual(st["frontier"], "PAUSED")

    # 20. repeated execution produces nondeterministic status/traceability
    def test_20_repeated_execution_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _synth_repo(d)
            mp = _write(d, _manifest([_task("T")]))
            norm = []
            for i in range(3):
                sd = Path(d) / f"r{i}"; sd.mkdir()
                sp, ep, so = sd / "s.json", sd / "e.jsonl", sd / "o.json"
                _run(["--manifest", str(mp), "--repo-root", str(repo),
                      "--state", str(sp), "--evidence", str(ep),
                      "--status-out", str(so), "--execute", "--allow-tool",
                      "python3", "--quiet"])
                s = json.loads(so.read_text())
                n = json.dumps({k: s[k] for k in
                                ("frontier", "graph", "classifications")},
                               sort_keys=True)
                norm.append(n)
            self.assertEqual(len(set(norm)), 1, "normalized output must be stable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
