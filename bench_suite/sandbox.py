"""Per-task sandbox setup (setup_steps from TaskEntry)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def apply_setup_steps(task: dict[str, Any], sandbox: Path, *, allow_commands: bool = True) -> None:
    """Execute TaskEntry.setup_steps inside sandbox."""
    sandbox = Path(sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)
    for step in task.get("setup_steps") or []:
        action = step["action"]
        if action == "write_file":
            path = sandbox / step["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(step.get("content") or "", encoding="utf-8")
        elif action == "run_command":
            if not allow_commands:
                continue
            command = step.get("command")
            if not command:
                raise ValueError("run_command setup step requires 'command'")
            subprocess.run(
                command,
                shell=True,
                cwd=sandbox,
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            raise ValueError(f"Unknown setup action: {action}")


def write_sandbox_files(sandbox: Path, files: list[dict[str, str]]) -> None:
    """Write model-produced files into the sandbox (paths must be relative)."""
    sandbox = Path(sandbox).resolve()
    for item in files:
        rel = item["path"]
        path = (sandbox / rel).resolve()
        if not str(path).startswith(str(sandbox)):
            raise ValueError(f"Refusing path escape outside sandbox: {rel}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item.get("content") or "", encoding="utf-8")
