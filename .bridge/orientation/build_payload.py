#!/usr/bin/env python3
"""Build deterministic, self-contained orientation payloads from tracked sources."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ORIENTATION = ROOT / ".bridge" / "orientation"
MANIFEST_PATH = ORIENTATION / "manifest.json"


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8").rstrip()
    except OSError as exc:
        return f"[UNAVAILABLE: cannot read {relative_path}: {exc}]"


def read_json(relative_path: str) -> Any:
    path = ROOT / relative_path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"availability": "unavailable", "source": relative_path, "reason": str(exc)}


def command_output(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return False, str(exc)
    output = (result.stdout or result.stderr).strip()
    return result.returncode == 0, output


def main_sha() -> str:
    ok, output = command_output(["git", "rev-parse", "main"])
    return output if ok else f"UNAVAILABLE ({output})"


def bridge_live_state() -> dict[str, Any]:
    ok, output = command_output([sys.executable, ".bridge/bridge_cli.py", "status"])
    state: dict[str, Any] = {"availability": "available" if ok else "unavailable", "raw": output}
    if not ok:
        return state
    pending_count: int | None = None
    pending_ids: list[str] = []
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        if key == "pending":
            try:
                pending_count = int(value)
            except ValueError:
                pass
        elif key == "queued":
            pending_ids.append(value)
    state["pending_task_count"] = pending_count
    state["pending_task_ids"] = pending_ids
    return state


def render_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def build(role: str) -> str:
    manifest = read_json(".bridge/orientation/manifest.json")
    if not isinstance(manifest, dict):
        raise SystemExit("Orientation manifest must be a JSON object")
    role_guides = manifest.get("role_guides")
    if not isinstance(role_guides, dict) or role not in role_guides:
        raise SystemExit(f"Unsupported role: {role}")
    handbook_path = manifest.get("canonical_handbook_path")
    if not isinstance(handbook_path, str):
        raise SystemExit("Orientation manifest lacks canonical_handbook_path")
    role_path = role_guides[role]
    if not isinstance(role_path, str):
        raise SystemExit(f"Orientation manifest guide for {role} is invalid")

    controller_state = read_json(".bridge/state/controller.json")
    live_state = bridge_live_state()
    identity = {
        "orientation_version": manifest.get("orientation_version", "UNAVAILABLE"),
        "payload_format_version": manifest.get("generated_payload", {}).get("format_version", "UNAVAILABLE"),
        "repository": manifest.get("repository", "UNAVAILABLE"),
        "protocol_version": manifest.get("compatible_protocol_version", "UNAVAILABLE"),
        "selected_role": role,
        "current_main_commit": main_sha(),
        "controller_state_source": ".bridge/state/controller.json",
        "pending_tasks_source": "python3 .bridge/bridge_cli.py status",
    }

    return "\n".join(
        [
            "# Rhino CHATGPT Orientation Payload",
            "",
            "## GENERATED / LIVE FACTS — inspect time dependent; not stable instructions",
            render_json(identity),
            "",
            "### Current controller state (generated from .bridge/state/controller.json)",
            render_json(controller_state),
            "",
            "### Live bridge task state (generated from bridge_cli.py when available)",
            render_json(live_state),
            "",
            "## STABLE HANDBOOK CONTENT — canonical tracked source",
            f"Source: `{handbook_path}`",
            "",
            read_text(handbook_path),
            "",
            "## SELECTED ROLE GUIDE — canonical tracked source",
            f"Selected role: `{role}`",
            f"Source: `{role_path}`",
            "",
            read_text(role_path),
            "",
            "## PAYLOAD END",
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Rhino CHATGPT orientation payload.")
    parser.add_argument("role", nargs="?", default="universal", choices=("controller", "operator", "reviewer", "universal"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(build(args.role), end="")
