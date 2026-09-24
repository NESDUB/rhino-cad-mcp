#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / ".bridge"
REQUESTS = BRIDGE / "requests"
REPORTS = BRIDGE / "reports"
PROTOCOL = BRIDGE / "protocol.json"
CURRENT_PROTOCOL = "0.3"

TASK_RE = re.compile(r"^[A-Za-z0-9._-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


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
    print(f"REPORT_OK {task_id}")


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
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main()
