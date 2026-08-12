"""Fail-closed error types."""

from __future__ import annotations


class GitUpError(Exception):
    """Base error. Never used to paper over ambiguity."""


class ContractError(GitUpError):
    pass


class SafetyError(GitUpError):
    pass


class LockAcquisitionError(GitUpError):
    pass


class EvidenceError(GitUpError):
    pass


class TransitionError(GitUpError):
    pass


class RepositoryError(GitUpError):
    pass
