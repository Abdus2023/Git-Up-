"""Compare two contracts by identity. Derived; never authorizes PASS."""

from __future__ import annotations

from .identity import _task_canon, source_identity


def _summary(contract) -> dict:
    prov = contract.provenance or {}
    tasks = {t.id: _task_canon(t) for t in contract.tasks}
    return {
        "document_identity": source_identity(contract),
        "plan_identity": str(prov.get("source_identity") or ""),
        "producer": str(prov.get("producer") or ""),
        "parent_contracts": list(prov.get("parent_contracts") or []),
        "task_ids": sorted(tasks),
        "tasks": tasks,
    }


def _changed_fields(old: dict, new: dict) -> list:
    keys = sorted(set(old) | set(new))
    return [k for k in keys if old.get(k) != new.get(k)]


def diff_contracts(left, right) -> dict:
    a, b = _summary(left), _summary(right)
    a_ids, b_ids = set(a["task_ids"]), set(b["task_ids"])
    changed = []
    for tid in sorted(a_ids & b_ids):
        fields = _changed_fields(a["tasks"][tid], b["tasks"][tid])
        if fields:
            changed.append({"task_id": tid, "fields": fields})
    return {
        "identical": a["document_identity"] == b["document_identity"],
        "document_identity": {
            "a": a["document_identity"],
            "b": b["document_identity"],
        },
        "plan_identity": {"a": a["plan_identity"], "b": b["plan_identity"]},
        "producer": {"a": a["producer"], "b": b["producer"]},
        "parent_contracts": {
            "a": a["parent_contracts"],
            "b": b["parent_contracts"],
        },
        "tasks_added": sorted(b_ids - a_ids),
        "tasks_removed": sorted(a_ids - b_ids),
        "tasks_changed": changed,
    }
