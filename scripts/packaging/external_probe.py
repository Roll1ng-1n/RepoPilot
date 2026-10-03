"""Explicit optional service check with separate skip/unavailable/failure results."""

from __future__ import annotations

import json
import os
from pathlib import Path


def main():
    model = os.environ.get("REPOPILOT_MODEL")
    key = os.environ.get("REPOPILOT_API_KEY")
    if not model or not key:
        result = {"status": "skip", "reason": "Model or credentials not configured; no requests made."}
    else:
        from repopilot.model_probe import ModelProbe

        probe = ModelProbe(api_key=key, base_url=os.environ.get("REPOPILOT_BASE_URL")).probe_model(model)
        errors = [attempt.error for attempt in (probe.text, probe.tool_call) if attempt.error]
        unavailable = any(
            word in " ".join(errors).lower()
            for word in ("timeout", "connection", "notfound", "authentication", "ratelimit", "503", "502")
        )
        result = {
            "status": "passed" if probe.passed else "unavailable" if unavailable else "failure",
            "probe": probe.to_dict(),
        }
    Path("external-probe.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"])
    if result["status"] in {"failure", "unavailable"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
