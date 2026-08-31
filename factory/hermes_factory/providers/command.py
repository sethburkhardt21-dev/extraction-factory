from __future__ import annotations
import json
import os
import shlex
import subprocess
from typing import Any, Dict, List
from .base import SemanticProvider
from ..models import WorkerIdentity


class JSONCommandProvider(SemanticProvider):
    """Generic real-provider bridge with no invented model CLI semantics.

    The configured command must accept one JSON request on stdin and emit one JSON
    response on stdout. It can wrap Hermes, Claude tooling, a local model server,
    or any other provider. The factory itself remains provider-neutral.
    """

    def __init__(self, command: List[str] | str, *, provider: str, model_alias: str,
                 underlying_family: str, observed_version: str = "UNKNOWN", role: str = "PRIMARY",
                 timeout_seconds: int = 600, network_required: bool = True,
                 certification_status: str = "UNBENCHMARKED"):
        self.command = shlex.split(command) if isinstance(command, str) else list(command)
        if not self.command:
            raise ValueError("empty_provider_command")
        self._identity = WorkerIdentity(provider, model_alias, underlying_family, observed_version, role, certification_status)
        self.timeout_seconds = timeout_seconds
        self.network_required = network_required

    def identity(self) -> WorkerIdentity:
        return self._identity

    def capabilities(self) -> Dict[str, Any]:
        return {"json_stdin_stdout": True, "network_required": self.network_required, "roles": [self._identity.role]}

    def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        env = os.environ.copy()
        proc = subprocess.run(
            self.command,
            input=json.dumps(request, ensure_ascii=False),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            timeout=self.timeout_seconds,
            env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"provider_command_failed:rc={proc.returncode}:stderr={proc.stderr[-4000:]}")
        try:
            output = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"provider_stdout_not_json:{exc}:stdout_tail={proc.stdout[-2000:]}")
        if proc.stderr.strip():
            output.setdefault("provider_diagnostics", {})["stderr"] = proc.stderr[-4000:]
        return output
