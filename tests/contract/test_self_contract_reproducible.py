"""Committed self-contract must match emit(self-plan) (ADR-0021)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import emit_contract_file
from git_up.contract import load_contract
from git_up.diff import diff_contracts
from git_up.identity import source_identity
from tests.support import ROOT


class SelfContractReproTests(unittest.TestCase):
    def test_committed_matches_emit_self_plan(self):
        plan = ROOT / "docs" / "plans" / "self.md"
        committed = ROOT / "git-up.contract.json"
        self.assertTrue(plan.is_file())
        self.assertTrue(committed.is_file())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "emitted.json"
            emit_contract_file(plan, out)
            a = load_contract(committed)
            b = load_contract(out)
            self.assertEqual(source_identity(a), source_identity(b))
            delta = diff_contracts(a, b)
            self.assertTrue(delta["identical"], delta)


if __name__ == "__main__":
    unittest.main()
