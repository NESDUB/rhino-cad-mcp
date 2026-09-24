#!/usr/bin/env python3
"""
Fixture-based tests for .bridge/bridge_cli.py Phase-20 provenance and
multi-pass lineage enforcement.

All tests use temporary Git repositories built from scratch — no live Rhino,
no network access.  Run with:

    python3 .bridge/tests/test_bridge_cli.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

# ---------------------------------------------------------------------------
# Load bridge_cli from the sibling directory without installing it.
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).resolve().parent
_BRIDGE_CLI = _HERE.parent / "bridge_cli.py"

spec = importlib.util.spec_from_file_location("bridge_cli", _BRIDGE_CLI)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# Helpers to build minimal fixture Git repositories
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _git_ok(args: list[str], cwd: str) -> str:
    r = _git(args, cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git {args} failed:\n{r.stderr}")
    return r.stdout.strip()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(path: pathlib.Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)


class TempRepo:
    """
    Minimal bare Git repo inside a tempdir.  Provides helpers to:
      - stage and commit files
      - obtain commit SHAs
    """

    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._td.name)
        _git_ok(["init", "-b", "main"], str(self.root))
        _git_ok(["config", "user.email", "test@test.invalid"], str(self.root))
        _git_ok(["config", "user.name", "Test"], str(self.root))

    def write(self, rel: str, content: str | bytes) -> None:
        _write(self.root / rel, content)

    def add(self, *rels: str) -> None:
        _git_ok(["add"] + list(rels), str(self.root))

    def commit(self, msg: str = "c") -> str:
        _git_ok(["commit", "--allow-empty", "-m", msg], str(self.root))
        return _git_ok(["rev-parse", "HEAD"], str(self.root))

    def cleanup(self):
        self._td.cleanup()


# Minimal valid protocol stub needed by bridge_cli internal functions
_PROTOCOL_STUB = json.dumps({"protocol_version": "0.3"})

_RHINO_CONTENT = b"# rhino stub\npass\n"
_RHINO_SHA = _sha256(_RHINO_CONTENT)


def _base_request(task_id: str, branch: str = None) -> dict:
    if branch is None:
        branch = f"operator/{task_id}"
    return {
        "protocol_version": "0.3",
        "task_id": task_id,
        "status": "queued",
        "controller": "chatgpt-web",
        "challenge": "TEST-CHALLENGE",
        "objective": "test",
        "operator_branch": branch,
        "instructions": ["test"],
        "expected_outputs": ["test"],
        "constraints": ["test"],
    }


def _base_report(task_id: str, base: str, result: str, branch: str = None) -> dict:
    if branch is None:
        branch = f"operator/{task_id}"
    return {
        "protocol_version": "0.3",
        "task_id": task_id,
        "status": "complete",
        "operator": "claude",
        "ack": "ACK",
        "base_commit": base,
        "result_commit": result,
        "branch": branch,
        "summary": "done",
        "files_changed": [],
        "tests": "pass",
        "blockers": [],
        "notes_for_controller": "",
    }


def _base_manifest(task_id: str, sha256: str = None, **extras) -> dict:
    if sha256 is None:
        sha256 = _RHINO_SHA
    m = {
        "payload_version": "1",
        "task_id": task_id,
        "author_role": "controller",
        "authoring_model": "chatgpt-web",
        "payload_type": "rhino_run",
        "python_compatibility": "3.9",
        "execution_method": "bridge.execute",
        "operation_name": "test_op",
        "sha256": sha256,
        "target_document_required": False,
        "local_modeling_authorized": False,
    }
    m.update(extras)
    return m


def _base_pass_eval(task_id: str, run_id: str, pass_index: int, pass_kind: str,
                    sha256: str = None) -> dict:
    if sha256 is None:
        sha256 = _RHINO_SHA
    return {
        "template_version": "1",
        "task_id": task_id,
        "modeling_run_id": run_id,
        "pass_index": pass_index,
        "pass_kind": pass_kind,
        "executed_payload_sha256": sha256,
        "execution_utc": "2026-01-01T00:00:00Z",
        "local_modeling_used": False,
        "local_modeling_authorized": False,
        "payload_modified_by_operator": False,
        "provenance_check": "pass",
        "operator_recommendation_scope": "evidence_only",
    }


# ---------------------------------------------------------------------------
# Patching helper: redirect bridge_cli's ROOT to a temp repo
# ---------------------------------------------------------------------------

class BridgeFacade:
    """
    Wraps bridge_cli functions with ROOT patched to a TempRepo.
    """

    def __init__(self, repo: TempRepo):
        self.repo = repo
        self._orig_root = _mod.ROOT
        self._orig_bridge = _mod.BRIDGE
        self._orig_requests = _mod.REQUESTS
        self._orig_reports = _mod.REPORTS
        self._orig_payloads = _mod.PAYLOADS
        self._orig_evidence = _mod.EVIDENCE
        self._orig_protocol = _mod.PROTOCOL

    def __enter__(self):
        _mod.ROOT = self.repo.root
        _mod.BRIDGE = self.repo.root / ".bridge"
        _mod.REQUESTS = _mod.BRIDGE / "requests"
        _mod.REPORTS = _mod.BRIDGE / "reports"
        _mod.PAYLOADS = _mod.BRIDGE / "payloads"
        _mod.EVIDENCE = _mod.BRIDGE / "evidence"
        _mod.PROTOCOL = _mod.BRIDGE / "protocol.json"
        return self

    def __exit__(self, *_):
        _mod.ROOT = self._orig_root
        _mod.BRIDGE = self._orig_bridge
        _mod.REQUESTS = self._orig_requests
        _mod.REPORTS = self._orig_reports
        _mod.PAYLOADS = self._orig_payloads
        _mod.EVIDENCE = self._orig_evidence
        _mod.PROTOCOL = self._orig_protocol

    def verify_ok(self, task_id: str):
        """Call cmd_verify_report and expect it to succeed."""
        _mod.cmd_verify_report(task_id)

    def verify_fail(self, task_id: str, fragment: str):
        """Call cmd_verify_report and expect SystemExit containing fragment."""
        with self.assertRaises(SystemExit) as ctx:
            _mod.cmd_verify_report(task_id)
        msg = str(ctx.exception)
        if fragment not in msg:
            raise AssertionError(
                f"Expected SystemExit containing {fragment!r}, got: {msg!r}"
            )

    def assertRaises(self, exc):
        import contextlib

        class _CM:
            def __init__(self_):
                self_.exception = None

            def __enter__(self_):
                return self_

            def __exit__(self_, et, ev, tb):
                if et is None:
                    raise AssertionError(f"Expected {exc} but no exception was raised")
                if not issubclass(et, exc):
                    return False  # re-raise
                self_.exception = ev
                return True  # suppress

        return _CM()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestNonPayloadBackwardCompat(unittest.TestCase):
    """Non-payload tasks (no manifest) must pass without provenance checks."""

    def test_non_payload_passes(self):
        repo = TempRepo()
        try:
            task_id = "task-nonpayload"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            repo.add(".")
            base = repo.commit("base")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, base)))
            repo.add(".")
            result = repo.commit("work")

            # Update report with actual result commit
            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo) as f:
                # Should not raise
                _mod.cmd_verify_report(task_id)
        finally:
            repo.cleanup()


class TestValidFoundationPass(unittest.TestCase):
    """Valid foundation pass (pass_index=1) with correct provenance must pass."""

    def test_valid_foundation(self):
        repo = TempRepo()
        try:
            task_id = "model001-pass1"
            run_id = "run-abc"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            manifest = _base_manifest(task_id, modeling_run_id=run_id,
                                      pass_index=1, pass_kind="foundation")
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest))
            repo.add(".")
            base = repo.commit("base")

            # Write pass-evaluation
            ev = _base_pass_eval(task_id, run_id, 1, "foundation")
            repo.write(f".bridge/evidence/{task_id}/pass-evaluation.json",
                       json.dumps(ev))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo) as f:
                _mod.cmd_verify_report(task_id)
        finally:
            repo.cleanup()


class TestValidCorrectionLineage(unittest.TestCase):
    """Valid pass_index=2 correction with correct parent lineage must pass."""

    def test_valid_correction(self):
        repo = TempRepo()
        try:
            run_id = "run-abc"
            parent_id = "model001-pass1"
            child_id = "model001-pass2"

            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)

            # --- parent pass already merged into main ---
            parent_manifest = _base_manifest(parent_id, modeling_run_id=run_id,
                                             pass_index=1, pass_kind="foundation")
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))
            repo.write(f".bridge/requests/{parent_id}.json",
                       json.dumps(_base_request(parent_id)))
            repo.add(".")
            parent_base = repo.commit("parent-base")

            # parent result commit
            parent_ev = _base_pass_eval(parent_id, run_id, 1, "foundation")
            repo.write(f".bridge/evidence/{parent_id}/pass-evaluation.json",
                       json.dumps(parent_ev))
            repo.add(".")
            parent_result = repo.commit("parent-work")

            repo.write(f".bridge/reports/{parent_id}.json",
                       json.dumps(_base_report(parent_id, parent_base, parent_result)))
            repo.add(".")
            repo.commit("parent-receipt")

            # --- child pass (correction) ---
            child_rhino = b"# correction pass\npass\n"
            child_sha = _sha256(child_rhino)
            repo.write(f".bridge/requests/{child_id}.json",
                       json.dumps(_base_request(child_id)))
            child_manifest = _base_manifest(
                child_id, sha256=child_sha,
                modeling_run_id=run_id,
                pass_index=2, pass_kind="correction",
                parent_task_id=parent_id,
                parent_payload_sha256=_RHINO_SHA,
                parent_result_commit=parent_result,
            )
            repo.write(f".bridge/payloads/{child_id}/rhino.py", child_rhino)
            repo.write(f".bridge/payloads/{child_id}/manifest.json",
                       json.dumps(child_manifest))
            repo.add(".")
            base = repo.commit("child-base")

            child_ev = _base_pass_eval(child_id, run_id, 2, "correction", sha256=child_sha)
            repo.write(f".bridge/evidence/{child_id}/pass-evaluation.json",
                       json.dumps(child_ev))
            repo.add(".")
            result = repo.commit("child-work")

            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))
            repo.add(".")
            repo.commit("child-receipt")

            with BridgeFacade(repo):
                _mod.cmd_verify_report(child_id)
        finally:
            repo.cleanup()


class TestSHAMismatch(unittest.TestCase):
    """Manifest sha256 that doesn't match actual rhino.py must fail."""

    def test_sha_mismatch(self):
        repo = TempRepo()
        try:
            task_id = "task-shamismatch"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            manifest = _base_manifest(task_id, sha256="a" * 64)  # wrong SHA
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest))
            repo.add(".")
            base = repo.commit("base")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, base)))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo) as f:
                try:
                    _mod.cmd_verify_report(task_id)
                    self.fail("Expected SystemExit for SHA mismatch")
                except SystemExit as e:
                    self.assertIn("PROVENANCE_ERROR", str(e))
                    self.assertIn("SHA-256 mismatch", str(e))
        finally:
            repo.cleanup()


