from pathlib import Path
import json, time
from ledger import Ledger

PRIORITY_ORDER={"P0":0,"P1":1,"P2":2,"P3":3}

class Scheduler:
    def __init__(self, ledger):
        self.ledger=ledger

    def ready_capsules(self):
        rows=self.ledger.db.execute("SELECT * FROM capsules WHERE state='READY'").fetchall()
        out=[dict(r) for r in rows]
        return sorted(out,key=lambda x:(PRIORITY_ORDER.get(x["priority"],9),x["created_at"],x["capsule_id"]))

    def claim_next(self, worker_id, eligible_types=None, ttl_seconds=900):
        for c in self.ready_capsules():
            if eligible_types and c["capsule_type"] not in eligible_types:
                continue
            lid=self.ledger.issue_lease(c["capsule_id"],worker_id,ttl_seconds)
            return c["capsule_id"],lid
        return None,None

    def recovery_pass(self):
        expired=self.ledger.expire_leases()
        state=self.ledger.reconstruct()
        if not state["event_chain_valid"]:
            raise RuntimeError("event_chain_integrity_failure")
        return {"expired_leases_requeued":expired,"capsules":len(state["capsules"])}
