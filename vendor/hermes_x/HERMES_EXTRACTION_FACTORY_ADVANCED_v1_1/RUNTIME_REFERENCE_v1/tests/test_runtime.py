from pathlib import Path
import tempfile, json, hashlib, time, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ledger import Ledger
from scheduler import Scheduler

def manifest(cid,ctype="EXTRACTION_CAPSULE",priority="P2"):
    return {"capsule_id":cid,"capsule_type":ctype,"work_class":"W2","source_class":"S1","priority":priority}

with tempfile.TemporaryDirectory() as td:
    db=Path(td)/"ledger.sqlite"
    l=Ledger(db)
    l.register_capsule(manifest("CAP-A",priority="P1"))
    l.register_capsule(manifest("CAP-B",priority="P2"))
    s=Scheduler(l)

    # priority scheduling
    cid,lease=s.claim_next("worker-1")
    assert cid=="CAP-A"
    l.mark_running(lease)

    # duplicate lease forbidden
    try:
        l.issue_lease("CAP-A","worker-2")
        raise AssertionError("duplicate lease was allowed")
    except RuntimeError:
        pass

    # commit with CAS
    art=hashlib.sha256(b"artifact").hexdigest()
    commit,newv=l.commit("CAP-A",0,art,"RUN-1",lease)
    assert newv==1 and l.get_capsule("CAP-A")["state"]=="ACCEPTED"

    # stale out-of-order commit forbidden
    try:
        l.commit("CAP-A",0,hashlib.sha256(b"stale").hexdigest(),"RUN-stale")
        raise AssertionError("stale commit was allowed")
    except RuntimeError as e:
        assert "stale_parent_version" in str(e)

    # lease expiry returns work to READY
    cid2,lease2=s.claim_next("worker-2",ttl_seconds=1)
    assert cid2=="CAP-B"
    l.db.execute("UPDATE leases SET expires_at=? WHERE lease_id=?",(time.time()-10,lease2)); l.db.commit()
    rec=s.recovery_pass()
    assert rec["expired_leases_requeued"]==1
    assert l.get_capsule("CAP-B")["state"]=="READY"

    # event chain valid before restart
    assert l.verify_event_chain()
    state1=l.reconstruct()
    l.close()

    # exact disk restart reconstruction
    l2=Ledger(db)
    state2=l2.reconstruct()
    assert state2["event_chain_valid"]
    assert [(c["capsule_id"],c["state"],c["version"]) for c in state1["capsules"]] == \
           [(c["capsule_id"],c["state"],c["version"]) for c in state2["capsules"]]
    l2.close()

print("RUNTIME_REFERENCE_TESTS: PASS")
