#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / ".bridge"
REQUESTS = BRIDGE / "requests"
REPORTS = BRIDGE / "reports"
PAYLOADS = BRIDGE / "payloads"
EVIDENCE = BRIDGE / "evidence"
PROTOCOL = BRIDGE / "protocol.json"
CURRENT_PROTOCOL = "0.3"

TASK_RE = re.compile(r"^[A-Za-z0-9._-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VALID_PASS_KINDS = {"foundation", "correction", "detail_qa", "hotfix", "single_pass"}


# ---------------------------------------------------------------------------
# Basic I/O helpers
# ---------------------------------------------------------------------------

def load(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def request_path(task_id: str) -> Path:
    return REQUESTS / f"{task_id}.json"


def report_path(task_id: str) -> Path:
    return REPORTS / f"{task_id}.json"


def validate_task_id(task_id: str):
    if not TASK_RE.fullmatch(task_id):
        raise SystemExit(f"Invalid task id: {task_id}")


# ---------------------------------------------------------------------------
# Git helpers (subprocess — standard library only)
# ---------------------------------------------------------------------------

def _git_show_bytes(sha: str, rel_path: str) -> bytes | None:
    """Return the raw bytes of rel_path at the given commit SHA, or None."""
    r = subprocess.run(
        ["git", "show", f"{sha}:{rel_path}"],
        capture_output=True,
        cwd=str(ROOT),
    )
    return r.stdout if r.returncode == 0 else None


def _git_show_json(sha: str, rel_path: str) -> dict | None:
    """Return parsed JSON of rel_path at the given commit SHA, or None."""
    raw = _git_show_bytes(sha, rel_path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Phase-20 provenance checks
# ---------------------------------------------------------------------------

def _check_payload_provenance(task_id: str, base_commit: str, result_commit: str) -> dict | None:
    """
    Enforce controller-authored payload provenance.

    Payload-task status is determined from BASE commit, never result commit:
      base absent + result absent → non-payload task, return None
      base absent + result present → operator fabricated a payload, reject
      base present + result absent → operator deleted the manifest, reject
      base present + result present → full provenance validation

    Additional trust-boundary rules:
      - author_role=controller is checked at base_commit.
      - base rhino.py SHA-256 must match base manifest.sha256.
      - Authorization is read exclusively from base manifest.
        Operator cannot self-authorize by changing local_modeling_authorized.
      - When local_modeling_authorized=false:
          result manifest and rhino.py must be byte-for-byte identical to base.
      - When local_modeling_authorized=true (authorized Codex task):
          result rhino.py SHA-256 must match result manifest.sha256.
          Only manifest.sha256 may differ; all other controller-owned fields
          (task_id, author_role, modeling_run_id, pass_index, pass_kind,
          parent lineage, etc.) must remain identical to base manifest.
          Returns a manifest using base contract values + verified result sha256
          so downstream lineage checks cannot consume operator-modified fields.

    Returns the authoritative manifest dict on success.
    Raises SystemExit on any provenance violation.
    """
    manifest_rel = f".bridge/payloads/{task_id}/manifest.json"
    rhino_rel    = f".bridge/payloads/{task_id}/rhino.py"

    # Payload-task detection is driven by base_commit (controller's state).
    base_manifest_bytes   = _git_show_bytes(base_commit, manifest_rel)
    result_manifest_bytes = _git_show_bytes(result_commit, manifest_rel)

    if base_manifest_bytes is None:
        if result_manifest_bytes is None:
            # Neither commit has a manifest → ordinary non-payload task.
            return None
        # Operator introduced a payload that has no controller origin.
        raise SystemExit(
            f"PROVENANCE_ERROR: {manifest_rel} is absent at base_commit {base_commit} "
            f"but present at result_commit. Operator cannot introduce a controller "
            f"payload; it must originate from the controller on main."
        )

    # base manifest present → this is a payload task regardless of result.
    if result_manifest_bytes is None:
        raise SystemExit(
            f"PROVENANCE_ERROR: {manifest_rel} exists at base_commit {base_commit} "
            f"but was deleted by the operator on result_commit {result_commit}. "
            f"Operator cannot delete a controller-authored manifest."
        )

    # Parse manifests.
    try:
        base_manifest = json.loads(base_manifest_bytes)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"PROVENANCE_ERROR: {manifest_rel} at base_commit is not valid JSON: {exc}"
        )
    try:
        result_manifest = json.loads(result_manifest_bytes)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"PROVENANCE_ERROR: {manifest_rel} at result_commit is not valid JSON: {exc}"
        )

    # author_role must be "controller" at base_commit.
    if base_manifest.get("author_role") != "controller":
        raise SystemExit(
            f"PROVENANCE_ERROR: base manifest author_role is "
            f"{base_manifest.get('author_role')!r}, expected 'controller'"
        )

    # Load rhino.py from both commits.
    base_rhino   = _git_show_bytes(base_commit, rhino_rel)
    result_rhino = _git_show_bytes(result_commit, rhino_rel)

    if base_rhino is None:
        raise SystemExit(
            f"PROVENANCE_ERROR: {rhino_rel} not found at base_commit {base_commit}. "
            f"Controller must commit rhino.py alongside the manifest."
        )
    if result_rhino is None:
        raise SystemExit(
            f"PROVENANCE_ERROR: {rhino_rel} was deleted by operator at "
            f"result_commit {result_commit}. Operator cannot delete rhino.py."
        )

    # Base integrity: base rhino.py SHA-256 must match base manifest.sha256.
    base_computed = hashlib.sha256(base_rhino).hexdigest()
    base_declared = base_manifest.get("sha256", "")
    if base_computed != base_declared:
        raise SystemExit(
            f"PROVENANCE_ERROR: base rhino.py SHA-256 mismatch — "
            f"computed {base_computed}, base manifest declares {base_declared}"
        )

    # Authorization is authoritative from BASE manifest only — never from result.
    authorized = base_manifest.get("local_modeling_authorized", False)

    # Self-authorization prevention: result manifest must not grant more authority.
    if not authorized and result_manifest.get("local_modeling_authorized", False):
        raise SystemExit(
            f"UNAUTHORIZED_LOCAL_MODELING: result manifest claims "
            f"local_modeling_authorized=true but base manifest has "
            f"local_modeling_authorized=false. Operator cannot self-authorize."
        )

    if not authorized:
        # Byte-for-byte immutability when not authorized.
        if result_manifest_bytes != base_manifest_bytes:
            raise SystemExit(
                f"UNAUTHORIZED_LOCAL_MODELING: manifest.json was modified on the operator "
                f"branch but local_modeling_authorized=false per base manifest"
            )
        if result_rhino != base_rhino:
            raise SystemExit(
                f"UNAUTHORIZED_LOCAL_MODELING: rhino.py was modified on the operator "
                f"branch but local_modeling_authorized=false per base manifest"
            )
        # Both identical — return result manifest (equals base manifest).
        return result_manifest

    # ---- Authorized local-modeling path ----
    # Codex may change rhino.py and update sha256. All other controller-owned
    # contract fields must remain identical to base manifest.

    result_computed = hashlib.sha256(result_rhino).hexdigest()
    result_declared = result_manifest.get("sha256", "")
    if result_computed != result_declared:
        raise SystemExit(
            f"PROVENANCE_ERROR: result rhino.py SHA-256 mismatch — "
            f"computed {result_computed}, result manifest declares {result_declared}"
        )

    # Only sha256 may differ; all other fields must be controller-authoritative.
    _OPERATOR_WRITABLE = {"sha256"}
    base_contract   = {k: v for k, v in base_manifest.items()
                       if k not in _OPERATOR_WRITABLE}
    result_contract = {k: v for k, v in result_manifest.items()
                       if k not in _OPERATOR_WRITABLE}
    if base_contract != result_contract:
        all_keys = set(base_contract) | set(result_contract)
        changed = sorted(k for k in all_keys
                         if base_contract.get(k) != result_contract.get(k))
        raise SystemExit(
            f"MANIFEST_CONTRACT_ERROR: local_modeling_authorized=true permits only "
            f"sha256 to change; these fields differ from the controller base: {changed}"
        )

    # Return authoritative manifest: base controller contract + verified result sha256.
    # This ensures _check_multipass_lineage/_check_pass_evaluation cannot consume
    # any operator-modified contract values.
    authoritative = dict(base_manifest)
    authoritative["sha256"] = result_declared
    return authoritative


def _check_multipass_lineage(task_id: str, base_commit: str, manifest: dict) -> None:
    """
    Enforce multi-pass lineage invariants when manifest carries a modeling_run_id.
    Raises SystemExit on any violation.
    """
    run_id = manifest.get("modeling_run_id", "")
    if not run_id:
        return  # Not a multi-pass task; skip.

    # modeling_run_id must be a non-empty string (already confirmed above)

    # pass_index must be a positive integer
    pass_index = manifest.get("pass_index")
    if not isinstance(pass_index, int) or pass_index < 1:
        raise SystemExit(
            f"LINEAGE_ERROR: manifest.pass_index must be a positive integer, "
            f"got {pass_index!r}"
        )

    # pass_kind must be one of the valid values
    pass_kind = manifest.get("pass_kind", "")
    if pass_kind not in VALID_PASS_KINDS:
        raise SystemExit(
            f"LINEAGE_ERROR: manifest.pass_kind {pass_kind!r} not in "
            f"{sorted(VALID_PASS_KINDS)}"
        )

    # requires_controller_review_after must be boolean if present
    rcra = manifest.get("requires_controller_review_after")
    if rcra is not None and not isinstance(rcra, bool):
        raise SystemExit(
            f"LINEAGE_ERROR: manifest.requires_controller_review_after must be "
            f"boolean, got {rcra!r}"
        )

    parent_task_id     = manifest.get("parent_task_id", "")
    parent_sha256      = manifest.get("parent_payload_sha256", "")
    parent_result_sha  = manifest.get("parent_result_commit", "")

    if pass_index == 1:
        # Foundation pass: reject parent lineage fields unless this is explicitly
        # a hotfix/import case (documented via pass_kind=hotfix).
        if pass_kind != "hotfix":
            if parent_task_id or parent_sha256 or parent_result_sha:
                raise SystemExit(
                    f"LINEAGE_ERROR: pass_index=1/pass_kind={pass_kind!r} must not "
                    f"carry parent lineage fields (parent_task_id, "
                    f"parent_payload_sha256, parent_result_commit)"
                )
    else:
        # pass_index > 1: require all parent lineage fields
        for field, value in [
            ("parent_task_id",         parent_task_id),
            ("parent_payload_sha256",  parent_sha256),
            ("parent_result_commit",   parent_result_sha),
        ]:
            if not value:
                raise SystemExit(
                    f"LINEAGE_ERROR: pass_index={pass_index} requires "
                    f"manifest.{field}"
                )

        # Validate parent_task_id format
        if not TASK_RE.fullmatch(parent_task_id):
            raise SystemExit(
                f"LINEAGE_ERROR: invalid parent_task_id {parent_task_id!r}"
            )

        # Validate parent_result_commit is a 40-char SHA
        if not SHA_RE.fullmatch(parent_result_sha):
            raise SystemExit(
                f"LINEAGE_ERROR: parent_result_commit must be a 40-character "
                f"lowercase SHA, got {parent_result_sha!r}"
            )

        # Resolve parent from base_commit (not from operator modifications)
        parent_report_rel   = f".bridge/reports/{parent_task_id}.json"
        parent_manifest_rel = f".bridge/payloads/{parent_task_id}/manifest.json"

        parent_report = _git_show_json(base_commit, parent_report_rel)
        if parent_report is None:
            raise SystemExit(
                f"LINEAGE_ERROR: parent report "
                f"{parent_report_rel} not found at base_commit {base_commit}. "
                f"Controller must merge the parent pass before queuing the next."
            )

        # Parent report's result_commit must equal manifest's parent_result_commit
        pr_result = parent_report.get("result_commit", "")
        if pr_result != parent_result_sha:
            raise SystemExit(
                f"LINEAGE_ERROR: parent report result_commit {pr_result!r} does not "
                f"match manifest.parent_result_commit {parent_result_sha!r}"
            )

        # Parent payload manifest must exist at base_commit
        parent_manifest = _git_show_json(base_commit, parent_manifest_rel)
        if parent_manifest is None:
            raise SystemExit(
                f"LINEAGE_ERROR: parent manifest {parent_manifest_rel} not found "
                f"at base_commit {base_commit}"
            )

        # Parent manifest sha256 must equal manifest's parent_payload_sha256
        pm_sha = parent_manifest.get("sha256", "")
        if pm_sha != parent_sha256:
            raise SystemExit(
                f"LINEAGE_ERROR: parent manifest sha256 {pm_sha!r} does not match "
                f"manifest.parent_payload_sha256 {parent_sha256!r}"
            )

        # Same modeling_run_id
        pm_run_id = parent_manifest.get("modeling_run_id", "")
        if pm_run_id != run_id:
            raise SystemExit(
                f"LINEAGE_ERROR: parent manifest modeling_run_id {pm_run_id!r} "
                f"does not match current modeling_run_id {run_id!r}"
            )

        # pass_index must be parent pass_index + 1
        parent_pass_index = parent_manifest.get("pass_index")
        if not isinstance(parent_pass_index, int):
            raise SystemExit(
                f"LINEAGE_ERROR: parent manifest pass_index is not an integer: "
                f"{parent_pass_index!r}"
            )
        if pass_index != parent_pass_index + 1:
            raise SystemExit(
                f"LINEAGE_ERROR: expected pass_index={parent_pass_index + 1}, "
                f"got {pass_index}"
            )


def _check_pass_evaluation(task_id: str, result_commit: str, manifest: dict) -> None:
    """
    For multi-pass tasks, require pass-evaluation.json at result_commit and
    validate its fields against the manifest.
    Raises SystemExit on any violation.
    """
    run_id = manifest.get("modeling_run_id", "")
    if not run_id:
        return  # Not a multi-pass task; skip.

    eval_rel = f".bridge/evidence/{task_id}/pass-evaluation.json"
    raw = _git_show_bytes(result_commit, eval_rel)
    if raw is None:
        raise SystemExit(
            f"PASS_EVAL_ERROR: {eval_rel} not found at result_commit "
            f"{result_commit}. Multi-pass tasks must commit pass-evaluation.json."
        )

    try:
        ev = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"PASS_EVAL_ERROR: {eval_rel} is not valid JSON: {exc}")

    # Cross-validate fields against manifest
    checks = [
        ("task_id",                   task_id,                  ev.get("task_id")),
        ("modeling_run_id",           run_id,                   ev.get("modeling_run_id")),
        ("pass_index",                manifest.get("pass_index"), ev.get("pass_index")),
        ("pass_kind",                 manifest.get("pass_kind"),  ev.get("pass_kind")),
        ("executed_payload_sha256",   manifest.get("sha256"),    ev.get("executed_payload_sha256")),
    ]
    for field, expected, actual in checks:
        if actual != expected:
            raise SystemExit(
                f"PASS_EVAL_ERROR: pass-evaluation.{field}={actual!r}, "
                f"expected {expected!r}"
            )

    # operator_recommendation_scope must be "evidence_only"
    scope = ev.get("operator_recommendation_scope")
    if scope != "evidence_only":
        raise SystemExit(
            f"PASS_EVAL_ERROR: operator_recommendation_scope={scope!r}, "
            f"must be 'evidence_only'"
        )

    # Unauthorized local modeling checks
    authorized = manifest.get("local_modeling_authorized", False)
    if not authorized:
        if ev.get("local_modeling_used") is True:
            raise SystemExit(
                "PASS_EVAL_ERROR: pass-evaluation.local_modeling_used=true but "
                "manifest.local_modeling_authorized=false"
            )
        if ev.get("payload_modified_by_operator") is True:
            raise SystemExit(
                "PASS_EVAL_ERROR: pass-evaluation.payload_modified_by_operator=true "
                "but manifest.local_modeling_authorized=false"
            )


