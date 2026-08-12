"""Spec 05: validation command is argv-or-string."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import PLAN_SCHEMA, emit_contract
from git_up.contract import load_contract
from git_up.errors import ContractError
from git_up.identity import command_identity
from tests.support import contract_doc, init_repo, make_controller, seed_worktree


class CommandArgvTests(unittest.TestCase):
    def test_argv_list_loads_and_matches_string_identity(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            as_string = contract_doc()
            as_argv = contract_doc()
            as_argv["tasks"][0]["validation_commands"][0]["command"] = [
                "python3", "-c", "pass",
            ]
            p_str = repo / "string.json"
            p_argv = repo / "argv.json"
            p_str.write_text(json.dumps(as_string), encoding="utf-8")
            p_argv.write_text(json.dumps(as_argv), encoding="utf-8")
            a = load_contract(p_str)
            b = load_contract(p_argv)
            self.assertEqual(a.tasks[0].validation_commands[0].command, "python3 -c pass")
            self.assertEqual(
                command_identity(a.tasks[0].validation_commands[0]),
                command_identity(b.tasks[0].validation_commands[0]),
            )
            # Document identity differs by other fields only if command
            # canonical form differs — it must not.
            seed_worktree(repo, as_argv)
            loaded = load_contract(repo / "git-up.contract.json")
            self.assertEqual(
                loaded.tasks[0].validation_commands[0].command,
                "python3 -c pass",
            )

    def test_argv_executes(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["tasks"][0]["validation_commands"][0]["command"] = [
                "python3", "-c", "pass",
            ]
            seed_worktree(repo, doc)
            res = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(res.result, "PASS", res.errors)

    def test_non_string_argv_token_is_contract_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["tasks"][0]["validation_commands"][0]["command"] = ["python3", 1]
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(p)
            self.assertIn("argv[1]", str(ctx.exception))

    def test_command_must_not_be_a_number(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            doc = contract_doc()
            doc["tasks"][0]["validation_commands"][0]["command"] = 42
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(p)
            self.assertIn("string or argv", str(ctx.exception))

    def test_adapter_canonicalizes_argv(self):
        plan = {
            "schema_version": PLAN_SCHEMA,
            "tasks": [{
                "id": "T1",
                "commands": [{
                    "id": "v1",
                    "command": ["python3", "-c", "pass"],
                    "expected_exit": 0,
                }],
            }],
        }
        doc = emit_contract(plan)
        self.assertEqual(
            doc["tasks"][0]["validation_commands"][0]["command"],
            "python3 -c pass",
        )


if __name__ == "__main__":
    unittest.main()