class TestOperatorPayloadModification(unittest.TestCase):
    """Operator modifying rhino.py without authorization must fail."""

    def test_unauthorized_modification(self):
        repo = TempRepo()
        try:
            task_id = "task-unauthorized"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            manifest = _base_manifest(task_id)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest))
            repo.add(".")
            base = repo.commit("base")

            # Operator modifies rhino.py (not authorized)
            modified = b"# UNAUTHORIZED MODIFICATION\npass\n"
            modified_sha = _sha256(modified)
            # Also update manifest to match modified SHA (so SHA check passes
            # but modification detection fails)
            manifest2 = _base_manifest(task_id, sha256=modified_sha)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", modified)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest2))
            repo.add(".")
            result = repo.commit("operator-modified")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                try:
                    _mod.cmd_verify_report(task_id)
                    self.fail("Expected SystemExit for unauthorized modification")
                except SystemExit as e:
                    self.assertIn("UNAUTHORIZED_LOCAL_MODELING", str(e))
        finally:
            repo.cleanup()


class TestMissingParentReport(unittest.TestCase):
    """pass_index=2 with parent report absent from base_commit must fail."""

    def test_missing_parent_report(self):
        repo = TempRepo()
        try:
            run_id = "run-xyz"
            parent_id = "pass1"
            child_id = "pass2"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{child_id}.json",
                       json.dumps(_base_request(child_id)))

            parent_manifest = _base_manifest(parent_id, modeling_run_id=run_id,
                                             pass_index=1, pass_kind="foundation")
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))
            repo.add(".")
            base = repo.commit("base-no-parent-report")

            child_manifest = _base_manifest(
                child_id,
                modeling_run_id=run_id,
                pass_index=2, pass_kind="correction",
                parent_task_id=parent_id,
                parent_payload_sha256=_RHINO_SHA,
                parent_result_commit="a" * 40,
            )
            repo.write(f".bridge/payloads/{child_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{child_id}/manifest.json",
                       json.dumps(child_manifest))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                try:
                    _mod.cmd_verify_report(child_id)
                    self.fail("Expected SystemExit for missing parent report")
                except SystemExit as e:
                    self.assertIn("LINEAGE_ERROR", str(e))
                    self.assertIn("parent report", str(e))
        finally:
            repo.cleanup()