# ---------------------------------------------------------------------------
# Request / report loading
# ---------------------------------------------------------------------------

def load_request(task_id: str):
    validate_task_id(task_id)
    path = request_path(task_id)
    if not path.exists():
        raise SystemExit(f"Missing request: {path}")
    req = load(path)
    required = {
        "protocol_version",
        "task_id",
        "status",
        "controller",
        "objective",
        "operator_branch",
        "instructions",
        "expected_outputs",
        "constraints",
    }
    missing = sorted(required - set(req))
    if missing:
        raise SystemExit(f"Request missing fields: {', '.join(missing)}")
    if req["task_id"] != task_id:
        raise SystemExit("Request task_id mismatch")
    if req["protocol_version"] != CURRENT_PROTOCOL:
        raise SystemExit(
            f"Request protocol mismatch: expected {CURRENT_PROTOCOL}, got {req['protocol_version']}"
        )
    branch = req["operator_branch"]
    if not isinstance(branch, str) or not BRANCH_RE.fullmatch(branch):
        raise SystemExit(f"Invalid operator branch: {branch!r}")
    return req


def iter_requests():
    for path in sorted(REQUESTS.glob("*.json")):
        try:
            item = load(path)
        except Exception as exc:
            raise SystemExit(f"Invalid JSON in {path}: {exc}")
        if "task_id" not in item:
            raise SystemExit(f"Request lacks task_id: {path}")
        yield path, item


