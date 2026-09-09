"""Read-only local prerequisites; never contacts a model provider."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import Any


def diagnose(*, model: str | None, api_key: str | None, image: str | None) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "python": {"version": platform.python_version(), "ok": sys.version_info >= (3, 10)},
        "git": {"available": shutil.which("git") is not None},
        "rg": {"available": shutil.which("rg") is not None},
        "model": {"configured": bool(model)},
        "credentials": {"configured": bool(api_key)},
    }
    docker = shutil.which("docker")
    wsl = "microsoft" in platform.release().lower() or bool(os.environ.get("WSL_DISTRO_NAME"))
    if not docker:
        checks["docker"] = {"status": "cli_missing", "wsl": wsl}
    else:
        try:
            server = subprocess.run(
                [docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=5
            )
            checks["docker"] = {
                "status": "available" if server.returncode == 0 else "server_unreachable",
                "wsl": wsl,
            }
            if server.returncode != 0 and wsl:
                checks["docker"]["hint"] = "Check Docker Desktop WSL integration for this distribution."
            if server.returncode == 0 and image:
                found = subprocess.run([docker, "image", "inspect", image], capture_output=True, timeout=5)
                checks["image"] = {"status": "available" if found.returncode == 0 else "missing"}
        except (OSError, subprocess.TimeoutExpired):
            checks["docker"] = {"status": "probe_failed", "wsl": wsl}
    checks.setdefault("image", {"status": "not_checked" if image else "not_configured"})
    return {"checks": checks, "paid_requests": 0}