class TestWrongParentResultCommit(unittest.TestCase):
    """Parent report result_commit that doesn't match manifest must fail."""

    def test_wrong_parent_result_commit(self):
        repo = TempRepo()
        try:
            run_id = "run-xyz"
            parent_id = "ppass1"
            child_id = "ppass2"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{child_id}.json",
                       json.dumps(_base_request(child_id)))

            parent_manifest = _base_manifest(parent_id, modeling_run_id=run_id,
                                             pass_index=1, pass_kind="foundation")
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))
            real_parent_result = "b" * 40
            repo.write(f".bridge/reports/{parent_id}.json",
                       json.dumps(_base_report(parent_id, "a" * 40, real_parent_result)))
            repo.add(".")
            base = repo.commit("base")

            # child claims wrong parent_result_commit
            wrong_result = "c" * 40
            child_manifest = _base_manifest(
                child_id,
                modeling_run_id=run_id,
                pass_index=2, pass_kind="correction",
                parent_task_id=parent_id,
                parent_payload_sha256=_RHINO_SHA,
                parent_result_commit=wrong_result,
            )
            repo.write(f".bridge/payloads/{child_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{child_id}/manifest.json",
                       json.dumps(child_manifest))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                try:
                    _mod.cmd_verify_report(child_id)
                    self.fail("Expected SystemExit for wrong parent result commit")
                except SystemExit as e:
                    self.assertIn("LINEAGE_ERROR", str(e))
                    self.assertIn("result_commit", str(e))
        finally:
            repo.cleanup()


