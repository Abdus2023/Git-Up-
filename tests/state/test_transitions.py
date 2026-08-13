"""I-PASS-1 — PASS only from VALIDATING."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.checkpoint import StateStore
from git_up.errors import TransitionError
from git_up.model import TaskState


class TransitionTests(unittest.TestCase):
    def test_I_PASS_1_ready_to_pass_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.json")
            store.load()
            store.transition("T1", TaskState.READY.value)
            with self.assertRaises(TransitionError):
                store.transition("T1", TaskState.PASS.value)

    def test_in_progress_to_pass_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.json")
            store.load()
            store.transition("T1", TaskState.READY.value)
            store.begin("T1")
            with self.assertRaises(TransitionError):
                store.finish_pass("T1", "EVID-X")

    def test_record_reconstructed_pass_walks_validating(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.json")
            store.load()
            store.transition("T1", TaskState.READY.value)
            store.begin("T1")
            store.record_reconstructed_pass("T1", "EVID-R")
            self.assertEqual(store.get("T1").state, TaskState.PASS.value)
            self.assertTrue(store.get("T1").validated_pass)
            self.assertFalse(store.get("T1").in_progress)

    def test_in_progress_to_blocked_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.json")
            store.load()
            store.transition("T1", TaskState.READY.value)
            store.begin("T1")
            store.finish_blocked("T1", "EVID-B")
            self.assertEqual(store.get("T1").state, TaskState.BLOCKED.value)
            self.assertFalse(store.get("T1").in_progress)
            self.assertIn("EVID-B", store.get("T1").evidence_refs)

    def test_validating_to_blocked_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.json")
            store.load()
            store.transition("T1", TaskState.READY.value)
            store.begin("T1")
            store.enter_validating("T1")
            with self.assertRaises(TransitionError):
                store.finish_blocked("T1", "EVID-B")

    def test_validating_to_pass_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.json")
            store.load()
            store.transition("T1", TaskState.READY.value)
            store.begin("T1")
            store.enter_validating("T1")
            store.finish_pass("T1", "EVID-X")
            self.assertEqual(store.get("T1").state, TaskState.PASS.value)


if __name__ == "__main__":
    unittest.main()
