"""Shared JSON-lines loop for engine workers. Runs inside each engine's own venv, so it
must not import anything from `app`.

stdout is reserved for protocol replies: we dup the real stdout away, then point fd 1 at
stderr so any library print()/C-level output lands in the log instead of corrupting it.
"""

import json
import os
import sys
import traceback
from collections.abc import Callable
from typing import Any

Handler = Callable[[dict[str, Any]], dict[str, Any]]


def serve(handlers: dict[str, Handler]) -> None:
    proto = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            cmd = req.get("cmd")
            if cmd == "shutdown":
                proto.write(json.dumps({"ok": True}) + "\n")
                return
            if cmd not in handlers:
                raise ValueError(f"unknown cmd {cmd!r}")
            resp = {"ok": True, **handlers[cmd](req)}
        except Exception as exc:  # noqa: BLE001 - report every failure to the parent
            traceback.print_exc()
            resp = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        proto.write(json.dumps(resp) + "\n")
