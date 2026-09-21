#!/usr/bin/env python3
"""Non-destructive host-side smoke tests. Rhino must be running for live tests."""
import json
from bridge import execute, status
from snippets import DOCUMENT_INFO

print(json.dumps(status(), indent=2))
if status().get("ok"):
    print(json.dumps(execute('result = {"ping": "pong"}', operation="smoke_ping"), indent=2))
    print(json.dumps(execute(DOCUMENT_INFO, operation="smoke_inspect"), indent=2))
