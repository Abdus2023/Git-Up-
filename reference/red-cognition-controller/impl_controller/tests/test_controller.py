"""Self-test suite for the Implementation Execution Controller.

Covers the eight mandated cases plus fail-closed, schema, queue, contract,
checkpoint, evidence, and a real-manifest integration assertion. Uses only
the standard library (unittest). Run via:

    python3 tools/impl-controller.py --self-test
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# make the package importable when run via unittest discovery
HERE = Path(__file__).resolve().parent
PKG = HERE.parent                       # .../tools/impl_controller
TOOLS = PKG.parent                       # .../tools
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from impl_controller import model as M
from impl_controller.engine import classify_task, classify_all, self_blockers
from impl_controller.queue import build_ready_queue, dependency_depth
from impl_controller.contract import build_execution_contract
from impl_controller.evidence import EvidenceRecord, EvidenceLog, safe_command, EvidenceError
from impl_controller.checkpoint import StateStore
from impl_controller.manifest import load_manifest, ManifestError
from impl_controller.controller import Controller
from impl_controller.model import TaskState, BlockerCategory

REPO_ROOT = TOOLS.parent                 # .../Red-Cognition-


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _repo(tmp: Path) -> Path:
    (tmp / "spec.md").write_text("# spec\n", encoding="utf-8")
    return tmp


def _tool_reg(rebol=False, python3=True):
    return M.ToolRegistry([
        M.Tool(id="rebol-278", available=rebol),
        M.Tool(id="python3", available=python3),
    ])


def _ready_task(tid="T-READY", deps=None, tools=None, conflicts=None,
                gaps=None, authority=True, with_validation=True,
                with_criteria=True):
    t = M.Task(
        task_id=tid, title=tid, description="d", priority=10, plan_order=0,
        scope="s",
        source_authority=[M.AuthorityRef(doc="spec.md")] if authority else [],
        requirement_refs=["REQ-1"] if authority else [],
        specification_refs=[M.AuthorityRef(doc="spec.md")] if authority else [],
        dependency_refs=deps or [],
        required_tools=tools or [],
        validation_commands=[M.ValidationCommand(id="V1", command="python3 -V")]
        if with_validation else [],
        acceptance_criteria=[M.AcceptanceCriterion(id="A1", criterion="ok")]
        if with_criteria else [],
        spec_conflicts=conflicts or [], spec_gaps=gaps or [],
    )
    return t


# --------------------------------------------------------------------------
# Case 1 — READY task with satisfied dependencies
# --------------------------------------------------------------------------
class Case1Ready(unittest.TestCase):
    def test_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=[])
            c = classify_task(t, satisfied_deps=set(), tool_registry=_tool_reg(),
                              repo_root=root)
            self.assertEqual(c.effective_state, "READY")
            self.assertTrue(c.ready)
            self.assertIsNone(c.blocker_class)


# --------------------------------------------------------------------------
# Case 2 — missing dependency -> BLOCKED - DEPENDENCY
# --------------------------------------------------------------------------
class Case2Dependency(unittest.TestCase):
    def test_missing_dep(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=[],
                            deps=[M.DependencyRef(ref="MISSING", required_state="PASS")])
            c = classify_task(t, satisfied_deps=set(), tool_registry=_tool_reg(),
                              repo_root=root)
            self.assertEqual(c.effective_state, "BLOCKED")
            self.assertEqual(c.blocker_class, "DEPENDENCY")
            self.assertIn("DEPENDENCY", c.reasons)


# --------------------------------------------------------------------------
# Case 3 — missing toolchain -> BLOCKED - TOOLCHAIN
# --------------------------------------------------------------------------
class Case3Toolchain(unittest.TestCase):
    def test_missing_tool(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=["rebol-278"])
            c = classify_task(t, satisfied_deps=set(),
                              tool_registry=_tool_reg(rebol=False), repo_root=root)
            self.assertEqual(c.effective_state, "BLOCKED")
            self.assertEqual(c.blocker_class, "TOOLCHAIN")
            self.assertIn("TOOLCHAIN", c.reasons)


# --------------------------------------------------------------------------
# Case 4 — specification conflict -> BLOCKED - SPECIFICATION
# --------------------------------------------------------------------------
class Case4SpecConflict(unittest.TestCase):
    def test_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=[], conflicts=["CONFLICT-1"])
            c = classify_task(t, satisfied_deps=set(), tool_registry=_tool_reg(),
                              repo_root=root)
            self.assertEqual(c.effective_state, "BLOCKED")
            self.assertIn("SPECIFICATION_CONFLICT", c.reasons)

    def test_incomplete_spec(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=[], gaps=["GAP-1"])
            c = classify_task(t, satisfied_deps=set(), tool_registry=_tool_reg(),
                              repo_root=root)
            self.assertEqual(c.effective_state, "BLOCKED")
            self.assertIn("INCOMPLETE_SPECIFICATION", c.reasons)


# --------------------------------------------------------------------------
# Case 5 — missing authoritative requirement -> INSUFFICIENT_TASK_DEFINITION
# --------------------------------------------------------------------------
class Case5Insufficient(unittest.TestCase):
    def test_no_authority(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=[], authority=False)
            c = classify_task(t, satisfied_deps=set(), tool_registry=_tool_reg(),
                              repo_root=root)
            self.assertEqual(c.effective_state, "BLOCKED")
            self.assertIn("INSUFFICIENT_TASK_DEFINITION", c.reasons)

    def test_authority_doc_missing_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)  # NOTE: no spec.md created -> fail closed
            t = _ready_task(tools=[], authority=True)
            c = classify_task(t, satisfied_deps=set(), tool_registry=_tool_reg(),
                              repo_root=root)
            self.assertEqual(c.effective_state, "BLOCKED")
            self.assertIn("INSUFFICIENT_TASK_DEFINITION", c.reasons)

    def test_no_validation(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=[], with_validation=False)
            c = classify_task(t, satisfied_deps=set(), tool_registry=_tool_reg(),
                              repo_root=root)
            self.assertIn("INSUFFICIENT_TASK_DEFINITION", c.reasons)


# --------------------------------------------------------------------------
# Case 6 — all tasks blocked -> READY = 0, PAUSED
# --------------------------------------------------------------------------
class Case6AllBlocked(unittest.TestCase):
    def test_all_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            tasks = [
                _ready_task("A", tools=["rebol-278"]),
                _ready_task("B", conflicts=["X"]),
            ]
            cl = classify_all(tasks, _tool_reg(rebol=False), root)
            q = build_ready_queue(tasks, cl)
            self.assertEqual(q, [])
            self.assertTrue(all(c.effective_state == "BLOCKED"
                                for c in cl.values()))


# --------------------------------------------------------------------------
# Case 7 — completed dependency becomes PASS -> dependent READY
# --------------------------------------------------------------------------
class Case7DepSatisfied(unittest.TestCase):
    def test_dep_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            dep = _ready_task("DEP", tools=[])
            dependent = _ready_task("DEP-USER", tools=[],
                                    deps=[M.DependencyRef(ref="DEP", required_state="PASS")])
            cl = classify_all([dep, dependent], _tool_reg(), root, validated_pass={"DEP"})
            # DEP is the completed (validated) dependency -> terminal PASS.
            self.assertEqual(cl["DEP"].effective_state, "PASS")
            # DEP-USER's PASS dependency is satisfied -> READY.
            self.assertEqual(cl["DEP-USER"].effective_state, "READY")


# --------------------------------------------------------------------------
# Case 8 — dependency later invalid -> READY invalidated
# --------------------------------------------------------------------------
class Case8DepInvalidated(unittest.TestCase):
    def test_dep_invalidated(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            dep = _ready_task("DEP", tools=[])
            dependent = _ready_task("DEP-USER", tools=[],
                                    deps=[M.DependencyRef(ref="DEP", required_state="PASS")])
            # pass then fail
            cl_pass = classify_all([dep, dependent], _tool_reg(), root,
                                   validated_pass={"DEP"})
            self.assertEqual(cl_pass["DEP-USER"].effective_state, "READY")
            cl_fail = classify_all([dep, dependent], _tool_reg(), root,
                                   validated_pass=set())
            self.assertEqual(cl_fail["DEP-USER"].effective_state, "BLOCKED")
            self.assertEqual(cl_fail["DEP-USER"].blocker_class, "DEPENDENCY")


# --------------------------------------------------------------------------
# Validated PASS is terminal (not recomputed, not re-queued)
# --------------------------------------------------------------------------
class ValidatedPassTerminal(unittest.TestCase):
    def test_pass_not_requeued(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task("T", tools=[])
            cl = classify_all([t], _tool_reg(), root, validated_pass={"T"})
            self.assertEqual(cl["T"].effective_state, "PASS")
            self.assertFalse(cl["T"].ready)
            self.assertEqual(build_ready_queue([t], cl), [])

    def test_pass_satisfies_dependent(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            dep = _ready_task("DEP", tools=[])
            user = _ready_task("USER", tools=[],
                               deps=[M.DependencyRef(ref="DEP", required_state="PASS")])
            cl = classify_all([dep, user], _tool_reg(), root, validated_pass={"DEP"})
            self.assertEqual(cl["DEP"].effective_state, "PASS")
            self.assertEqual(cl["USER"].effective_state, "READY")


# --------------------------------------------------------------------------
# Fail-closed + contract
# --------------------------------------------------------------------------
class FailClosed(unittest.TestCase):
    def test_contract_refuses_non_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=["rebol-278"])
            cl = classify_all([t], _tool_reg(rebol=False), root)
            with self.assertRaises(ValueError):
                build_execution_contract(t, cl, _tool_reg())

    def test_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=[])
            t.rejected = True
            c = classify_task(t, set(), _tool_reg(), root)
            self.assertEqual(c.effective_state, "REJECTED")

    def test_deferred(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            t = _ready_task(tools=[])
            t.deferred = True
            c = classify_task(t, set(), _tool_reg(), root)
            self.assertEqual(c.effective_state, "DEFERRED")

    def test_command_safety(self):
        # Hardened contract: an EMPTY allowlist authorizes NOTHING (fail closed).
        with self.assertRaises(EvidenceError):
            safe_command("python3 -V", [])
        with self.assertRaises(EvidenceError):
            safe_command("python3 -V; rm -rf /", [])
        with self.assertRaises(EvidenceError):
            safe_command("wget http://x/binary", [])
        # An EXPLICIT allowlist permits only the declared tool.
        safe_command("python3 -V", ["python3"])               # ok
        with self.assertRaises(EvidenceError):
            safe_command("wget http://x", ["python3"])        # not allowlisted


# --------------------------------------------------------------------------
# Queue ordering determinism
# --------------------------------------------------------------------------
class QueueOrdering(unittest.TestCase):
    def test_ordering(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo(Path(d))
            a = _ready_task("A", tools=[]); a.priority = 5; a.plan_order = 2
            b = _ready_task("B", tools=[]); b.priority = 5; b.plan_order = 1
            c = _ready_task("C", tools=[]); c.priority = 1
            cl = classify_all([a, b, c], _tool_reg(), root)
            q = build_ready_queue([a, b, c], cl)
            self.assertEqual(q, ["C", "B", "A"])


# --------------------------------------------------------------------------
# Checkpoint / resume
# --------------------------------------------------------------------------
class CheckpointResume(unittest.TestCase):
    def test_save_load_and_invalidate(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "state.json"
            store = StateStore(sp)
            store.load()
            store.set_state("T1", "READY")
            store.begin("T1")
            store.save(repo_head="deadbeef")

            store2 = StateStore(sp)
            store2.load()
            self.assertTrue(store2.get("T1").in_progress)
            # begin() marks the task IN_PROGRESS (correct lifecycle); the
            # persisted state reflects that until reclassification.
            self.assertEqual(store2.get("T1").state, "IN_PROGRESS")

            # recompute says T1 is now BLOCKED -> invalidate stale
            cl = {  # simulate reclassification
                "T1": M.Classification(task_id="T1", effective_state="BLOCKED")
            }
            changed = store2.invalidate_stale(cl)
            self.assertIn("T1", changed)
            self.assertEqual(store2.get("T1").state, "BLOCKED")
            self.assertFalse(store2.get("T1").in_progress)

    def test_terminal_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "state.json"
            store = StateStore(sp); store.load()
            store.set_state("T2", "PASS", validated_pass=True)
            store.save()
            store2 = StateStore(sp); store2.load()
            cl = {"T2": M.Classification(task_id="T2", effective_state="BLOCKED")}
            changed = store2.invalidate_stale(cl)
            self.assertNotIn("T2", changed)         # PASS is sticky
            self.assertTrue(store2.get("T2").validated_pass)


# --------------------------------------------------------------------------
# Evidence log
# --------------------------------------------------------------------------
class EvidenceTests(unittest.TestCase):
    def test_append_and_pass_set(self):
        with tempfile.TemporaryDirectory() as d:
            ep = Path(d) / "ev.jsonl"
            log = EvidenceLog(ep)
            log.append(EvidenceRecord("E1", "T1", "python3 -V", exit_status=0,
                                      result="PASS"))
            log.append(EvidenceRecord("E2", "T2", "false", exit_status=1,
                                      result="FAIL", failure_class="TEST"))
            self.assertEqual(log.validated_pass(), {"T1"})
            self.assertEqual(len(log.for_task("T2")), 1)


# --------------------------------------------------------------------------
# Manifest schema validation
# --------------------------------------------------------------------------
class ManifestSchema(unittest.TestCase):
    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            mp = Path(d) / "m.json"
            mp.write_text(json.dumps({
                "schema_version": "1.0", "project": "x", "tool_registry": {},
                "tasks": [
                    {"task_id": "DUP", "title": "a", "description": "d",
                     "source_authority": [{"doc": "x.md"}], "requirement_refs": ["r"],
                     "validation_commands": [{"id": "v", "command": "python3 -V"}],
                     "acceptance_criteria": [{"id": "a", "criterion": "c"}]},
                    {"task_id": "DUP", "title": "b", "description": "d",
                     "source_authority": [{"doc": "x.md"}], "requirement_refs": ["r"],
                     "validation_commands": [{"id": "v", "command": "python3 -V"}],
                     "acceptance_criteria": [{"id": "a", "criterion": "c"}]},
                ]
            }), encoding="utf-8")
            with self.assertRaises(ManifestError):
                load_manifest(mp)

    def test_unknown_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            mp = Path(d) / "m.json"
            mp.write_text(json.dumps({
                "schema_version": "1.0", "project": "x", "tool_registry": {},
                "tasks": [
                    {"task_id": "T", "title": "a", "description": "d",
                     "source_authority": [{"doc": "x.md"}], "requirement_refs": ["r"],
                     "validation_commands": [{"id": "v", "command": "python3 -V"}],
                     "acceptance_criteria": [{"id": "a", "criterion": "c"}],
                     "dependency_refs": [{"ref": "NOPE"}]},
                ]
            }), encoding="utf-8")
            with self.assertRaises(ManifestError):
                load_manifest(mp)


# --------------------------------------------------------------------------
# Integration — real manifest dry-run preserves documented blockers, READY=0
# --------------------------------------------------------------------------
class RealManifestIntegration(unittest.TestCase):
    def setUp(self):
        self.manifest = REPO_ROOT / "docs/implementation/implementation-plan.json"
        self.assume = self.manifest.is_file()

    def test_dry_run_ready_zero(self):
        if not self.assume:
            self.skipTest("seed manifest absent")
        ctrl = Controller(
            manifest_path=str(self.manifest), repo_root=str(REPO_ROOT),
            state_path=str(REPO_ROOT / ".impl_controller/_test_state.json"),
            evidence_path=str(REPO_ROOT / ".impl_controller/_test_evidence.jsonl"))
        res = ctrl.run(dry_run=True)
        self.assertEqual(res.ready_queue, [])
        self.assertEqual(res.frontier, "PAUSED")
        cl = res.classifications
        self.assertEqual(cl["RED-LEX-001"].effective_state, "BLOCKED")
        self.assertEqual(cl["RED-LEX-001"].blocker_class, "TOOLCHAIN")
        for r in ("TOOLCHAIN", "ARCHITECTURE", "PROVISIONING", "AUTHORIZATION"):
            self.assertIn(r, cl["RED-LEX-001"].reasons)
        self.assertEqual(cl["LIBRED-001"].effective_state, "BLOCKED")
        self.assertEqual(cl["LIBRED-001"].blocker_class, "DEPENDENCY")
        self.assertIn("TOOLCHAIN", cl["LIBRED-001"].reasons)
        self.assertEqual(cl["HASH-001"].effective_state, "BLOCKED")
        self.assertIn("INCOMPLETE_SPECIFICATION", cl["HASH-001"].reasons)
        self.assertIn("TOOLCHAIN", cl["HASH-001"].reasons)
        self.assertEqual(cl["RFC0075-001"].effective_state, "BLOCKED")
        self.assertIn("SPECIFICATION_CONFLICT", cl["RFC0075-001"].reasons)
        self.assertIn("INCOMPLETE_SPECIFICATION", cl["RFC0075-001"].reasons)


if __name__ == "__main__":
    unittest.main(verbosity=2)
