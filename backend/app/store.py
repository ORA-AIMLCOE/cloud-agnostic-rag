import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

from cryptography.fernet import Fernet

TERMINAL = {"completed", "failed", "cancelled", "expired"}


class Store:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        key = directory / "vault.key"
        if not key.exists():
            try:
                with key.open("xb") as f:
                    f.write(Fernet.generate_key())
            except FileExistsError:
                pass
        self.cipher = Fernet(key.read_bytes())
        self.path = directory / "jobs.sqlite3"
        self.lock = threading.RLock()
        with self.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, phase TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, public TEXT NOT NULL,
                secrets BLOB, cancel INTEGER NOT NULL DEFAULT 0)""")

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, public, secrets):
        identifier = uuid4().hex
        now = time.time()
        public.update(events=[], checks=[], files=[])
        with self.db() as db:
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    "queued_inspection",
                    "Queued for inspection",
                    now,
                    now,
                    json.dumps(public),
                    self.cipher.encrypt(json.dumps(secrets).encode()),
                    0,
                ),
            )
        return identifier

    def get(self, identifier):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        return dict(
            json.loads(row["public"]),
            id=row["id"],
            status=row["status"],
            phase=row["phase"],
            created_at=row["created"],
            updated_at=row["updated"],
            cancel_requested=bool(row["cancel"]),
        )

    def secrets(self, identifier):
        with self.db() as db:
            row = db.execute("SELECT secrets FROM jobs WHERE id=?", (identifier,)).fetchone()
        if row is None or not row[0]:
            raise ValueError("Job credentials have expired.")
        return json.loads(self.cipher.decrypt(row[0]))

    def save_secrets(self, identifier, payload):
        with self.db() as db:
            db.execute(
                "UPDATE jobs SET secrets=? WHERE id=?",
                (self.cipher.encrypt(json.dumps(payload).encode()), identifier),
            )

    def update(self, identifier, status=None, phase=None, **values):
        with self.lock, self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            public = json.loads(row["public"])
            public.update(values)
            if phase:
                public["events"].append({"time": time.time(), "message": phase})
            db.execute(
                "UPDATE jobs SET status=?, phase=?, updated=?, public=? WHERE id=?",
                (status or row["status"], phase or row["phase"], time.time(), json.dumps(public), identifier),
            )

    def queue_conversion(self, identifier, payload=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE jobs SET status='queued', phase='Queued for conversion' WHERE id=? AND status='ready'",
                (identifier,),
            ).rowcount
            if not changed:
                raise ValueError("Only an inspected, ready job can be converted once.")
            if payload is not None:
                db.execute(
                    "UPDATE jobs SET secrets=? WHERE id=?",
                    (self.cipher.encrypt(json.dumps(payload).encode()), identifier),
                )

    def delete(self, identifier, remove_workspace):
        # Serialize state checks with queue claims and retention cleanup.
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM jobs WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError(identifier)
            if row[0] not in TERMINAL:
                raise ValueError("Finish or cancel this conversion before deleting it.")
            remove_workspace()
            db.execute("DELETE FROM jobs WHERE id=?", (identifier,))

    def list(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM jobs ORDER BY created DESC LIMIT 100")]
        jobs = []
        for identifier in ids:
            try:
                jobs.append(self.get(identifier))
            except KeyError:
                pass  # A terminal job may have been deleted during this read.
        return jobs

    def claim(self):
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id,status FROM jobs WHERE status IN ('queued_inspection','queued') AND cancel=0 ORDER BY created LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (row[0],))
            return row[0], row[1]

    def cancel(self, identifier):
        with self.db() as db:
            db.execute(
                "UPDATE jobs SET cancel=1 WHERE id=? AND status NOT IN ('completed','failed','expired')",
                (identifier,),
            )
        job = self.get(identifier)
        if job["status"] in {"queued", "queued_inspection", "ready"}:
            self.update(identifier, status="cancelled", phase="Cancelled")

    def expire(self, cutoff):
        with self.db() as db:
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM jobs WHERE created < ? AND status != 'running' AND secrets IS NOT NULL",
                    (cutoff,),
                )
            ]
            for identifier in ids:
                db.execute(
                    "UPDATE jobs SET secrets=NULL,status='expired',public=? WHERE id=?",
                    (
                        json.dumps(
                            {
                                "events": [],
                                "checks": [],
                                "files": [],
                                "repository_url": "Expired job",
                                "source_branch": "",
                            }
                        ),
                        identifier,
                    ),
                )
        return ids

    def recover(self):
        # Do not automatically replay a model call or publish after an interrupted process.
        for job in self.list():
            if job["status"] == "running":
                self.update(
                    job["id"],
                    status="failed",
                    phase="Worker interrupted. Inspect any recorded branch before starting a new job.",
                )
