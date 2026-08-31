from __future__ import annotations
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from .hashing import canonical_json, sha256_text
from .models import WorkState

ALLOWED_TRANSITIONS = {
    WorkState.REGISTERED.value: {WorkState.READY.value, WorkState.CANCELLED.value},
    WorkState.READY.value: {WorkState.LEASED.value, WorkState.CANCELLED.value},
    WorkState.LEASED.value: {WorkState.RUNNING.value, WorkState.READY.value, WorkState.CANCELLED.value},
    WorkState.RUNNING.value: {WorkState.STAGED.value, WorkState.RETRY.value, WorkState.ESCALATE.value, WorkState.DEFERRED.value, WorkState.FAILED.value, WorkState.CANCELLED.value},
    WorkState.STAGED.value: {WorkState.VALIDATING.value, WorkState.RETRY.value, WorkState.FAILED.value, WorkState.CANCELLED.value},
    WorkState.VALIDATING.value: {WorkState.ACCEPTED.value, WorkState.RETRY.value, WorkState.ESCALATE.value, WorkState.DEFERRED.value, WorkState.FAILED.value, WorkState.CANCELLED.value},
    WorkState.RETRY.value: {WorkState.READY.value, WorkState.CANCELLED.value},
    WorkState.ESCALATE.value: {WorkState.READY.value, WorkState.DEFERRED.value, WorkState.CANCELLED.value},
    WorkState.DEFERRED.value: {WorkState.READY.value, WorkState.CANCELLED.value},
    WorkState.ACCEPTED.value: {WorkState.SUPERSEDED.value},
    WorkState.FAILED.value: set(),
    WorkState.SUPERSEDED.value: set(),
    WorkState.CANCELLED.value: set(),
}

ACTIVE_STATES = {
    WorkState.LEASED.value, WorkState.RUNNING.value, WorkState.STAGED.value, WorkState.VALIDATING.value
}


def _event_hash(prev_hash: str, body: Dict[str, Any]) -> str:
    return sha256_text(prev_hash + canonical_json(body))