def pending():
    out = []
    for path, req in iter_requests():
        task_id = req["task_id"]
        if not report_path(task_id).exists():
            out.append((path, req))
    return out


def single_pending_request():
    pend = pending()
    if len(pend) != 1:
        raise SystemExit(f"Expected exactly one pending request, found {len(pend)}")
    path, item = pend[0]
    req = load_request(item["task_id"])
    return path, req


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_status():
    protocol = load(PROTOCOL)
    reqs = list(iter_requests())
    pend = pending()
    print(f"protocol={protocol['protocol_version']}")
    print(f"requests={len(reqs)}")
    print(f"pending={len(pend)}")
    print(f"reports={len(list(REPORTS.glob('*.json'))) if REPORTS.exists() else 0}")
    for _, req in pend:
        print(f"queued={req['task_id']}")


def cmd_next():
    pend = pending()
    if not pend:
        print("NO_PENDING_REQUESTS")
        return
    _, req = pend[0]
    print(json.dumps(req, indent=2, sort_keys=True))


def cmd_next_id():
    _, req = single_pending_request()
    print(req["task_id"])


def cmd_next_branch():
    _, req = single_pending_request()
    print(req["operator_branch"])


def cmd_validate_request(task_id: str):
    req = load_request(task_id)
    print(f"REQUEST_OK {req['task_id']}")


