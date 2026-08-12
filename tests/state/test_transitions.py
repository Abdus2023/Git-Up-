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
