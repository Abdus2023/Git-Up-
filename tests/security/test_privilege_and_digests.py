"""Spec 16 §8 sudo ban; load-time digest/command fail-closed."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.cli import main
from git_up.contract import load_contract
from git_up.errors import ContractError
from tests.support import (
    contract_doc, init_repo, make_controller, seed_worktree,
)


class PrivilegeAndDigestTests(unittest.TestCase):
    def test_empty_command_is_contract_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["tasks"][0]["validation_commands"][0]["command"] = "   "
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(p)
            self.assertIn("empty command", str(ctx.exception))

    def test_expected_output_digest_must_be_sha256(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["tasks"][0]["expected_outputs"] = [
                {"path": "src/out.txt", "sha256": "deadbeef"},
            ]
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(p)
            self.assertIn("64 hex", str(ctx.exception))

    def test_evidence_annotates_context_binding(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            r = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(r.result, "PASS", r.errors)
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main([
                    "--contract", str(repo / "git-up.contract.json"),
                    "--repo-root", str(repo),
                    "evidence",
                ])
            finally:
                sys.stdout = old
            data = json.loads(buf.getvalue())
            self.assertEqual(code, 0, data)
            trusted = data.get("trusted") or []
            self.assertTrue(trusted)
            self.assertTrue(trusted[0].get("bound_to_current_context"))


if __name__ == "__main__":
    unittest.main()
