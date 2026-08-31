import hashlib
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from hermes_factory.ledger import Ledger
from hermes_factory.staging import stage_artifact, verify_staged_artifact


def manifest(wid="W1"):
    return {"work_id":wid,"work_type":"PRIMARY","source_unit_id":"SU","priority":"P1"}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.db = Path(self.td.name)/"ledger.sqlite"
        self.l = Ledger(self.db)
        self.l.register_work(manifest())

    def tearDown(self):
        self.l.close(); self.td.cleanup()

    def test_register_becomes_ready(self):
        self.assertEqual(self.l.get_work("W1")["state"], "READY")

    def test_duplicate_active_lease_rejected(self):
        self.l.issue_lease("W1","A")
        with self.assertRaises(RuntimeError):
            self.l.issue_lease("W1","B")

    def test_illegal_direct_accept_rejected(self):
        with self.assertRaises(RuntimeError):
            self.l.transition("W1","ACCEPTED",expected_state="READY")

    def test_expired_lease_requeues(self):
        lid=self.l.issue_lease("W1","A",ttl_seconds=1)
        self.l.db.execute("UPDATE leases SET expires_at=? WHERE lease_id=?",(time.time()-10,lid))
        n=self.l.expire_leases()
        self.assertEqual(n,1)
        self.assertEqual(self.l.get_work("W1")["state"],"READY")

    def _full_commit(self):
        lid=self.l.issue_lease("W1","A")
        self.l.mark_running("W1",lid)
        staged=stage_artifact(Path(self.td.name)/"staging",work_id="W1",run_id="R1",files={"out.json":{"ok":True}})
        aid=self.l.register_staged_artifact("W1",lid,"R1",staged["path"],staged["manifest_sha256"])
        self.l.begin_validation("W1",lid,aid)
        ver=verify_staged_artifact(Path(staged["path"]))
        self.assertTrue(ver["ok"])
        cid,v=self.l.commit_validated("W1",lid,aid,expected_parent_version=0,expected_manifest_sha256=ver["manifest_sha256"],run_id="R1")
        return lid,aid,cid,v

    def test_atomic_commit_and_reconciliation(self):
        _,_,_,v=self._full_commit()
        self.assertEqual(v,1)
        snap=self.l.snapshot()
        self.assertTrue(snap["event_chain_valid"])
        self.assertTrue(snap["state_reconciliation_valid"])
        self.assertEqual(self.l.get_work("W1")["state"],"ACCEPTED")

    def test_stale_commit_rejected(self):
        self._full_commit()
        with self.assertRaises(RuntimeError):
            self.l.transition("W1","SUPERSEDED",expected_state="ACCEPTED",expected_version=0)

    def test_old_worker_after_expiry_rejected(self):
        lid=self.l.issue_lease("W1","OLD",ttl_seconds=1)
        self.l.mark_running("W1",lid)
        self.l.db.execute("UPDATE leases SET expires_at=? WHERE lease_id=?",(time.time()-10,lid))
        self.l.expire_leases()
        new=self.l.issue_lease("W1","NEW")
        with self.assertRaises(RuntimeError):
            self.l.mark_running("W1",lid)
        self.l.mark_running("W1",new)

    def test_event_tamper_detected(self):
        self.l.issue_lease("W1","A")
        row=self.l.db.execute("SELECT seq FROM events ORDER BY seq LIMIT 1").fetchone()
        self.l.db.execute("UPDATE events SET body_json='{}' WHERE seq=?",(row["seq"],))
        ok,err=self.l.verify_event_chain()
        self.assertFalse(ok); self.assertTrue(err)

    def test_state_table_tamper_detected(self):
        self.l.db.execute("UPDATE work_items SET state='ACCEPTED' WHERE work_id='W1'")
        ok,err=self.l.verify_state_reconciliation()
        self.assertFalse(ok)
        self.assertTrue(any("state_history_divergence" in x or "accepted_without_commit" in x for x in err))

    def test_restart_reconstructs(self):
        self._full_commit()
        snap1=self.l.snapshot()
        self.l.close()
        self.l=Ledger(self.db)
        snap2=self.l.snapshot()
        self.assertTrue(snap2["event_chain_valid"])
        self.assertTrue(snap2["state_reconciliation_valid"])
        self.assertEqual([(x["work_id"],x["state"],x["version"]) for x in snap1["work_items"]],[(x["work_id"],x["state"],x["version"]) for x in snap2["work_items"]])

    def test_two_controllers_race_one_lease_wins(self):
        self.l.close()
        barrier=threading.Barrier(2)
        results=[]
        lock=threading.Lock()
        def worker(name):
            l=Ledger(self.db)
            try:
                barrier.wait()
                try:
                    lid=l.issue_lease("W1",name)
                    val=("ok",lid)
                except Exception as e:
                    val=("err",str(e))
                with lock: results.append(val)
            finally: l.close()
        t1=threading.Thread(target=worker,args=("A",)); t2=threading.Thread(target=worker,args=("B",))
        t1.start();t2.start();t1.join();t2.join()
        self.l=Ledger(self.db)
        self.assertEqual(sum(x[0]=="ok" for x in results),1)
        self.assertEqual(sum(x[0]=="err" for x in results),1)


class StagingTests(unittest.TestCase):
    def test_complete_stage_verifies(self):
        with tempfile.TemporaryDirectory() as td:
            s=stage_artifact(Path(td),work_id="W",run_id="R",files={"a.txt":"abc","nested/b.json":{"x":1}})
            self.assertTrue(verify_staged_artifact(Path(s["path"]))["ok"])

    def test_torn_stage_missing_completion_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"R";p.mkdir();(p/"a.txt").write_text("x");(p/"ARTIFACT_MANIFEST.json").write_text(json.dumps({"files":[]}))
            r=verify_staged_artifact(p)
            self.assertFalse(r["ok"]);self.assertIn("missing_completion_receipt",r["errors"])

    def test_post_stage_artifact_mutation_fails(self):
        with tempfile.TemporaryDirectory() as td:
            s=stage_artifact(Path(td),work_id="W",run_id="R",files={"a.txt":"abc"})
            (Path(s["path"])/"a.txt").write_text("changed")
            r=verify_staged_artifact(Path(s["path"]))
            self.assertFalse(r["ok"])
            self.assertTrue(any("hash_mismatch" in x or "size_mismatch" in x for x in r["errors"]))


if __name__ == "__main__": unittest.main()
