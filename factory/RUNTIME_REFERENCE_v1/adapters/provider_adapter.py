from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import json, subprocess, time, uuid

@dataclass
class WorkerIdentity:
    provider: str
    model_alias: str
    underlying_family: str
    observed_version: str

class ProviderAdapter(ABC):
    @abstractmethod
    def identity(self) -> WorkerIdentity: ...
    @abstractmethod
    def capabilities(self) -> dict: ...
    @abstractmethod
    def launch(self, capsule_path: Path, lease: dict) -> dict: ...
    @abstractmethod
    def status(self, run_id: str) -> dict: ...
    @abstractmethod
    def cancel(self, run_id: str) -> dict: ...
    @abstractmethod
    def collect(self, run_id: str) -> dict: ...

class CommandTemplateAdapter(ProviderAdapter):
    """
    Reference sidecar adapter.
    It requires an operator-supplied command template and does NOT assume
    any unverified Hermes CLI command or flag.
    """
    def __init__(self, identity: WorkerIdentity, command_template: list[str], capabilities_dict=None):
        self._identity=identity
        self.command_template=command_template
        self._caps=capabilities_dict or {}
        self.runs={}

    def identity(self): return self._identity
    def capabilities(self): return dict(self._caps)

    def launch(self,capsule_path,lease):
        run_id="RUN-"+uuid.uuid4().hex
        values={"capsule_path":str(capsule_path),"lease_id":lease["lease_id"],"run_id":run_id}
        cmd=[part.format(**values) for part in self.command_template]
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.runs[run_id]=proc
        return {"run_id":run_id,"pid":proc.pid,"command":cmd}

    def status(self,run_id):
        p=self.runs[run_id]
        rc=p.poll()
        return {"run_id":run_id,"status":"RUNNING" if rc is None else "EXITED","returncode":rc}

    def cancel(self,run_id):
        p=self.runs[run_id]
        if p.poll() is None: p.terminate()
        return {"run_id":run_id,"cancelled":True}

    def collect(self,run_id):
        p=self.runs[run_id]
        out,err=p.communicate()
        return {"run_id":run_id,"returncode":p.returncode,"stdout":out,"stderr":err}