class Ledger:
    """Durable deterministic work-state authority.

    Semantic workers never receive a direct database handle. All accepted state
    changes pass through this controller-facing API with legal-state and CAS checks.
    """

    def __init__(self, path: Path | str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=30000")
        self._init()

    def _init(self) -> None:
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS work_items(
            work_id TEXT PRIMARY KEY,
            work_type TEXT NOT NULL,
            source_unit_id TEXT,
            priority TEXT NOT NULL,
            state TEXT NOT NULL,
            version INTEGER NOT NULL,
            manifest_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leases(
            lease_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            status TEXT NOT NULL,
            issued_at REAL NOT NULL,
            heartbeat_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            FOREIGN KEY(work_id) REFERENCES work_items(work_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_lease_per_work
            ON leases(work_id) WHERE status='ACTIVE';
        CREATE TABLE IF NOT EXISTS events(
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            prior_state TEXT,
            resulting_state TEXT,
            prior_version INTEGER,
            resulting_version INTEGER,
            body_json TEXT NOT NULL,
            prev_event_hash TEXT NOT NULL,
            event_hash TEXT UNIQUE NOT NULL,
            ts REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS artifacts(
            artifact_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            staging_path TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY(work_id) REFERENCES work_items(work_id)
        );
        CREATE TABLE IF NOT EXISTS commits(
            commit_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            parent_version INTEGER NOT NULL,
            resulting_version INTEGER NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            run_id TEXT NOT NULL,
            committed_at REAL NOT NULL,
            FOREIGN KEY(work_id) REFERENCES work_items(work_id),
            FOREIGN KEY(artifact_id) REFERENCES artifacts(artifact_id)
        );
        """)

    @contextmanager
    def txn(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def close(self) -> None:
        self.db.close()

    def _last_event_hash_txn(self) -> str:
        row = self.db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return row["event_hash"] if row else "GENESIS"

    def _append_event_txn(self, *, entity_type: str, entity_id: str, event_type: str,
                          prior_state: Optional[str], resulting_state: Optional[str],
                          prior_version: Optional[int], resulting_version: Optional[int],
                          detail: Optional[Dict[str, Any]] = None) -> tuple[str, str]:
        ts = time.time()
        body = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_type": event_type,
            "prior_state": prior_state,
            "resulting_state": resulting_state,
            "prior_version": prior_version,
            "resulting_version": resulting_version,
            "detail": detail or {},
            "ts": ts,
        }
        prev = self._last_event_hash_txn()
        eh = _event_hash(prev, body)
        eid = "EVT-" + uuid.uuid4().hex
        self.db.execute(
            """INSERT INTO events(event_id,entity_type,entity_id,event_type,prior_state,resulting_state,
               prior_version,resulting_version,body_json,prev_event_hash,event_hash,ts)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, entity_type, entity_id, event_type, prior_state, resulting_state,
             prior_version, resulting_version, canonical_json(body), prev, eh, ts),
        )
        return eid, eh

    def register_work(self, manifest: Dict[str, Any]) -> str:
        work_id = manifest["work_id"]
        now = time.time()
        with self.txn():
            self.db.execute(
                """INSERT INTO work_items(work_id,work_type,source_unit_id,priority,state,version,manifest_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,0,?,?,?)""",
                (work_id, manifest["work_type"], manifest.get("source_unit_id"), manifest.get("priority", "P2"),
                 WorkState.REGISTERED.value, canonical_json(manifest), now, now),
            )
            self._append_event_txn(entity_type="WORK", entity_id=work_id, event_type="REGISTERED",
                                   prior_state=None, resulting_state=WorkState.REGISTERED.value,
                                   prior_version=None, resulting_version=0, detail={"manifest": manifest})
        self.transition(work_id, WorkState.READY.value, expected_state=WorkState.REGISTERED.value, expected_version=0,
                        detail={"reason": "registration_complete"})
        return work_id

    def get_work(self, work_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.execute("SELECT * FROM work_items WHERE work_id=?", (work_id,)).fetchone()
        return dict(row) if row else None

    def list_work(self, state: Optional[str] = None) -> list[Dict[str, Any]]:
        if state:
            rows = self.db.execute("SELECT * FROM work_items WHERE state=? ORDER BY created_at,work_id", (state,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM work_items ORDER BY created_at,work_id").fetchall()
        return [dict(r) for r in rows]

    def transition(self, work_id: str, new_state: str, *, expected_state: Optional[str] = None,
                   expected_version: Optional[int] = None, detail: Optional[Dict[str, Any]] = None,
                   bump_version: bool = False) -> int:
        if new_state not in WorkState._value2member_map_:
            raise RuntimeError("unknown_target_state")
        with self.txn():
            row = self.db.execute("SELECT * FROM work_items WHERE work_id=?", (work_id,)).fetchone()
            if not row:
                raise RuntimeError("unknown_work")
            old_state, old_version = row["state"], row["version"]
            if expected_state is not None and old_state != expected_state:
                raise RuntimeError(f"unexpected_state:{old_state}")
            if expected_version is not None and old_version != expected_version:
                raise RuntimeError("stale_parent_version")
            if new_state not in ALLOWED_TRANSITIONS.get(old_state, set()):
                raise RuntimeError(f"illegal_state_transition:{old_state}->{new_state}")
            new_version = old_version + 1 if bump_version else old_version
            now = time.time()
            self.db.execute("UPDATE work_items SET state=?,version=?,updated_at=? WHERE work_id=?",
                            (new_state, new_version, now, work_id))
            self._append_event_txn(entity_type="WORK", entity_id=work_id, event_type="STATE_TRANSITION",
                                   prior_state=old_state, resulting_state=new_state,
                                   prior_version=old_version, resulting_version=new_version, detail=detail)
            return new_version

    def issue_lease(self, work_id: str, worker_id: str, ttl_seconds: int = 900) -> str:
        now = time.time()
        with self.txn():
            row = self.db.execute("SELECT * FROM work_items WHERE work_id=?", (work_id,)).fetchone()
            if not row:
                raise RuntimeError("unknown_work")
            if row["state"] != WorkState.READY.value:
                raise RuntimeError("work_not_ready")
            active = self.db.execute("SELECT 1 FROM leases WHERE work_id=? AND status='ACTIVE'", (work_id,)).fetchone()
            if active:
                raise RuntimeError("active_lease_exists")
            lease_id = "LEASE-" + uuid.uuid4().hex
            self.db.execute("INSERT INTO leases VALUES(?,?,?,?,?,?,?)",
                            (lease_id, work_id, worker_id, "ACTIVE", now, now, now + ttl_seconds))
            self.db.execute("UPDATE work_items SET state=?,updated_at=? WHERE work_id=?",
                            (WorkState.LEASED.value, now, work_id))
            self._append_event_txn(entity_type="WORK", entity_id=work_id, event_type="LEASE_ISSUED",
                                   prior_state=WorkState.READY.value, resulting_state=WorkState.LEASED.value,
                                   prior_version=row["version"], resulting_version=row["version"],
                                   detail={"lease_id": lease_id, "worker_id": worker_id, "expires_at": now + ttl_seconds})
            return lease_id

    def heartbeat(self, lease_id: str, ttl_seconds: int = 900) -> None:
        now = time.time()
        with self.txn():
            row = self.db.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
            if not row or row["status"] != "ACTIVE":
                raise RuntimeError("lease_not_active")
            if row["expires_at"] < now:
                raise RuntimeError("lease_expired")
            self.db.execute("UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?",
                            (now, now + ttl_seconds, lease_id))
            self._append_event_txn(entity_type="LEASE", entity_id=lease_id, event_type="HEARTBEAT",
                                   prior_state="ACTIVE", resulting_state="ACTIVE", prior_version=None, resulting_version=None,
                                   detail={"work_id": row["work_id"], "expires_at": now + ttl_seconds})

    def mark_running(self, work_id: str, lease_id: str) -> None:
        with self.txn():
            row = self.db.execute("SELECT * FROM work_items WHERE work_id=?", (work_id,)).fetchone()
            lease = self.db.execute("SELECT * FROM leases WHERE lease_id=? AND work_id=?", (lease_id, work_id)).fetchone()
            if not row or not lease or lease["status"] != "ACTIVE":
                raise RuntimeError("lease_not_active")
            if lease["expires_at"] < time.time():
                raise RuntimeError("lease_expired")
            if row["state"] != WorkState.LEASED.value:
                raise RuntimeError("work_not_leased")
            self.db.execute("UPDATE work_items SET state=?,updated_at=? WHERE work_id=?",
                            (WorkState.RUNNING.value, time.time(), work_id))
            self._append_event_txn(entity_type="WORK", entity_id=work_id, event_type="RUNNING",
                                   prior_state=WorkState.LEASED.value, resulting_state=WorkState.RUNNING.value,
                                   prior_version=row["version"], resulting_version=row["version"],
                                   detail={"lease_id": lease_id})

    def register_staged_artifact(self, work_id: str, lease_id: str, run_id: str, staging_path: str,
                                 manifest_sha256: str) -> str:
        with self.txn():
            row = self.db.execute("SELECT * FROM work_items WHERE work_id=?", (work_id,)).fetchone()
            lease = self.db.execute("SELECT * FROM leases WHERE lease_id=? AND work_id=?", (lease_id, work_id)).fetchone()
            if not row or row["state"] != WorkState.RUNNING.value:
                raise RuntimeError("work_not_running")
            if not lease or lease["status"] != "ACTIVE" or lease["expires_at"] < time.time():
                raise RuntimeError("lease_not_active")
            artifact_id = "ART-" + uuid.uuid4().hex
            now = time.time()
            self.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
                            (artifact_id, work_id, run_id, staging_path, manifest_sha256, "STAGED", now))
            self.db.execute("UPDATE work_items SET state=?,updated_at=? WHERE work_id=?",
                            (WorkState.STAGED.value, now, work_id))
            self._append_event_txn(entity_type="WORK", entity_id=work_id, event_type="ARTIFACT_STAGED",
                                   prior_state=WorkState.RUNNING.value, resulting_state=WorkState.STAGED.value,
                                   prior_version=row["version"], resulting_version=row["version"],
                                   detail={"artifact_id": artifact_id, "manifest_sha256": manifest_sha256, "run_id": run_id})
            return artifact_id

    def begin_validation(self, work_id: str, lease_id: str, artifact_id: str) -> None:
        with self.txn():
            row = self.db.execute("SELECT * FROM work_items WHERE work_id=?", (work_id,)).fetchone()
            lease = self.db.execute("SELECT * FROM leases WHERE lease_id=? AND work_id=?", (lease_id, work_id)).fetchone()
            art = self.db.execute("SELECT * FROM artifacts WHERE artifact_id=? AND work_id=?", (artifact_id, work_id)).fetchone()
            if not row or row["state"] != WorkState.STAGED.value:
                raise RuntimeError("work_not_staged")
            if not lease or lease["status"] != "ACTIVE" or lease["expires_at"] < time.time():
                raise RuntimeError("lease_not_active")
            if not art or art["status"] != "STAGED":
                raise RuntimeError("artifact_not_staged")
            self.db.execute("UPDATE artifacts SET status='VALIDATING' WHERE artifact_id=?", (artifact_id,))
            self.db.execute("UPDATE work_items SET state=?,updated_at=? WHERE work_id=?",
                            (WorkState.VALIDATING.value, time.time(), work_id))
            self._append_event_txn(entity_type="WORK", entity_id=work_id, event_type="VALIDATION_STARTED",
                                   prior_state=WorkState.STAGED.value, resulting_state=WorkState.VALIDATING.value,
                                   prior_version=row["version"], resulting_version=row["version"],
                                   detail={"artifact_id": artifact_id, "lease_id": lease_id})

    def commit_validated(self, work_id: str, lease_id: str, artifact_id: str, *, expected_parent_version: int,
                         expected_manifest_sha256: str, run_id: str) -> tuple[str, int]:
        with self.txn():
            row = self.db.execute("SELECT * FROM work_items WHERE work_id=?", (work_id,)).fetchone()
            lease = self.db.execute("SELECT * FROM leases WHERE lease_id=? AND work_id=?", (lease_id, work_id)).fetchone()
            art = self.db.execute("SELECT * FROM artifacts WHERE artifact_id=? AND work_id=?", (artifact_id, work_id)).fetchone()
            if not row:
                raise RuntimeError("unknown_work")
            if row["state"] != WorkState.VALIDATING.value:
                raise RuntimeError("work_not_validating")
            if row["version"] != expected_parent_version:
                raise RuntimeError("stale_parent_version")
            if not lease or lease["status"] != "ACTIVE" or lease["expires_at"] < time.time():
                raise RuntimeError("lease_not_active")
            if not art or art["status"] != "VALIDATING":
                raise RuntimeError("artifact_not_validating")
            if art["manifest_sha256"] != expected_manifest_sha256:
                raise RuntimeError("artifact_manifest_mismatch")
            new_version = expected_parent_version + 1
            commit_id = "COMMIT-" + uuid.uuid4().hex
            now = time.time()
            self.db.execute("INSERT INTO commits VALUES(?,?,?,?,?,?,?,?)",
                            (commit_id, work_id, artifact_id, expected_parent_version, new_version,
                             expected_manifest_sha256, run_id, now))
            self.db.execute("UPDATE artifacts SET status='ACCEPTED' WHERE artifact_id=?", (artifact_id,))
            self.db.execute("UPDATE leases SET status='COMPLETED' WHERE lease_id=?", (lease_id,))
            self.db.execute("UPDATE work_items SET state=?,version=?,updated_at=? WHERE work_id=?",
                            (WorkState.ACCEPTED.value, new_version, now, work_id))
            self._append_event_txn(entity_type="WORK", entity_id=work_id, event_type="COMMITTED",
                                   prior_state=WorkState.VALIDATING.value, resulting_state=WorkState.ACCEPTED.value,
                                   prior_version=expected_parent_version, resulting_version=new_version,
                                   detail={"commit_id": commit_id, "artifact_id": artifact_id,
                                           "manifest_sha256": expected_manifest_sha256, "run_id": run_id})
            return commit_id, new_version


    def abandon_active_work(self, work_id: str, lease_id: str, *, target_state: str = WorkState.RETRY.value, reason: str = "worker_failure") -> None:
        if target_state not in {WorkState.RETRY.value, WorkState.ESCALATE.value, WorkState.DEFERRED.value, WorkState.FAILED.value, WorkState.CANCELLED.value}:
            raise RuntimeError("invalid_abandon_target")
        with self.txn():
            row = self.db.execute("SELECT * FROM work_items WHERE work_id=?", (work_id,)).fetchone()
            lease = self.db.execute("SELECT * FROM leases WHERE lease_id=? AND work_id=?", (lease_id, work_id)).fetchone()
            if not row or row["state"] not in ACTIVE_STATES:
                raise RuntimeError("work_not_active")
            if not lease or lease["status"] != "ACTIVE":
                raise RuntimeError("lease_not_active")
            if target_state not in ALLOWED_TRANSITIONS.get(row["state"], set()):
                raise RuntimeError(f"illegal_state_transition:{row['state']}->{target_state}")
            self.db.execute("UPDATE leases SET status='ABANDONED' WHERE lease_id=?", (lease_id,))
            self.db.execute("UPDATE work_items SET state=?,updated_at=? WHERE work_id=?", (target_state, time.time(), work_id))
            self._append_event_txn(entity_type="WORK", entity_id=work_id, event_type="WORK_ABANDONED",
                                   prior_state=row["state"], resulting_state=target_state,
                                   prior_version=row["version"], resulting_version=row["version"],
                                   detail={"lease_id": lease_id, "reason": reason})

    def expire_leases(self, now: Optional[float] = None) -> int:
        now = now if now is not None else time.time()
        with self.txn():
            rows = self.db.execute("SELECT * FROM leases WHERE status='ACTIVE' AND expires_at < ?", (now,)).fetchall()
            count = 0
            for lease in rows:
                work = self.db.execute("SELECT * FROM work_items WHERE work_id=?", (lease["work_id"],)).fetchone()
                self.db.execute("UPDATE leases SET status='EXPIRED' WHERE lease_id=?", (lease["lease_id"],))
                if work and work["state"] in ACTIVE_STATES:
                    self.db.execute("UPDATE work_items SET state=?,updated_at=? WHERE work_id=?",
                                    (WorkState.READY.value, now, lease["work_id"]))
                    self._append_event_txn(entity_type="WORK", entity_id=lease["work_id"], event_type="LEASE_EXPIRED_REQUEUE",
                                           prior_state=work["state"], resulting_state=WorkState.READY.value,
                                           prior_version=work["version"], resulting_version=work["version"],
                                           detail={"lease_id": lease["lease_id"]})
                count += 1
            return count

    def verify_event_chain(self) -> tuple[bool, list[str]]:
        prev = "GENESIS"
        errors: list[str] = []
        rows = self.db.execute("SELECT * FROM events ORDER BY seq").fetchall()
        for row in rows:
            try:
                body = json.loads(row["body_json"])
            except Exception:
                errors.append(f"event_json_invalid:{row['seq']}")
                continue
            expected = _event_hash(prev, body)
            if row["prev_event_hash"] != prev:
                errors.append(f"prev_hash_mismatch:{row['seq']}")
            if row["event_hash"] != expected:
                errors.append(f"event_hash_mismatch:{row['seq']}")
            prev = row["event_hash"]
        return not errors, errors

    def replay_work_state(self) -> Dict[str, Dict[str, Any]]:
        replay: Dict[str, Dict[str, Any]] = {}
        for row in self.db.execute("SELECT * FROM events WHERE entity_type='WORK' ORDER BY seq"):
            body = json.loads(row["body_json"])
            wid = row["entity_id"]
            replay[wid] = {
                "state": body.get("resulting_state"),
                "version": body.get("resulting_version"),
            }
        return replay

    def verify_state_reconciliation(self) -> tuple[bool, list[str]]:
        errors: list[str] = []
        chain_ok, chain_errors = self.verify_event_chain()
        errors.extend(chain_errors)
        replay = self.replay_work_state()
        for row in self.db.execute("SELECT * FROM work_items"):
            expected = replay.get(row["work_id"])
            if not expected:
                errors.append(f"work_missing_event_history:{row['work_id']}")
                continue
            if expected["state"] != row["state"] or expected["version"] != row["version"]:
                errors.append(f"state_history_divergence:{row['work_id']}")
            if row["state"] == WorkState.ACCEPTED.value:
                commit = self.db.execute("SELECT * FROM commits WHERE work_id=? AND resulting_version=?",
                                         (row["work_id"], row["version"])).fetchone()
                if not commit:
                    errors.append(f"accepted_without_commit:{row['work_id']}")
        return not errors, errors

    def snapshot(self) -> Dict[str, Any]:
        chain_ok, chain_errors = self.verify_event_chain()
        recon_ok, recon_errors = self.verify_state_reconciliation()
        return {
            "work_items": [dict(r) for r in self.db.execute("SELECT * FROM work_items ORDER BY work_id")],
            "leases": [dict(r) for r in self.db.execute("SELECT * FROM leases ORDER BY issued_at")],
            "artifacts": [dict(r) for r in self.db.execute("SELECT * FROM artifacts ORDER BY created_at")],
            "commits": [dict(r) for r in self.db.execute("SELECT * FROM commits ORDER BY committed_at")],
            "event_chain_valid": chain_ok,
            "event_chain_errors": chain_errors,
            "state_reconciliation_valid": recon_ok,
            "state_reconciliation_errors": recon_errors,
        }