def cmd_branch(task_id: str):
    req = load_request(task_id)
    print(req["operator_branch"])


def cmd_verify_report(task_id: str):
    validate_task_id(task_id)
    path = report_path(task_id)
    if not path.exists():
        raise SystemExit(f"Missing report: {path}")
    report = load(path)
    required = {
        "protocol_version",
        "task_id",
        "status",
        "operator",
        "ack",
        "base_commit",
        "result_commit",
        "branch",
        "summary",
        "files_changed",
        "tests",
        "blockers",
        "notes_for_controller",
    }
    missing = sorted(required - set(report))
    if missing:
        raise SystemExit(f"Report missing fields: {', '.join(missing)}")
    if report["protocol_version"] != CURRENT_PROTOCOL:
        raise SystemExit("Report protocol_version mismatch")
    if report["task_id"] != task_id:
        raise SystemExit("Report task_id mismatch")
    if report["status"] not in {"blocked", "complete"}:
        raise SystemExit("Report status must be blocked or complete")
    for field in ("base_commit", "result_commit"):
        value = report[field]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
            raise SystemExit(f"Report {field} must be a 40-character lowercase Git SHA")
    req = load_request(task_id)
    if report["branch"] != req["operator_branch"]:
        raise SystemExit("Report branch does not match request operator_branch")

    # Verify result_commit is a real git object and equals current HEAD.
    # verify-report is run before the receipt commit, so HEAD must be the work commit.
    base_commit   = report["base_commit"]
    result_commit = report["result_commit"]

    obj_check = subprocess.run(
        ["git", "cat-file", "-e", result_commit],
        capture_output=True,
        cwd=str(ROOT),
    )
    if obj_check.returncode != 0:
        raise SystemExit(
            f"result_commit {result_commit!r} does not exist as a git object. "
            f"Ensure result_commit references the actual work commit SHA."
        )

    head_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True,
        cwd=str(ROOT),
    )
    current_head = head_result.stdout.strip()
    if current_head != result_commit:
        raise SystemExit(
            f"HEAD_MISMATCH: report.result_commit={result_commit!r} but "
            f"current HEAD={current_head!r}. "
            f"Run verify-report before the receipt commit, with HEAD at the work commit."
        )

    # Phase-20 provenance and multi-pass enforcement

    manifest = _check_payload_provenance(task_id, base_commit, result_commit)
    if manifest is not None:
        _check_multipass_lineage(task_id, base_commit, manifest)
        _check_pass_evaluation(task_id, result_commit, manifest)

    print(f"REPORT_OK {task_id}")


