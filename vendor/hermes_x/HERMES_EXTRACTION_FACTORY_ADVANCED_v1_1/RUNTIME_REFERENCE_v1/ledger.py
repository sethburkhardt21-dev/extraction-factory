from __future__ import annotations
import sqlite3, json, hashlib, time, uuid
from pathlib import Path

TERMINAL = {"ACCEPTED","FAILED_ESCALATE","DEFERRED","CANCELLED","SUPERSEDED"}

def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False)

def _hash_event(prev_hash, body):
    return hashlib.sha256((prev_hash + _canon(body)).encode("utf-8")).hexdigest()

class Ledger:
    def __init__(self, path):
        self.path=str(path)
        self.db=sqlite3.connect(self.path)
        self.db.row_factory=sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self._init()

    def _init(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS capsules(
            capsule_id TEXT PRIMARY KEY,
            capsule_type TEXT NOT NULL,
            work_class TEXT NOT NULL,
            source_class TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'P2',
            state TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 0,
            manifest_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leases(
            lease_id TEXT PRIMARY KEY,
            capsule_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            status TEXT NOT NULL,
            issued_at REAL NOT NULL,
            heartbeat_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            FOREIGN KEY(capsule_id) REFERENCES capsules(capsule_id)
        );
        CREATE TABLE IF NOT EXISTS events(
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            prior_version INTEGER,
            resulting_version INTEGER,
            body_json TEXT NOT NULL,
            prev_event_hash TEXT NOT NULL,
            event_hash TEXT UNIQUE NOT NULL,
            ts REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS commits(
            commit_id TEXT PRIMARY KEY,
            capsule_id TEXT NOT NULL,
            parent_version INTEGER NOT NULL,
            resulting_version INTEGER NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            run_id TEXT NOT NULL,
            committed_at REAL NOT NULL,
            FOREIGN KEY(capsule_id) REFERENCES capsules(capsule_id)
        );
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def _last_event_hash(self):
        r=self.db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return r["event_hash"] if r else "GENESIS"

    def append_event(self, entity_type, entity_id, event_type, prior_version=None, resulting_version=None, detail=None):
        detail=detail or {}
        body={"entity_type":entity_type,"entity_id":entity_id,"event_type":event_type,
              "prior_version":prior_version,"resulting_version":resulting_version,"detail":detail}
        prev=self._last_event_hash()
        eh=_hash_event(prev,body)
        eid="EVT-"+uuid.uuid4().hex
        self.db.execute("""INSERT INTO events(event_id,entity_type,entity_id,event_type,prior_version,resulting_version,
                          body_json,prev_event_hash,event_hash,ts) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (eid,entity_type,entity_id,event_type,prior_version,resulting_version,_canon(body),prev,eh,time.time()))
        self.db.commit()
        return eid,eh

    def verify_event_chain(self):
        prev="GENESIS"
        for r in self.db.execute("SELECT * FROM events ORDER BY seq"):
            body=json.loads(r["body_json"])
            expect=_hash_event(prev,body)
            if r["prev_event_hash"] != prev or r["event_hash"] != expect:
                return False
            prev=r["event_hash"]
        return True

    def register_capsule(self, manifest):
        now=time.time()
        cid=manifest["capsule_id"]
        self.db.execute("""INSERT INTO capsules(capsule_id,capsule_type,work_class,source_class,priority,state,version,
                         manifest_json,created_at,updated_at) VALUES(?,?,?,?,?,'READY',0,?,?,?)""",
                        (cid,manifest["capsule_type"],manifest["work_class"],manifest["source_class"],
                         manifest.get("priority","P2"),_canon(manifest),now,now))
        self.db.commit()
        self.append_event("CAPSULE",cid,"REGISTERED",None,0,{"state":"READY"})

    def get_capsule(self,capsule_id):
        r=self.db.execute("SELECT * FROM capsules WHERE capsule_id=?",(capsule_id,)).fetchone()
        return dict(r) if r else None

    def issue_lease(self,capsule_id,worker_id,ttl_seconds=900):
        c=self.get_capsule(capsule_id)
        if not c or c["state"]!="READY":
            raise RuntimeError("capsule_not_ready")
        active=self.db.execute("SELECT 1 FROM leases WHERE capsule_id=? AND status='ACTIVE'",(capsule_id,)).fetchone()
        if active:
            raise RuntimeError("active_lease_exists")
        now=time.time(); lid="LEASE-"+uuid.uuid4().hex
        self.db.execute("INSERT INTO leases VALUES(?,?,?,?,?,?,?)",
                        (lid,capsule_id,worker_id,"ACTIVE",now,now,now+ttl_seconds))
        self.db.execute("UPDATE capsules SET state='LEASED',updated_at=? WHERE capsule_id=?",(now,capsule_id))
        self.db.commit()
        self.append_event("LEASE",lid,"ISSUED",c["version"],c["version"],{"capsule_id":capsule_id,"worker_id":worker_id})
        return lid

    def heartbeat(self,lease_id,ttl_seconds=900):
        now=time.time()
        r=self.db.execute("SELECT * FROM leases WHERE lease_id=? AND status='ACTIVE'",(lease_id,)).fetchone()
        if not r: raise RuntimeError("lease_not_active")
        self.db.execute("UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?",(now,now+ttl_seconds,lease_id))
        self.db.commit()

    def mark_running(self,lease_id):
        r=self.db.execute("SELECT * FROM leases WHERE lease_id=? AND status='ACTIVE'",(lease_id,)).fetchone()
        if not r: raise RuntimeError("lease_not_active")
        self.db.execute("UPDATE capsules SET state='RUNNING',updated_at=? WHERE capsule_id=?",(time.time(),r["capsule_id"]))
        self.db.commit()
        c=self.get_capsule(r["capsule_id"])
        self.append_event("CAPSULE",r["capsule_id"],"RUNNING",c["version"],c["version"],{"lease_id":lease_id})

    def expire_leases(self, now=None):
        now=now or time.time()
        rows=self.db.execute("SELECT * FROM leases WHERE status='ACTIVE' AND expires_at < ?",(now,)).fetchall()
        for r in rows:
            self.db.execute("UPDATE leases SET status='EXPIRED' WHERE lease_id=?",(r["lease_id"],))
            c=self.get_capsule(r["capsule_id"])
            if c and c["state"] not in TERMINAL:
                self.db.execute("UPDATE capsules SET state='READY',updated_at=? WHERE capsule_id=?",(time.time(),r["capsule_id"]))
            self.db.commit()
            self.append_event("LEASE",r["lease_id"],"EXPIRED",c["version"] if c else None,c["version"] if c else None,
                              {"capsule_id":r["capsule_id"]})
        return len(rows)

    def commit(self,capsule_id,expected_parent_version,artifact_sha256,run_id,lease_id=None):
        c=self.get_capsule(capsule_id)
        if not c: raise RuntimeError("unknown_capsule")
        if c["version"] != expected_parent_version:
            raise RuntimeError("stale_parent_version")
        if lease_id:
            lr=self.db.execute("SELECT * FROM leases WHERE lease_id=? AND capsule_id=? AND status='ACTIVE'",
                               (lease_id,capsule_id)).fetchone()
            if not lr: raise RuntimeError("lease_not_active")
        newv=expected_parent_version+1
        now=time.time(); commit_id="COMMIT-"+uuid.uuid4().hex
        self.db.execute("BEGIN IMMEDIATE")
        row=self.db.execute("SELECT version FROM capsules WHERE capsule_id=?",(capsule_id,)).fetchone()
        if row["version"] != expected_parent_version:
            self.db.rollback(); raise RuntimeError("stale_parent_version")
        self.db.execute("UPDATE capsules SET version=?,state='ACCEPTED',updated_at=? WHERE capsule_id=?",
                        (newv,now,capsule_id))
        self.db.execute("INSERT INTO commits VALUES(?,?,?,?,?,?,?)",
                        (commit_id,capsule_id,expected_parent_version,newv,artifact_sha256,run_id,now))
        if lease_id:
            self.db.execute("UPDATE leases SET status='COMPLETED' WHERE lease_id=?",(lease_id,))
        self.db.commit()
        self.append_event("CAPSULE",capsule_id,"COMMITTED",expected_parent_version,newv,
                          {"artifact_sha256":artifact_sha256,"run_id":run_id,"commit_id":commit_id})
        return commit_id,newv

    def reconstruct(self):
        caps=[dict(r) for r in self.db.execute("SELECT * FROM capsules ORDER BY capsule_id")]
        leases=[dict(r) for r in self.db.execute("SELECT * FROM leases ORDER BY issued_at")]
        return {"capsules":caps,"leases":leases,"event_chain_valid":self.verify_event_chain()}