class TestWrongModelingRunId(unittest.TestCase):
    """Parent with different modeling_run_id must fail."""

    def test_wrong_run_id(self):
        repo = TempRepo()
        try:
            parent_id = "qpass1"
            child_id = "qpass2"
            parent_run = "run-parent"
            child_run = "run-child-different"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{child_id}.json",
                       json.dumps(_base_request(child_id)))

            parent_manifest = _base_manifest(parent_id, modeling_run_id=parent_run,
                                             pass_index=1, pass_kind="foundation")
            parent_result_sha = "d" * 40
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))
            repo.write(f".bridge/reports/{parent_id}.json",
                       json.dumps(_base_report(parent_id, "a" * 40, parent_result_sha)))
            repo.add(".")
            base = repo.commit("base")

            child_manifest = _base_manifest(
                child_id,
                modeling_run_id=child_run,  # different run ID!
                pass_index=2, pass_kind="correction",
                parent_task_id=parent_id,
                parent_payload_sha256=_RHINO_SHA,
                parent_result_commit=parent_result_sha,
            )
            repo.write(f".bridge/payloads/{child_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{child_id}/manifest.json",
                       json.dumps(child_manifest))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                try:
                    _mod.cmd_verify_report(child_id)
                    self.fail("Expected SystemExit for run_id mismatch")
                except SystemExit as e:
                    self.assertIn("LINEAGE_ERROR", str(e))
                    self.assertIn("modeling_run_id", str(e))
        finally:
            repo.cleanup()


class TestNonSequentialPassIndex(unittest.TestCase):
    """pass_index jumping by 2 (not sequential) must fail."""

    def test_nonsequential_index(self):
        repo = TempRepo()
        try:
            run_id = "run-seq"
            parent_id = "spass1"
            child_id = "spass3"  # gap: skips 2
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{child_id}.json",
                       json.dumps(_base_request(child_id)))

            parent_manifest = _base_manifest(parent_id, modeling_run_id=run_id,
                                             pass_index=1, pass_kind="foundation")
            parent_result = "e" * 40
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))
            repo.write(f".bridge/reports/{parent_id}.json",
                       json.dumps(_base_report(parent_id, "a" * 40, parent_result)))
            repo.add(".")
            base = repo.commit("base")

            child_manifest = _base_manifest(
                child_id,
                modeling_run_id=run_id,
                pass_index=3,  # should be 2
                pass_kind="correction",
                parent_task_id=parent_id,
                parent_payload_sha256=_RHINO_SHA,
                parent_result_commit=parent_result,
            )
            repo.write(f".bridge/payloads/{child_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{child_id}/manifest.json",
                       json.dumps(child_manifest))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                try:
                    _mod.cmd_verify_report(child_id)
                    self.fail("Expected SystemExit for non-sequential pass_index")
                except SystemExit as e:
                    self.assertIn("LINEAGE_ERROR", str(e))
                    self.assertIn("pass_index", str(e))
        finally:
            repo.cleanup()


