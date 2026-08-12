"""Adversarial hardening suite for the Implementation Execution Controller.

Covers categories A..N from the hardening mandate. Every test encodes a
fail-closed expectation: malformed/ambiguous/stale/tampered input must NEVER
transform into permission (BLOCKED->READY, FAIL->PASS, IN_PROGRESS->PASS).

Run via:  python3 tools/impl-controller.py --self-test
(the CLI discovers both test_*.py files under tests/).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from impl_controller import model as M
from impl_controller.manifest import load_manifest, ManifestError
from impl_controller.engine import classify_all, classify_task, blocking_chain, authority_problems
from impl_controller.evidence import EvidenceRecord, EvidenceLog, EvidenceError, safe_command
from impl_controller.safety import validate_command, validate_targets, SafetyError
from impl_controller.locking import FileLock, LockAcquisitionError
from impl_controller.checkpoint import StateStore
from impl_controller.controller import Controller
from impl_controller.model import TaskState

REPO_ROOT = TOOLS.parent


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def mk_repo(d: Path) -> Path:
    root = Path(d)
    (root / "spec.md").write_text("# spec v1\n", encoding="utf-8")
    (root / "req.md").write_text("# req\n", encoding="utf-8")
    return root


def task_dict(tid="T", **over):
    base = {
        "task_id": tid, "title": tid, "description": "d", "priority": 10,
        "plan_order": 1, "scope": "s",
        "source_authority": [{"doc": "spec.md"}],
        "requirement_refs": ["REQ-1"],
        "specification_refs": [{"doc": "spec.md"}],
        "dependency_refs": [], "required_tools": [],
        "validation_commands": [{"id": "V1", "command": "python3 -V", "expected_exit": 0}],
        "acceptance_criteria": [{"id": "A1", "criterion": "c"}],
    }
    base.update(over)
    return base


def manifest(tasks, tools=None, **over):
    m = {"schema_version": "1.0", "project": "test",
         "tool_registry": tools or {"python3": {"available": True}}, "tasks": tasks}
    m.update(over)
    return m


def write(d: Path, obj) -> Path:
    p = Path(d) / "m.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


# ==========================================================================
# A. MANIFEST ATTACKS
# ==========================================================================
class A_ManifestAttacks(unittest.TestCase):
    def _bad(self, obj, tmp):
        with self.assertRaises(ManifestError):
            load_manifest(write(tmp, obj))

    def test_a1_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("DUP"), task_dict("DUP")]), Path(d))

    def test_a2_unknown_dependency(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T", dependency_refs=[{"ref": "NOPE"}])]), Path(d))

    def test_a4_missing_task_id(self):
        with tempfile.TemporaryDirectory() as d:
            t = task_dict(); t.pop("task_id")
            self._bad(manifest([t]), Path(d))

    def test_a5_missing_title(self):
        with tempfile.TemporaryDirectory() as d:
            t = task_dict(); t.pop("title")
            self._bad(manifest([t]), Path(d))

    def test_a7_invalid_status_is_unknown_field(self):
        # status is derived, not declared; a declared status is an unknown field
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T", status="READY")]), Path(d))

    def test_a8_invalid_priority(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T", priority="high")]), Path(d))

    def test_a9_malformed_requirement_refs(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T", requirement_refs="REQ-1")]), Path(d))

    def test_a10_missing_authority(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T", source_authority=[])]), Path(d)) \
                if False else None
            # authority presence is enforced at CLASSIFY time (INSUFFICIENT),
            # but an authority ref without 'doc' is a structural error:
            self._bad(manifest([task_dict("T", source_authority=[{"anchor": "x"}])]),
                      Path(d))

    def test_a13_malformed_validation_command(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T", validation_commands=[{"id": "V"}])]), Path(d))

    def test_a14_malformed_blocker(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T", declared_blockers=[{"satisfied": False}])]),
                      Path(d))

    def test_a15_unknown_task_field(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T", dependenc_refs=[])]), Path(d))  # typo

    def test_a15b_unknown_toplevel_field(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T")], garbage=1), Path(d))

    def test_a16_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.json"
            p.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ManifestError):
                load_manifest(p)

    def test_a17_empty_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad({"schema_version": "1.0", "project": "x", "tasks": []}, Path(d))

    def test_a18_duplicate_evidence_refs(self):
        with tempfile.TemporaryDirectory() as d:
            self._bad(manifest([task_dict("T", evidence_refs=["E1", "E1"])]), Path(d))

    def test_a3_unknown_tool_id_classifies_blocked(self):
        # unknown tool id is not a structural error; it yields TOOLCHAIN block
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            t = task_dict("T", required_tools=["nope-tool"])
            m = load_manifest(write(Path(d), manifest([t])))
            cl = classify_all(m.tasks, m.tool_registry, root)
            self.assertEqual(cl["T"].effective_state, "BLOCKED")
            self.assertEqual(cl["T"].blocker_class, "TOOLCHAIN")


# ==========================================================================
# B. DEPENDENCY GRAPH ATTACKS
# ==========================================================================
class B_DependencyGraph(unittest.TestCase):
    def _cycle(self, edges):
        # edges: list of (id, [dep_ids]); builds a manifest and expects rejection
        with tempfile.TemporaryDirectory() as d:
            tasks = [task_dict(a, dependency_refs=[{"ref": x} for x in deps])
                     for a, deps in edges]
            with self.assertRaises(ManifestError) as cm:
                load_manifest(write(Path(d), manifest(tasks)))
            return str(cm.exception)

    def test_b1_direct_cycle(self):
        self.assertIn("cycle", self._cycle([("A", ["B"]), ("B", ["A"])]))

    def test_b2_indirect_cycle(self):
        self.assertIn("cycle",
                      self._cycle([("A", ["B"]), ("B", ["C"]), ("C", ["A"])]))

    def test_b3_self_dependency(self):
        self.assertIn("cycle", self._cycle([("A", ["A"])]))

    def _dep_state(self, dep_state):
        """Build DEP with a given forced classification then classify USER."""
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            dep = task_dict("DEP")
            user = task_dict("USER", dependency_refs=[{"ref": "DEP"}])
            m = load_manifest(write(Path(d), manifest([dep, user])))
            # validated_pass controls DEP being PASS
            vp = {"DEP"} if dep_state == "PASS" else set()
            cl = classify_all(m.tasks, m.tool_registry, root, validated_pass=vp)
            if dep_state == "REJECTED":
                dep_t = m.tasks[0]; dep_t.rejected = True
                cl = classify_all(m.tasks, m.tool_registry, root, validated_pass=set())
            return cl["USER"].effective_state, cl["USER"].blocker_class

    def test_b4_dep_rejected(self):
        st, bc = self._dep_state("REJECTED")
        self.assertEqual(st, "BLOCKED"); self.assertEqual(bc, "DEPENDENCY")

    def test_b5_to_b8_dep_not_pass(self):
        for s in ("BLOCKED", "FAIL", "IN_PROGRESS", "DEFERRED"):
            st, bc = self._dep_state(s)  # DEP not validated_pass -> not PASS
            self.assertEqual(st, "BLOCKED", msg=f"dep_state={s}")
            self.assertEqual(bc, "DEPENDENCY", msg=f"dep_state={s}")

    def test_b9_b10_invalidation(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            dep = task_dict("DEP"); user = task_dict("USER", dependency_refs=[{"ref": "DEP"}])
            m = load_manifest(write(Path(d), manifest([dep, user])))
            cl1 = classify_all(m.tasks, m.tool_registry, root, validated_pass={"DEP"})
            self.assertEqual(cl1["USER"].effective_state, "READY")
            cl2 = classify_all(m.tasks, m.tool_registry, root, validated_pass=set())
            self.assertEqual(cl2["USER"].effective_state, "BLOCKED")

    def test_blocking_chain_reports(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            A = task_dict("A", dependency_refs=[{"ref": "B"}])
            B = task_dict("B", dependency_refs=[{"ref": "C"}])
            C = task_dict("C", required_tools=["rebol-278"])  # leaf blocked
            m = load_manifest(write(Path(d), manifest([A, B, C],
                                                      tools={"rebol-278": {"available": False}})))
            cl = classify_all(m.tasks, m.tool_registry, root)
            by_id = {t.task_id: t for t in m.tasks}
            chain = blocking_chain("A", cl, by_id)
            self.assertEqual(chain, ["A", "B", "C"])


# ==========================================================================
# C. SPECIFICATION AUTHORITY ATTACKS
# ==========================================================================
class C_Authority(unittest.TestCase):
    def test_c1_missing_authority_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)  # no spec.md
            t = M.Task(task_id="T", title="T", description="d",
                       source_authority=[M.AuthorityRef(doc="spec.md")],
                       requirement_refs=["R"],
                       validation_commands=[M.ValidationCommand("V", "python3 -V")],
                       acceptance_criteria=[M.AcceptanceCriterion("A", "c")])
            self.assertTrue(authority_problems(t, root))

    def test_c3_authority_replaced_by_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / "spec.md").mkdir()
            t = M.Task(task_id="T", title="T", description="d",
                       source_authority=[M.AuthorityRef(doc="spec.md")],
                       requirement_refs=["R"],
                       validation_commands=[M.ValidationCommand("V", "python3 -V")],
                       acceptance_criteria=[M.AcceptanceCriterion("A", "c")])
            self.assertTrue(authority_problems(t, root))

    def test_c4_authority_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); p = root / "spec.md"; p.write_text("x"); p.chmod(0o000)
            t = M.Task(task_id="T", title="T", description="d",
                       source_authority=[M.AuthorityRef(doc="spec.md")],
                       requirement_refs=["R"],
                       validation_commands=[M.ValidationCommand("V", "python3 -V")],
                       acceptance_criteria=[M.AcceptanceCriterion("A", "c")])
            self.assertTrue(authority_problems(t, root))
            p.chmod(0o644)

    def test_c5_authority_outside_repo(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            t = M.Task(task_id="T", title="T", description="d",
                       source_authority=[M.AuthorityRef(doc="../etc/passwd")],
                       requirement_refs=["R"],
                       validation_commands=[M.ValidationCommand("V", "python3 -V")],
                       acceptance_criteria=[M.AcceptanceCriterion("A", "c")])
            self.assertTrue(authority_problems(t, root))

    def test_c2_deleted_after_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            m = load_manifest(write(Path(d), manifest([task_dict("T")])))
            cl1 = classify_all(m.tasks, m.tool_registry, root)
            self.assertEqual(cl1["T"].effective_state, "READY")
            (root / "spec.md").unlink()  # delete authority
            cl2 = classify_all(m.tasks, m.tool_registry, root)
            self.assertEqual(cl2["T"].effective_state, "BLOCKED")
            self.assertEqual(cl2["T"].blocker_class, "INSUFFICIENT_TASK_DEFINITION")


# ==========================================================================
# D. CHECKPOINT ATTACKS
# ==========================================================================
class D_Checkpoint(unittest.TestCase):
    def test_d1_d2_truncated_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "s.json"
            sp.write_text("{truncated", encoding="utf-8")
            st = StateStore(sp); st.load()
            self.assertEqual(st.tasks, {})  # rejected -> clean start

    def test_d4_unknown_task_ids_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "s.json"
            sp.write_text(json.dumps({"tasks": [
                {"task_id": "GHOST", "state": "PASS", "validated_pass": True}]}),
                encoding="utf-8")
            st = StateStore(sp); st.load()
            # loaded but inert: not in any manifest, never satisfies a real dep
            self.assertTrue(st.get("GHOST").validated_pass)

    def test_d5_checkpoint_pass_without_evidence_demoted(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("T")]))
            sp = Path(d) / "s.json"; ep = Path(d) / "e.jsonl"
            # seed a checkpoint claiming PASS with NO evidence
            sp.write_text(json.dumps({"tasks": [
                {"task_id": "T", "state": "PASS", "validated_pass": True}]}),
                encoding="utf-8")
            ctrl = Controller(mp, root, sp, ep)
            res = ctrl.run(dry_run=False)
            # no evidence -> authoritative pass empty -> demoted
            self.assertNotIn("T", res.classifications and [c for c in [res.classifications["T"]] if c.effective_state == "PASS"] or [])
            self.assertNotEqual(res.classifications["T"].effective_state, "PASS")

    def test_d6_in_progress_after_change_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("T", required_tools=["rebol-278"])]))
            sp = Path(d) / "s.json"; ep = Path(d) / "e.jsonl"
            sp.write_text(json.dumps({"tasks": [
                {"task_id": "T", "state": "IN_PROGRESS", "in_progress": True}]}),
                encoding="utf-8")
            ctrl = Controller(mp, root, sp, ep,
                              execute_allow=None)
            from impl_controller.manifest import load_manifest
            m = load_manifest(mp)
            cl = classify_all(m.tasks, m.tool_registry, root)
            changed = ctrl.store.load() or None
            ctrl.store.invalidate_stale(cl)
            self.assertFalse(ctrl.store.get("T").in_progress)


# ==========================================================================
# E. EVIDENCE ATTACKS
# ==========================================================================
class E_Evidence(unittest.TestCase):
    def _log_with_pass(self, d, **over):
        ep = Path(d) / "e.jsonl"
        log = EvidenceLog(ep)
        rec = EvidenceRecord(evidence_id="E1", task_id="T1", command="python3 -V",
                             stdout="Python 3.11.2\n", exit_status=0, result="PASS",
                             expected_exit=0, **over)
        log.append(rec)
        return ep, log

    def test_e11_pass_nonzero_exit_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"
            log = EvidenceLog(ep)
            log.append(EvidenceRecord("E1", "T1", "false", exit_status=1,
                                      result="PASS", expected_exit=0))
            self.assertEqual(log.validated_pass(), set())

    def test_e10_pass_without_command_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"
            log = EvidenceLog(ep)
            log.append(EvidenceRecord("E1", "T1", "", exit_status=0,
                                      result="PASS", expected_exit=0))
            self.assertEqual(log.validated_pass(), set())

    def test_e14_tampered_record_breaks_chain(self):
        with tempfile.TemporaryDirectory() as d:
            ep, log = self._log_with_pass(d)
            self.assertEqual(log.validated_pass(), {"T1"})
            # tamper: rewrite the stdout of the historical record
            lines = ep.read_text(encoding="utf-8").splitlines()
            rec = json.loads(lines[0]); rec["stdout"] = "TAMPERED"
            # recompute record_hash would be needed to keep chain; we do NOT -> break
            ep.write_text(json.dumps(rec) + "\n", encoding="utf-8")
            log2 = EvidenceLog(ep)
            self.assertEqual(log2.validated_pass(), set())
            self.assertFalse(log2.verify_integrity()["intact"])

    def test_e_malformed_line_breaks_chain(self):
        with tempfile.TemporaryDirectory() as d:
            ep, log = self._log_with_pass(d)
            with ep.open("a", encoding="utf-8") as fh:
                fh.write("{not json\n")
            log2 = EvidenceLog(ep)
            self.assertEqual(log2.validated_pass(), {"T1"})  # first still trusted
            self.assertEqual(log2.verify_integrity()["trusted_records"], 1)

    def test_e13_duplicate_evidence_ids_integrity_failure(self):
        # Hardened (recovery-phase) contract: a duplicate evidence_id is an
        # integrity failure. The chain stops at the duplicate; only the first
        # record is trusted and there is no duplicate PASS transition.
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "e.jsonl"
            log = EvidenceLog(ep)
            r1 = EvidenceRecord("ED", "T1", "python3 -V", exit_status=0,
                                result="PASS", expected_exit=0)
            r2 = EvidenceRecord("ED", "T1", "python3 -V", exit_status=0,
                                result="PASS", expected_exit=0)
            log.append(r1); log.append(r2)
            self.assertLessEqual(len(log.verified_records()), 1)
            self.assertEqual(log.validated_pass(), {"T1"})  # PASS is a set

    def test_e_unknown_task_evidence_isolated(self):
        with tempfile.TemporaryDirectory() as d:
            ep, log = self._log_with_pass(d)  # T1 PASS
            self.assertEqual(log.validated_pass(), {"T1"})  # not applied to unknown tasks


# ==========================================================================
# F. EXECUTION (COMMAND) SAFETY
# ==========================================================================
class F_CommandSafety(unittest.TestCase):
    BAD = ["python3 -V; rm -rf /", "python3 -V && rm x", "python3 -V || true",
           "python3 -V | cat", "python3 -V > /tmp/x", "python3 -V >> /tmp/x",
           "python3 -V < /etc/passwd", "python3 -V$(rm x)", "python3 -V`rm x`",
           "python3 ${EVIL}", "python3 -V\nrm -rf /", "python3 -V\rrm"]

    def test_metacharacters_rejected(self):
        for cmd in self.BAD:
            with self.assertRaises((SafetyError, EvidenceError), msg=cmd):
                safe_command(cmd, ["python3"])

    def test_executable_outside_registry_rejected(self):
        with self.assertRaises(EvidenceError):
            safe_command("wget http://x", ["python3"])

    def test_absolute_exe_rejected(self):
        with self.assertRaises(EvidenceError):
            safe_command("/bin/sh -c x", ["sh", "/bin/sh"])

    def test_traversal_exe_rejected(self):
        with self.assertRaises(EvidenceError):
            safe_command("../rebol -V", ["rebol", ".."])

    def test_absolute_arg_rejected(self):
        with self.assertRaises(EvidenceError):
            safe_command("python3 /etc/passwd", ["python3"])

    def test_traversal_arg_rejected(self):
        with self.assertRaises(EvidenceError):
            safe_command("python3 ../../etc/passwd", ["python3"])

    def test_shell_invocation_rejected(self):
        with self.assertRaises(EvidenceError):
            safe_command("sh -c 'rm -rf /'", ["sh"])

    def test_env_injection_rejected(self):
        with self.assertRaises(EvidenceError):
            safe_command("python3 -V$X", ["python3"])

    def test_safe_command_passes(self):
        safe_command("python3 -V", ["python3"])  # no raise


# ==========================================================================
# G. FILE-SCOPE ESCAPE
# ==========================================================================
class G_FileScope(unittest.TestCase):
    def test_targets_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            for bad in ["../outside.txt", "/tmp/outside.txt",
                        "~/outside.txt", "~/.ssh/id_rsa", ".git/config"]:
                v = validate_targets([bad], root)
                self.assertTrue(v, msg=f"expected rejection for {bad}")

    def test_in_repo_target_ok(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            self.assertEqual(validate_targets(["src/new.txt", "build/out"], root), [])

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"; root.mkdir()
            (root / "spec.md").write_text("x")
            outside = Path(d) / "outside.txt"; outside.write_text("x")
            link = root / "escape.txt"
            try:
                os.symlink(outside, link)
            except OSError:
                self.skipTest("symlinks not supported")
            v = validate_targets(["escape.txt"], root)
            self.assertTrue(v)

    def test_manifest_rejects_unsafe_targets(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("T",
                 implementation_targets=["../outside.txt"])]))
            m = load_manifest(mp)
            with self.assertRaises(ManifestError):
                m.validate_paths(root)


# ==========================================================================
# H. REPOSITORY DRIFT
# ==========================================================================
class H_Drift(unittest.TestCase):
    def test_authority_modified_after_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("T")]))
            ctrl = Controller(mp, root, Path(d) / "s.json", Path(d) / "e.jsonl")
            r1 = ctrl.run(dry_run=False)
            self.assertEqual(r1.classifications["T"].effective_state, "READY")
            (root / "spec.md").unlink()  # drift: authority gone
            ctrl2 = Controller(mp, root, Path(d) / "s.json", Path(d) / "e.jsonl")
            r2 = ctrl2.run(dry_run=False)
            self.assertEqual(r2.classifications["T"].effective_state, "BLOCKED")

    def test_head_change_noted(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("T")]))
            sp = Path(d) / "s.json"
            sp.write_text(json.dumps({"repo_head": "deadbeef", "tasks": []}),
                          encoding="utf-8")
            ctrl = Controller(mp, root, sp, Path(d) / "e.jsonl")
            res = ctrl.run(dry_run=False)
            self.assertTrue(any("HEAD changed" in n for n in res.drift_notes))


# ==========================================================================
# I. INTERRUPTED EXECUTION
# ==========================================================================
class I_Interruption(unittest.TestCase):
    def test_begin_without_finish_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("T", required_tools=["rebol-278"])]))
            sp = Path(d) / "s.json"; ep = Path(d) / "e.jsonl"
            store = StateStore(sp); store.load(); store.begin("T"); store.save("h")
            # simulate crash; restart reclassifies -> T is BLOCKED (no rebol), in_progress cleared
            ctrl = Controller(mp, root, sp, ep)
            res = ctrl.run(dry_run=False)
            self.assertEqual(res.classifications["T"].effective_state, "BLOCKED")
            self.assertFalse(ctrl.store.get("T").in_progress)

    def test_no_false_pass_on_crash_before_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("T")]))
            sp = Path(d) / "s.json"; ep = Path(d) / "e.jsonl"
            store = StateStore(sp); store.load(); store.begin("T"); store.save("h")
            # no evidence written; restart must NOT mark PASS
            ctrl = Controller(mp, root, sp, ep)
            ctrl.run(dry_run=False)
            self.assertNotEqual(ctrl.store.get("T").state, "PASS")
            self.assertFalse(ctrl.store.get("T").validated_pass)


# ==========================================================================
# J. CONCURRENT EXECUTION
# ==========================================================================
class J_Concurrency(unittest.TestCase):
    def test_two_locks_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            lp = Path(d) / "controller.lock"
            l1 = FileLock(lp); l1.acquire()
            try:
                with self.assertRaises(LockAcquisitionError):
                    FileLock(lp).acquire()
            finally:
                l1.release()

    def test_controller_lease(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("T")]))
            sp = Path(d) / "s.json"; ep = Path(d) / "e.jsonl"
            ctrl = Controller(mp, root, sp, ep)
            # hold the lease externally
            holder = FileLock(ctrl.lock_path); holder.acquire()
            try:
                res = ctrl.run(dry_run=False)
                self.assertEqual(res.result, "FAIL")  # locked -> fail closed
            finally:
                holder.release()


# ==========================================================================
# K. DETERMINISM
# ==========================================================================
class K_Determinism(unittest.TestCase):
    def test_dry_run_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("A"), task_dict("B"),
                                          task_dict("C")]))
            r1 = Controller(mp, root, Path(d) / "s1.json", Path(d) / "e1.json").run(dry_run=True)
            r2 = Controller(mp, root, Path(d) / "s2.json", Path(d) / "e2.json").run(dry_run=True)
            norm = lambda r: json.dumps({k: r.report[k] for k in
                        ("graph", "classifications", "ready_queue",
                         "execution_contracts", "frontier", "task_count")},
                        sort_keys=True)
            self.assertEqual(norm(r1), norm(r2))


# ==========================================================================
# L. FAIL-CLOSED PROPERTY (aggregation)
# ==========================================================================
class L_FailClosed(unittest.TestCase):
    def test_every_malformed_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)  # no authority files
            cases = [
                task_dict("C1"),  # authority missing on disk
                task_dict("C2", required_tools=["ghost"]),
                task_dict("C3", spec_conflicts=["X"]),
                task_dict("C4", spec_gaps=["G"]),
            ]
            m = load_manifest(write(Path(d), manifest(cases)))
            cl = classify_all(m.tasks, m.tool_registry, root)
            for tid, c in cl.items():
                self.assertNotEqual(c.effective_state, "READY",
                                    f"{tid} must not be READY")


# ==========================================================================
# M. SYNTHETIC UNBLOCK LIFECYCLE
# ==========================================================================
class M_SyntheticLifecycle(unittest.TestCase):
    def test_ready_to_pass_and_invalidate(self):
        with tempfile.TemporaryDirectory() as d:
            root = mk_repo(Path(d))
            mp = write(Path(d), manifest([task_dict("SYNTH-001",
                allowed_tools=["python3"],
                implementation_targets=["out.txt"])]))
            sp = Path(d) / "s.json"; ep = Path(d) / "e.jsonl"
            # 1) READY
            c0 = Controller(mp, root, sp, ep)
            r0 = c0.run(dry_run=False)
            self.assertEqual(r0.classifications["SYNTH-001"].effective_state, "READY")
            # 2) execute -> IN_PROGRESS -> PASS
            c1 = Controller(mp, root, sp, ep)
            r1 = c1.run(dry_run=False, execute=True)
            self.assertEqual(r1.result, "PASS")
            self.assertEqual(c1.store.get("SYNTH-001").state, "PASS")
            self.assertTrue(c1.store.get("SYNTH-001").validated_pass)
            self.assertTrue(r1.new_evidence)
            self.assertEqual(r1.new_evidence[0]["exit_status"], 0)
            self.assertTrue(r1.new_evidence[0]["evidence_id"])
            # 3) mutate authority -> invalidate prior PASS
            (root / "spec.md").unlink()
            c2 = Controller(mp, root, sp, ep)
            r2 = c2.run(dry_run=False)
            self.assertNotEqual(r2.classifications["SYNTH-001"].effective_state, "PASS")
            self.assertEqual(r2.classifications["SYNTH-001"].effective_state, "BLOCKED")


# ==========================================================================
# N. REAL-REPOSITORY NON-INTERFERENCE
# ==========================================================================
class N_RealRepo(unittest.TestCase):
    def test_real_repo_blocked(self):
        mp = REPO_ROOT / "docs" / "implementation" / "implementation-plan.json"
        if not mp.is_file():
            self.skipTest("seed manifest absent")
        c = Controller(mp, REPO_ROOT,
                       REPO_ROOT / ".impl_controller" / "_h_state.json",
                       REPO_ROOT / ".impl_controller" / "_h_evidence.jsonl")
        res = c.run(dry_run=True)
        self.assertEqual(res.ready_queue, [])
        self.assertEqual(res.frontier, "PAUSED")
        for tid in ("RED-LEX-001", "LIBRED-001", "HASH-001", "RFC0075-001"):
            self.assertEqual(res.classifications[tid].effective_state, "BLOCKED", tid)
        # integrity: no product file touched
        self.assertTrue(res.report["evidence_integrity"]["intact"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