def cmd_next_pass_context(parent_task_id: str):
    """
    Non-mutating helper: reads parent report + manifest from the current
    checkout and prints JSON with the lineage context for the next pass.
    Does not author geometry or modify any file.
    """
    validate_task_id(parent_task_id)

    parent_report_path   = REPORTS / f"{parent_task_id}.json"
    parent_manifest_path = PAYLOADS / parent_task_id / "manifest.json"

    if not parent_report_path.exists():
        raise SystemExit(
            f"next-pass-context: parent report not found: {parent_report_path}"
        )
    if not parent_manifest_path.exists():
        raise SystemExit(
            f"next-pass-context: parent manifest not found: {parent_manifest_path}"
        )

    parent_report   = load(parent_report_path)
    parent_manifest = load(parent_manifest_path)

    run_id = parent_manifest.get("modeling_run_id", "")
    if not run_id:
        raise SystemExit(
            f"next-pass-context: parent manifest has no modeling_run_id — "
            f"{parent_task_id} is not a multi-pass task"
        )

    parent_pass_index = parent_manifest.get("pass_index")
    if not isinstance(parent_pass_index, int) or parent_pass_index < 1:
        raise SystemExit(
            f"next-pass-context: parent manifest pass_index invalid: "
            f"{parent_pass_index!r}"
        )

    result_commit = parent_report.get("result_commit", "")

    context = {
        "modeling_run_id":        run_id,
        "next_pass_index":        parent_pass_index + 1,
        "parent_task_id":         parent_task_id,
        "parent_payload_sha256":  parent_manifest.get("sha256", ""),
        "parent_result_commit":   result_commit,
        "parent_pass_kind":       parent_manifest.get("pass_kind", ""),
    }
    print(json.dumps(context, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "status"

    if command == "status":
        cmd_status()
    elif command == "next":
        cmd_next()
    elif command == "next-id":
        cmd_next_id()
    elif command == "next-branch":
        cmd_next_branch()
    elif command == "validate-request":
        if len(sys.argv) != 3:
            raise SystemExit("usage: bridge_cli.py validate-request TASK_ID")
        cmd_validate_request(sys.argv[2])
    elif command == "branch":
        if len(sys.argv) != 3:
            raise SystemExit("usage: bridge_cli.py branch TASK_ID")
        cmd_branch(sys.argv[2])
    elif command == "verify-report":
        if len(sys.argv) != 3:
            raise SystemExit("usage: bridge_cli.py verify-report TASK_ID")
        cmd_verify_report(sys.argv[2])
    elif command == "next-pass-context":
        if len(sys.argv) != 3:
            raise SystemExit("usage: bridge_cli.py next-pass-context PARENT_TASK_ID")
        cmd_next_pass_context(sys.argv[2])
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main()