class TestMissingPassEvaluation(unittest.TestCase):
    """Multi-pass task without pass-evaluation.json must fail."""

    def test_missing_eval(self):
        repo = TempRepo()
        try:
            task_id = "eval-missing"
            run_id = "run-eval"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            manifest = _base_manifest(task_id, modeling_run_id=run_id,
                                      pass_index=1, pass_kind="foundation")
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest))
            repo.add(".")
            base = repo.commit("base")

            # Work commit — NO pass-evaluation.json
            repo.write(f".bridge/evidence/{task_id}/other.txt", "irrelevant")
            repo.add(".")
            result = repo.commit("work-no-eval")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                try:
                    _mod.cmd_verify_report(task_id)
                    self.fail("Expected SystemExit for missing pass-evaluation")
                except SystemExit as e:
                    self.assertIn("PASS_EVAL_ERROR", str(e))
                    self.assertIn("pass-evaluation.json", str(e))
        finally:
            repo.cleanup()


class TestWrongExecutedSHA(unittest.TestCase):
    """pass-evaluation.json with wrong executed_payload_sha256 must fail."""

    def test_wrong_executed_sha(self):
        repo = TempRepo()
        try:
            task_id = "eval-wrongsha"
            run_id = "run-eval2"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            manifest = _base_manifest(task_id, modeling_run_id=run_id,
                                      pass_index=1, pass_kind="single_pass")
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest))
            repo.add(".")
            base = repo.commit("base")

            ev = _base_pass_eval(task_id, run_id, 1, "single_pass",
                                 sha256="f" * 64)  # wrong SHA
            repo.write(f".bridge/evidence/{task_id}/pass-evaluation.json",
                       json.dumps(ev))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                try:
                    _mod.cmd_verify_report(task_id)
                    self.fail("Expected SystemExit for wrong executed SHA")
                except SystemExit as e:
                    self.assertIn("PASS_EVAL_ERROR", str(e))
                    self.assertIn("executed_payload_sha256", str(e))
        finally:
            repo.cleanup()


class TestWrongRecommendationScope(unittest.TestCase):
    """pass-evaluation with operator_recommendation_scope != 'evidence_only' must fail."""

    def test_wrong_scope(self):
        repo = TempRepo()
        try:
            task_id = "eval-scope"
            run_id = "run-scope"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            manifest = _base_manifest(task_id, modeling_run_id=run_id,
                                      pass_index=1, pass_kind="foundation")
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest))
            repo.add(".")
            base = repo.commit("base")

            ev = _base_pass_eval(task_id, run_id, 1, "foundation")
            ev["operator_recommendation_scope"] = "redesign_recommended"  # WRONG
            repo.write(f".bridge/evidence/{task_id}/pass-evaluation.json",
                       json.dumps(ev))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                try:
                    _mod.cmd_verify_report(task_id)
                    self.fail("Expected SystemExit for wrong scope")
                except SystemExit as e:
                    self.assertIn("PASS_EVAL_ERROR", str(e))
                    self.assertIn("evidence_only", str(e))
        finally:
            repo.cleanup()


class TestUnauthorizedLocalModelingUsed(unittest.TestCase):
    """local_modeling_used=true without authorization must fail."""

    def test_unauthorized_local_modeling(self):
        repo = TempRepo()
        try:
            task_id = "eval-lm"
            run_id = "run-lm"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            manifest = _base_manifest(task_id, modeling_run_id=run_id,
                                      pass_index=1, pass_kind="foundation",
                                      local_modeling_authorized=False)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest))
            repo.add(".")
            base = repo.commit("base")

            ev = _base_pass_eval(task_id, run_id, 1, "foundation")
            ev["local_modeling_used"] = True  # claims unauthorized local modeling!
            repo.write(f".bridge/evidence/{task_id}/pass-evaluation.json",
                       json.dumps(ev))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                try:
                    _mod.cmd_verify_report(task_id)
                    self.fail("Expected SystemExit for unauthorized local modeling")
                except SystemExit as e:
                    self.assertIn("PASS_EVAL_ERROR", str(e))
                    self.assertIn("local_modeling_used", str(e))
        finally:
            repo.cleanup()


class TestSinglePassNonModelingBackwardCompat(unittest.TestCase):
    """Single-pass payload task without modeling_run_id skips lineage+eval checks."""

    def test_single_pass_no_run_id(self):
        repo = TempRepo()
        try:
            task_id = "task-singlepass"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            # manifest without modeling_run_id = single pass
            manifest = _base_manifest(task_id)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest))
            repo.add(".")
            base = repo.commit("base")

            # No pass-evaluation.json — should be fine for single-pass
            repo.write(f".bridge/evidence/{task_id}/notes.txt", "single pass, no eval needed")
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt")

            with BridgeFacade(repo):
                _mod.cmd_verify_report(task_id)  # must not raise
        finally:
            repo.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
