#!/usr/bin/env python3
"""
run_rhino_payload.py — Deterministic controller-authored payload runner.

Executes a controller-authored .bridge/payloads/<task-id>/rhino.py through the
bridge.execute() → rhinocode → Rhino path. Never creates geometry itself.

Usage:
    python3 .bridge/run_rhino_payload.py --task TASK_ID [options]

Options:
    --task TASK_ID           Required. Task ID matching a directory under .bridge/payloads/.
    --document-id DOC_ID     Required when manifest.target_document_required=true.
                             Format: PID:runtime_serial (from rhino_list_documents).
    --timeout SECONDS        Execution timeout passed to bridge.execute(). Default: 30.
    --dry-run                Verify manifest, hash, and Python compatibility only.
                             Does not execute Rhino. Exit 0 on pass, nonzero on failure.

Exit codes:
    0  Success (or dry-run pass).
    1  Validation failure (hash mismatch, bad manifest, missing target, Python rejected).
    2  Execution failure (Rhino error, bridge error, timeout).
    3  Usage / argument error.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Repository root is one level above this file's directory (.bridge/).
_BRIDGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BRIDGE_DIR.parent
_PAYLOADS_DIR = _BRIDGE_DIR / "payloads"

REQUIRED_MANIFEST_FIELDS = [
    "payload_version", "task_id", "author_role", "authoring_model",
    "payload_type", "python_compatibility", "execution_method",
    "operation_name", "sha256", "target_document_required",
]

# task_id must be a safe directory name: alphanumeric, hyphens, underscores, leading underscore allowed.
_TASK_ID_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_\-]*$')


def _fail(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _resolve_payload_dir(task_id: str) -> Path:
    """Return the resolved payload directory; reject any path traversal."""
    if not _TASK_ID_RE.match(task_id):
        _fail(f"Invalid task_id format: {task_id!r}. Must match [A-Za-z0-9_][A-Za-z0-9_-]*", 3)
    payload_dir = (_PAYLOADS_DIR / task_id).resolve()
    # Guard against path traversal (e.g., task_id = "../../../etc")
    try:
        payload_dir.relative_to(_PAYLOADS_DIR.resolve())
    except ValueError:
        _fail(f"task_id resolves outside .bridge/payloads/: {payload_dir}", 1)
    return payload_dir


def _load_manifest(payload_dir: Path) -> dict:
    manifest_path = payload_dir / "manifest.json"
    if not manifest_path.exists():
        _fail(f"manifest.json not found in {payload_dir}")
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        _fail(f"manifest.json is not valid JSON: {exc}")
    return manifest


def _validate_manifest(manifest: dict, task_id: str) -> None:
    missing = [f for f in REQUIRED_MANIFEST_FIELDS if f not in manifest]
    if missing:
        _fail(f"manifest.json missing required fields: {missing}")
    if manifest.get("task_id") != task_id:
        _fail(f"manifest task_id {manifest['task_id']!r} does not match requested task {task_id!r}")
    if manifest.get("author_role") != "controller":
        _fail(f"author_role must be 'controller', got {manifest.get('author_role')!r}. "
              "Local modeling is not permitted without explicit request authorization.")


def _verify_hash(payload_dir: Path, manifest: dict) -> str:
    rhino_py = payload_dir / "rhino.py"
    if not rhino_py.exists():
        _fail(f"rhino.py not found in {payload_dir}")
    code = rhino_py.read_bytes()
    actual = hashlib.sha256(code).hexdigest()
    expected = manifest.get("sha256", "")
    if actual != expected:
        _fail(f"SHA-256 mismatch.\n  manifest: {expected}\n  actual:   {actual}\n"
              "The payload may have been modified after the controller committed it. "
              "Do not execute a payload with a mismatched hash.")
    return rhino_py.read_text()


def _check_python_compat(code: str) -> None:
    # Import tool_support from repo root — it must be importable.
    sys.path.insert(0, str(_REPO_ROOT))
    try:
        from tool_support import check_code
    except ImportError as exc:
        _fail(f"Cannot import tool_support from {_REPO_ROOT}: {exc}")
    try:
        check_code(code)
    except (SyntaxError, ValueError) as exc:
        _fail(f"Python 3.9 compatibility check failed: {exc}")


def _derive_idempotency_key(task_id: str, sha256: str, manifest: dict) -> str:
    explicit = manifest.get("idempotency_key", "").strip()
    if explicit:
        return explicit
    return f"run_rhino_payload:{task_id}:{sha256}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute a controller-authored Rhino payload through bridge.execute().",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--task", required=True, metavar="TASK_ID",
                        help="Task ID matching .bridge/payloads/<task-id>/")
    parser.add_argument("--document-id", default=None, metavar="PID:runtime_serial",
                        help="Target document ID. Required when manifest.target_document_required=true.")
    parser.add_argument("--timeout", type=float, default=30.0, metavar="SECONDS",
                        help="Execution timeout in seconds (default: 30).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Verify manifest/hash/Python only; do not execute Rhino.")
    args = parser.parse_args()

    task_id = args.task
    document_id = args.document_id
    timeout = args.timeout
    dry_run = args.dry_run

    # 1. Resolve and guard payload directory.
    payload_dir = _resolve_payload_dir(task_id)
    if not payload_dir.is_dir():
        _fail(f"Payload directory not found: {payload_dir}", 1)

    # 2. Load and validate manifest.
    manifest = _load_manifest(payload_dir)
    _validate_manifest(manifest, task_id)

    # 3. Verify SHA-256 and read code.
    code = _verify_hash(payload_dir, manifest)

    # 4. Python 3.9 compatibility check.
    _check_python_compat(code)

    # 5. Target document check.
    target_required = bool(manifest.get("target_document_required", True))
    if target_required and not document_id:
        _fail("manifest.target_document_required=true but --document-id was not supplied. "
              "Provide a document ID from rhino_list_documents (format: PID:runtime_serial).")

    print(json.dumps({
        "status": "verified",
        "task_id": task_id,
        "operation_name": manifest.get("operation_name"),
        "sha256": manifest.get("sha256"),
        "author_role": manifest.get("author_role"),
        "target_document_required": target_required,
        "document_id": document_id,
        "dry_run": dry_run,
        "local_modeling_authorized": manifest.get("local_modeling_authorized", False),
    }), flush=True)

    if dry_run:
        print("DRY-RUN PASS: manifest valid, hash verified, Python 3.9 compatible.", flush=True)
        sys.exit(0)

    # 6. Execute via bridge.execute().
    sys.path.insert(0, str(_REPO_ROOT))
    try:
        import bridge
    except ImportError as exc:
        _fail(f"Cannot import bridge from {_REPO_ROOT}: {exc}", 2)

    idempotency_key = _derive_idempotency_key(task_id, manifest["sha256"], manifest)
    operation = manifest.get("operation_name", "rhino_payload")

    result = bridge.execute(
        code,
        timeout=timeout,
        operation=operation,
        document_id=document_id,
        idempotency_key=idempotency_key,
    )

    print(json.dumps(result, default=str, indent=2), flush=True)

    if not result.get("ok"):
        kind = result.get("kind", "unknown")
        _fail(f"bridge.execute() returned ok=false: kind={kind}", 2)

    print("EXECUTION COMPLETE.", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
