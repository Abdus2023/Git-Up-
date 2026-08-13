"""Spec 02/06: declared repository binding and evidence context match."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from git_up.authorize import evidence_bound_to_context, task_may_pass
from git_up.contract import load_contract
from git_up.errors import ContractError
from git_up.identity import contract_identity_for, provenance_context
from tests.support import (
    contract_doc, init_repo, make_controller, minimal_task, seed_worktree, write,
)


class RepositoryBindingTests(unittest.TestCase):
    def test_declared_revision_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["repository"] = {"revision": "deadbeef" * 5}
            seed_worktree(repo, doc)
            with self.assertRaises(ContractError) as ctx:
                make_controller(repo).run(dry_run=True)
            self.assertIn("repository binding", str(ctx.exception))

    def test_declared_identity_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["repository"] = {"identity": "repo-not-this-worktree"}
            seed_worktree(repo, doc)
            with self.assertRaises(ContractError) as ctx:
                make_controller(repo).run(dry_run=True)
            self.assertIn("repository.identity", str(ctx.exception))

    def test_dirty_state_clean_rejects_dirt(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["repository"] = {"dirty_state": "clean"}
            seed_worktree(repo, doc)
            write(repo / "extra.txt", "dirt\n")
            with self.assertRaises(ContractError) as ctx:
                make_controller(repo).run(dry_run=True)
            self.assertIn("dirty_state", str(ctx.exception))

    def test_unknown_dirty_state_refused(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["repository"] = {"dirty_state": "somewhat-clean"}
            seed_worktree(repo, doc)
            with self.assertRaises(ContractError) as ctx:
                make_controller(repo).run(dry_run=True)
            self.assertIn("unknown repository.dirty_state", str(ctx.exception))

    def test_evidence_head_field_must_match_context(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            seed_worktree(repo)
            r1 = make_controller(repo).run(dry_run=False, execute=True)
            self.assertEqual(r1.result, "PASS", r1.errors)
            contract = load_contract(repo / "git-up.contract.json")
            ctx = provenance_context(repo, contract, create_identity=False)
            evs = make_controller(repo).log.verified_records()
            self.assertTrue(evs)
            self.assertTrue(evidence_bound_to_context(evs[0], ctx))
            forged = dict(evs[0])
            forged["head"] = "0" * 40
            self.assertFalse(evidence_bound_to_context(forged, ctx))
            task = contract.tasks[0]
            cid = contract_identity_for(task, set(), ctx)
            self.assertFalse(
                task_may_pass(task, cid, [forged], set(), ctx, repo)
            )

    def test_unknown_dependency_is_named(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            task = minimal_task(
                dependencies=[{"ref": "T-MISSING", "required_state": "PASS"}],
            )
            seed_worktree(repo, contract_doc([task]))
            res = make_controller(repo).run(dry_run=True)
            by = {c["task_id"]: c for c in res.report["classifications"]}
            self.assertEqual(by["T1"]["effective_state"], "BLOCKED")
            self.assertTrue(
                any("not a declared task" in d for d in by["T1"]["detail"])
            )

    def test_malformed_expected_outputs_are_contract_error(self):
        with tempfile.TemporaryDirectory() as td:
            repo = init_repo(Path(td))
            doc = contract_doc()
            doc["tasks"][0]["expected_outputs"] = ["not-an-object"]
            path = repo / "git-up.contract.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ContractError) as ctx:
                load_contract(path)
            self.assertIn("expected_outputs", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
