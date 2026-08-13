"""contract diff compares identity, not 'who looks greener' (ADR-0019)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.adapter import PLAN_SCHEMA, emit_contract
from git_up.cli import main
from git_up.contract import load_contract
from git_up.diff import diff_contracts
from tests.support import init_repo, write


def _plan(title="t", extra_task=None):
    tasks = [{"id": "T1", "title": title, "commands": [
        {"id": "v1", "command": "python3 -c pass", "expected_exit": 0},
    ]}]
    if extra_task:
        tasks.append(extra_task)
    return {
        "schema_version": PLAN_SCHEMA,
        "tools": [{"id": "python3", "available": True, "binary": "python3"}],
        "tasks": tasks,
    }


class DiffTests(unittest.TestCase):
    def _write(self, repo, name, plan):
        path = repo / name
        write(path, json.dumps(emit_contract(plan)))
        return path

    def test_identical(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            a = self._write(repo, "a.json", _plan())
            b = self._write(repo, "b.json", _plan())
            d = diff_contracts(load_contract(a), load_contract(b))
            self.assertTrue(d["identical"])
            self.assertEqual(d["tasks_changed"], [])

    def test_title_change_listed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            a = self._write(repo, "a.json", _plan("one"))
            b = self._write(repo, "b.json", _plan("two"))
            d = diff_contracts(load_contract(a), load_contract(b))
            self.assertFalse(d["identical"])
            self.assertEqual(d["tasks_changed"][0]["task_id"], "T1")
            self.assertIn("title", d["tasks_changed"][0]["fields"])

    def test_task_added(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            a = self._write(repo, "a.json", _plan())
            b = self._write(repo, "b.json", _plan(extra_task={"id": "T2"}))
            d = diff_contracts(load_contract(a), load_contract(b))
            self.assertEqual(d["tasks_added"], ["T2"])

    def test_cli_diff(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            a = self._write(repo, "a.json", _plan("one"))
            b = self._write(repo, "b.json", _plan("two"))
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main(["contract", "diff", str(a), str(b)])
            finally:
                sys.stdout = old
            data = json.loads(buf.getvalue())
            self.assertEqual(code, 0, data)
            self.assertFalse(data.get("identical"))
            self.assertNotIn("PASS authorization", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
