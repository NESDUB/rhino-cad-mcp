#!/usr/bin/env python3
"""
Fixture-based tests for .bridge/bridge_cli.py Phase-20 provenance and
multi-pass lineage enforcement.

All tests use temporary Git repositories built from scratch — no live Rhino,
no network access.  Run with:

    python3 .bridge/tests/test_bridge_cli.py

Lifecycle note: verify-report is designed to run BEFORE the receipt commit,
with HEAD at the work/result commit. Tests mirror that workflow: write the
report file on disk (uncommitted), call verify-report, then commit receipt.
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

def _git_ok(args: list[str], cwd: str) -> str:
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
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
    Minimal bare Git repo inside a tempdir.
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

    def head(self) -> str:
        return _git_ok(["rev-parse", "HEAD"], str(self.root))

    def cleanup(self):
        self._td.cleanup()


# Minimal protocol stub
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
# Patching helper — redirects bridge_cli's ROOT to a TempRepo
# ---------------------------------------------------------------------------

class BridgeFacade:
    def __init__(self, repo: TempRepo):
        self.repo = repo
        self._saved = {}

    def __enter__(self):
        for attr, val in [
            ("ROOT",     self.repo.root),
            ("BRIDGE",   self.repo.root / ".bridge"),
            ("REQUESTS", self.repo.root / ".bridge" / "requests"),
            ("REPORTS",  self.repo.root / ".bridge" / "reports"),
            ("PAYLOADS", self.repo.root / ".bridge" / "payloads"),
            ("EVIDENCE", self.repo.root / ".bridge" / "evidence"),
            ("PROTOCOL", self.repo.root / ".bridge" / "protocol.json"),
        ]:
            self._saved[attr] = getattr(_mod, attr)
            setattr(_mod, attr, val)
        return self

    def __exit__(self, *_):
        for attr, val in self._saved.items():
            setattr(_mod, attr, val)


def _run_verify(repo: TempRepo, task_id: str):
    """Run verify-report with ROOT patched to repo; raises SystemExit on failure."""
    with BridgeFacade(repo):
        _mod.cmd_verify_report(task_id)


def _expect_fail(repo: TempRepo, task_id: str, fragment: str):
    """Expect verify-report to raise SystemExit containing fragment."""
    try:
        _run_verify(repo, task_id)
        raise AssertionError(
            f"Expected SystemExit containing {fragment!r} but no exception was raised"
        )
    except SystemExit as e:
        msg = str(e)
        if fragment not in msg:
            raise AssertionError(
                f"Expected SystemExit containing {fragment!r}, got: {msg!r}"
            )


# ---------------------------------------------------------------------------
# Helpers for common repo setups
# ---------------------------------------------------------------------------

def _setup_nonpayload_repo(task_id: str) -> TempRepo:
    """Base → work commit (no payload). Report written but NOT committed."""
    repo = TempRepo()
    repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
    repo.write(f".bridge/requests/{task_id}.json", json.dumps(_base_request(task_id)))
    repo.add(".")
    base = repo.commit("base")
    # Work commit (some other file changed)
    repo.write(f".bridge/evidence/{task_id}/notes.txt", "done")
    repo.add(".")
    result = repo.commit("work")
    # Write report (uncommitted) — HEAD = result
    repo.write(f".bridge/reports/{task_id}.json",
               json.dumps(_base_report(task_id, base, result)))
    return repo


def _setup_payload_repo(task_id: str, rhino_bytes: bytes = None,
                         manifest_extras: dict = None,
                         run_id: str = None) -> tuple[TempRepo, str, str]:
    """
    Base with controller payload → work commit (payload unchanged).
    Report written but NOT committed. Returns (repo, base, result).
    """
    if rhino_bytes is None:
        rhino_bytes = _RHINO_CONTENT
    rhino_sha = _sha256(rhino_bytes)
    if manifest_extras is None:
        manifest_extras = {}
    repo = TempRepo()
    repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
    repo.write(f".bridge/requests/{task_id}.json", json.dumps(_base_request(task_id)))
    manifest_kw = dict(sha256=rhino_sha)
    if run_id:
        manifest_kw.update(modeling_run_id=run_id, pass_index=1, pass_kind="foundation")
    manifest_kw.update(manifest_extras)
    manifest = _base_manifest(task_id, **manifest_kw)
    repo.write(f".bridge/payloads/{task_id}/rhino.py", rhino_bytes)
    repo.write(f".bridge/payloads/{task_id}/manifest.json", json.dumps(manifest))
    repo.add(".")
    base = repo.commit("base")
    # Work commit
    if run_id:
        ev = _base_pass_eval(task_id, run_id, 1, "foundation", sha256=rhino_sha)
        repo.write(f".bridge/evidence/{task_id}/pass-evaluation.json", json.dumps(ev))
        repo.add(".")
    result = repo.commit("work")
    # Write report (uncommitted)
    repo.write(f".bridge/reports/{task_id}.json",
               json.dumps(_base_report(task_id, base, result)))
    return repo, base, result


# ===========================================================================
# Existing Phase-20 tests (all restructured: verify BEFORE receipt commit)
# ===========================================================================

class TestNonPayloadBackwardCompat(unittest.TestCase):
    def test_non_payload_passes(self):
        repo = _setup_nonpayload_repo("task-nonpayload")
        try:
            _run_verify(repo, "task-nonpayload")
        finally:
            repo.cleanup()


class TestValidFoundationPass(unittest.TestCase):
    def test_valid_foundation(self):
        repo, _, _ = _setup_payload_repo("model001-pass1", run_id="run-abc")
        try:
            _run_verify(repo, "model001-pass1")
        finally:
            repo.cleanup()


class TestValidCorrectionLineage(unittest.TestCase):
    def test_valid_correction(self):
        repo = TempRepo()
        try:
            run_id = "run-abc"
            parent_id = "model001-pass1"
            child_id = "model001-pass2"

            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)

            # Parent pass already merged into main
            parent_manifest = _base_manifest(parent_id, modeling_run_id=run_id,
                                             pass_index=1, pass_kind="foundation")
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))
            repo.write(f".bridge/requests/{parent_id}.json",
                       json.dumps(_base_request(parent_id)))
            repo.add(".")
            parent_base = repo.commit("parent-base")

            parent_ev = _base_pass_eval(parent_id, run_id, 1, "foundation")
            repo.write(f".bridge/evidence/{parent_id}/pass-evaluation.json",
                       json.dumps(parent_ev))
            repo.add(".")
            parent_result = repo.commit("parent-work")

            repo.write(f".bridge/reports/{parent_id}.json",
                       json.dumps(_base_report(parent_id, parent_base, parent_result)))
            repo.add(".")
            repo.commit("parent-receipt")

            # Child pass (correction) — different rhino.py bytes → different SHA
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

            # Report written but NOT committed — verify before receipt
            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))

            _run_verify(repo, child_id)
        finally:
            repo.cleanup()


class TestSHAMismatch(unittest.TestCase):
    def test_sha_mismatch(self):
        repo = TempRepo()
        try:
            task_id = "task-shamismatch"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            # Base manifest has wrong SHA
            manifest = _base_manifest(task_id, sha256="a" * 64)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest))
            repo.add(".")
            base = repo.commit("base")

            repo.write(f".bridge/evidence/{task_id}/notes.txt", "work")
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))

            _expect_fail(repo, task_id, "PROVENANCE_ERROR")
            # More specific: should mention SHA mismatch on BASE
            _expect_fail(repo, task_id, "mismatch")
        finally:
            repo.cleanup()


class TestOperatorPayloadModification(unittest.TestCase):
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

            # Operator modifies rhino.py and updates SHA in manifest — not authorized
            modified = b"# UNAUTHORIZED MODIFICATION\npass\n"
            modified_sha = _sha256(modified)
            manifest2 = _base_manifest(task_id, sha256=modified_sha)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", modified)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(manifest2))
            repo.add(".")
            result = repo.commit("operator-modified")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))

            _expect_fail(repo, task_id, "UNAUTHORIZED_LOCAL_MODELING")
        finally:
            repo.cleanup()


class TestMissingParentReport(unittest.TestCase):
    def test_missing_parent_report(self):
        repo = TempRepo()
        try:
            run_id = "run-xyz"
            parent_id = "pass1"
            child_id = "pass2"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{child_id}.json",
                       json.dumps(_base_request(child_id)))

            # Parent payload at base — but NO parent report (parent not yet merged)
            parent_manifest = _base_manifest(parent_id, modeling_run_id=run_id,
                                             pass_index=1, pass_kind="foundation")
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))

            # Child payload must also exist at base_commit (controller commits it)
            child_rhino = b"# child\npass\n"
            child_sha = _sha256(child_rhino)
            child_manifest = _base_manifest(
                child_id, sha256=child_sha,
                modeling_run_id=run_id,
                pass_index=2, pass_kind="correction",
                parent_task_id=parent_id,
                parent_payload_sha256=_RHINO_SHA,
                parent_result_commit="a" * 40,
            )
            repo.write(f".bridge/payloads/{child_id}/rhino.py", child_rhino)
            repo.write(f".bridge/payloads/{child_id}/manifest.json",
                       json.dumps(child_manifest))
            repo.add(".")
            base = repo.commit("base-no-parent-report")

            # Work commit: no changes to payload
            repo.write(f".bridge/evidence/{child_id}/notes.txt", "work")
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))

            _expect_fail(repo, child_id, "LINEAGE_ERROR")
        finally:
            repo.cleanup()


class TestWrongParentResultCommit(unittest.TestCase):
    def test_wrong_parent_result_commit(self):
        repo = TempRepo()
        try:
            run_id = "run-xyz"
            parent_id = "ppass1"
            child_id = "ppass2"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{child_id}.json",
                       json.dumps(_base_request(child_id)))

            # Both parent payload+report and child payload committed at base
            parent_manifest = _base_manifest(parent_id, modeling_run_id=run_id,
                                             pass_index=1, pass_kind="foundation")
            real_parent_result = "b" * 40
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))
            repo.write(f".bridge/reports/{parent_id}.json",
                       json.dumps(_base_report(parent_id, "a" * 40, real_parent_result)))

            # Child claims wrong parent_result_commit
            child_rhino = b"# child\npass\n"
            child_sha = _sha256(child_rhino)
            wrong_result = "c" * 40
            child_manifest = _base_manifest(
                child_id, sha256=child_sha,
                modeling_run_id=run_id,
                pass_index=2, pass_kind="correction",
                parent_task_id=parent_id,
                parent_payload_sha256=_RHINO_SHA,
                parent_result_commit=wrong_result,
            )
            repo.write(f".bridge/payloads/{child_id}/rhino.py", child_rhino)
            repo.write(f".bridge/payloads/{child_id}/manifest.json",
                       json.dumps(child_manifest))
            repo.add(".")
            base = repo.commit("base")

            # Work commit unchanged
            repo.write(f".bridge/evidence/{child_id}/notes.txt", "work")
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))

            _expect_fail(repo, child_id, "LINEAGE_ERROR")
        finally:
            repo.cleanup()


class TestWrongModelingRunId(unittest.TestCase):
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

            # Both parent payload+report and child payload committed at base
            parent_manifest = _base_manifest(parent_id, modeling_run_id=parent_run,
                                             pass_index=1, pass_kind="foundation")
            parent_result_sha = "d" * 40
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))
            repo.write(f".bridge/reports/{parent_id}.json",
                       json.dumps(_base_report(parent_id, "a" * 40, parent_result_sha)))

            # Child claims different run_id
            child_rhino = b"# child\npass\n"
            child_sha = _sha256(child_rhino)
            child_manifest = _base_manifest(
                child_id, sha256=child_sha,
                modeling_run_id=child_run,  # different!
                pass_index=2, pass_kind="correction",
                parent_task_id=parent_id,
                parent_payload_sha256=_RHINO_SHA,
                parent_result_commit=parent_result_sha,
            )
            repo.write(f".bridge/payloads/{child_id}/rhino.py", child_rhino)
            repo.write(f".bridge/payloads/{child_id}/manifest.json",
                       json.dumps(child_manifest))
            repo.add(".")
            base = repo.commit("base")

            repo.write(f".bridge/evidence/{child_id}/notes.txt", "work")
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))

            _expect_fail(repo, child_id, "modeling_run_id")
        finally:
            repo.cleanup()


class TestNonSequentialPassIndex(unittest.TestCase):
    def test_nonsequential_index(self):
        repo = TempRepo()
        try:
            run_id = "run-seq"
            parent_id = "spass1"
            child_id = "spass3"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{child_id}.json",
                       json.dumps(_base_request(child_id)))

            # Both parent payload+report and child payload committed at base
            parent_manifest = _base_manifest(parent_id, modeling_run_id=run_id,
                                             pass_index=1, pass_kind="foundation")
            parent_result = "e" * 40
            repo.write(f".bridge/payloads/{parent_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{parent_id}/manifest.json",
                       json.dumps(parent_manifest))
            repo.write(f".bridge/reports/{parent_id}.json",
                       json.dumps(_base_report(parent_id, "a" * 40, parent_result)))

            # Child payload with pass_index=3 (skips 2)
            child_rhino = b"# child\npass\n"
            child_sha = _sha256(child_rhino)
            child_manifest = _base_manifest(
                child_id, sha256=child_sha,
                modeling_run_id=run_id,
                pass_index=3,  # should be 2
                pass_kind="correction",
                parent_task_id=parent_id,
                parent_payload_sha256=_RHINO_SHA,
                parent_result_commit=parent_result,
            )
            repo.write(f".bridge/payloads/{child_id}/rhino.py", child_rhino)
            repo.write(f".bridge/payloads/{child_id}/manifest.json",
                       json.dumps(child_manifest))
            repo.add(".")
            base = repo.commit("base")

            repo.write(f".bridge/evidence/{child_id}/notes.txt", "work")
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{child_id}.json",
                       json.dumps(_base_report(child_id, base, result)))

            _expect_fail(repo, child_id, "pass_index")
        finally:
            repo.cleanup()


class TestMissingPassEvaluation(unittest.TestCase):
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

            _expect_fail(repo, task_id, "PASS_EVAL_ERROR")
        finally:
            repo.cleanup()


class TestWrongExecutedSHA(unittest.TestCase):
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
                                 sha256="f" * 64)
            repo.write(f".bridge/evidence/{task_id}/pass-evaluation.json",
                       json.dumps(ev))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))

            _expect_fail(repo, task_id, "executed_payload_sha256")
        finally:
            repo.cleanup()


class TestWrongRecommendationScope(unittest.TestCase):
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
            ev["operator_recommendation_scope"] = "redesign_recommended"
            repo.write(f".bridge/evidence/{task_id}/pass-evaluation.json",
                       json.dumps(ev))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))

            _expect_fail(repo, task_id, "evidence_only")
        finally:
            repo.cleanup()


class TestUnauthorizedLocalModelingUsed(unittest.TestCase):
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
            ev["local_modeling_used"] = True
            repo.write(f".bridge/evidence/{task_id}/pass-evaluation.json",
                       json.dumps(ev))
            repo.add(".")
            result = repo.commit("work")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))

            _expect_fail(repo, task_id, "local_modeling_used")
        finally:
            repo.cleanup()


class TestSinglePassNonModelingBackwardCompat(unittest.TestCase):
    def test_single_pass_no_run_id(self):
        repo, _, _ = _setup_payload_repo("task-singlepass")
        try:
            _run_verify(repo, "task-singlepass")
        finally:
            repo.cleanup()


# ===========================================================================
# New Phase-20 review-correction tests
# ===========================================================================

class TestSelfAuthorizationAttack(unittest.TestCase):
    """
    Operator changes base manifest local_modeling_authorized=false → true,
    modifies rhino.py, updates SHA. verify-report must reject this.
    """

    def test_operator_self_authorization(self):
        repo = TempRepo()
        try:
            task_id = "task-selfauth"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))

            # Controller commits: local_modeling_authorized=false
            base_manifest = _base_manifest(task_id, local_modeling_authorized=False)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(base_manifest))
            repo.add(".")
            base = repo.commit("base")

            # Operator modifies rhino.py, changes manifest to authorized=true, updates SHA
            modified_rhino = b"# SELF-AUTHORIZED geometry\ncreate_objects()\n"
            modified_sha = _sha256(modified_rhino)
            evil_manifest = _base_manifest(task_id, sha256=modified_sha,
                                           local_modeling_authorized=True)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", modified_rhino)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(evil_manifest))
            repo.add(".")
            result = repo.commit("operator-self-authorized")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))

            _expect_fail(repo, task_id, "UNAUTHORIZED_LOCAL_MODELING")
        finally:
            repo.cleanup()


class TestFabricatedPayloadAttack(unittest.TestCase):
    """
    Payload files absent at base_commit but introduced by the operator on the
    result commit. verify-report must reject: fabrication attack.
    """

    def test_payload_absent_at_base(self):
        repo = TempRepo()
        try:
            task_id = "task-fabricated"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            # Base commit: no payload files
            repo.add(".")
            base = repo.commit("base-no-payload")

            # Operator introduces manifest + rhino.py on the operator branch
            fabricated_manifest = _base_manifest(task_id)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(fabricated_manifest))
            repo.add(".")
            result = repo.commit("operator-fabricated")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))

            _expect_fail(repo, task_id, "PROVENANCE_ERROR")
        finally:
            repo.cleanup()


class TestResultManifestChangedUnauthorized(unittest.TestCase):
    """
    Operator changes manifest content (but NOT local_modeling_authorized) while
    authorization is false. Must fail as unauthorized modification.
    """

    def test_manifest_field_changed(self):
        repo = TempRepo()
        try:
            task_id = "task-mchange"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))

            base_manifest = _base_manifest(task_id, notes="original")
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(base_manifest))
            repo.add(".")
            base = repo.commit("base")

            # Operator changes a non-SHA field in the manifest
            altered_manifest = _base_manifest(task_id, notes="operator altered this")
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(altered_manifest))
            repo.add(".")
            result = repo.commit("manifest-altered")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))

            _expect_fail(repo, task_id, "UNAUTHORIZED_LOCAL_MODELING")
        finally:
            repo.cleanup()


class TestResultRhinoPyChangedUnauthorized(unittest.TestCase):
    """
    Operator changes rhino.py while authorization is false (and leaves manifest
    SHA mismatched to trigger the modification check, not the SHA check).
    The byte-comparison must catch the rhino.py change before SHA checks.
    """

    def test_rhino_py_changed(self):
        repo = TempRepo()
        try:
            task_id = "task-rchange"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))

            base_manifest = _base_manifest(task_id)
            repo.write(f".bridge/payloads/{task_id}/rhino.py", _RHINO_CONTENT)
            repo.write(f".bridge/payloads/{task_id}/manifest.json",
                       json.dumps(base_manifest))
            repo.add(".")
            base = repo.commit("base")

            # Operator changes rhino.py but keeps manifest SHA pointing at original
            # (so SHA would mismatch if we reached that check — but byte comparison fires first)
            repo.write(f".bridge/payloads/{task_id}/rhino.py",
                       b"# modified rhino.py\npass\n")
            repo.add(".")
            result = repo.commit("rhino-changed")

            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))

            _expect_fail(repo, task_id, "UNAUTHORIZED_LOCAL_MODELING")
        finally:
            repo.cleanup()


class TestNonexistentResultCommit(unittest.TestCase):
    """
    report.result_commit contains a well-formed 40-char SHA that does not
    exist as a git object. verify-report must reject it.
    """

    def test_nonexistent_result_commit(self):
        repo = _setup_nonpayload_repo("task-fakerepo")
        try:
            task_id = "task-fakerepo"
            base = repo.head()  # the work commit IS HEAD; we'll use a fake result SHA
            # Overwrite report with a nonexistent result_commit
            fake_sha = "deadbeef" * 5  # 40 hex chars that don't exist
            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, fake_sha)))
            _expect_fail(repo, task_id, "does not exist")
        finally:
            repo.cleanup()


class TestResultCommitNotCurrentHead(unittest.TestCase):
    """
    report.result_commit is a real git object but HEAD has moved past it
    (e.g. the receipt commit was already made). verify-report must reject.
    """

    def test_head_mismatch(self):
        repo = TempRepo()
        try:
            task_id = "task-headmismatch"
            repo.write(".bridge/protocol.json", _PROTOCOL_STUB)
            repo.write(f".bridge/requests/{task_id}.json",
                       json.dumps(_base_request(task_id)))
            repo.add(".")
            base = repo.commit("base")

            repo.write(f".bridge/evidence/{task_id}/done.txt", "x")
            repo.add(".")
            result = repo.commit("work")  # this is what result_commit should be

            # Write and commit receipt BEFORE running verify-report (wrong order)
            repo.write(f".bridge/reports/{task_id}.json",
                       json.dumps(_base_report(task_id, base, result)))
            repo.add(".")
            repo.commit("receipt-too-early")  # HEAD is now receipt commit ≠ result

            # Now try to verify — HEAD != result_commit
            _expect_fail(repo, task_id, "HEAD_MISMATCH")
        finally:
            repo.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
