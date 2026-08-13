"""Unknown schema and insufficient definition fail closed."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.contract import load_contract
from git_up.errors import ContractError
from tests.support import contract_doc, init_repo, seed_worktree, write


class SchemaTests(unittest.TestCase):
    def test_unknown_schema_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["schema_version"] = "nope"
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError):
                load_contract(p)

    def test_duplicate_task_id(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["tasks"].append(dict(doc["tasks"][0]))
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError):
                load_contract(p)
