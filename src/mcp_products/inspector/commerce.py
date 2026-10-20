"""Inspector-only prepaid report store. No source ingestion or shared accounts."""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .model import PRODUCT, PROFILE, RULES, RULESET, digest

AMOUNT = 1900
CREDITS = 100
TRIAL = 3
RETENTION = 30 * 86400
SUMMARY_SCHEMA = "inspector-summary-v1"
FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
SECRET = re.compile(r"(?:[sr]k_(?:live|test)_|whsec_)[A-Za-z0-9]+|AKIA[0-9A-Z]{16}")


class CommerceError(ValueError):
    def __init__(self, code: str, status: int = 422):
        self.code, self.status = code, status


def opaque_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _fingerprint(value):
    if not isinstance(value, str) or not FINGERPRINT.fullmatch(value):
        raise CommerceError("invalid_fingerprint")
    return value


def validate_summary(value: dict) -> dict:
    """Whitelist only report metadata; never persist fact/source/excerpt fields."""
    keys = {"schema_version", "product", "profile", "ruleset_version", "input_fingerprint", "scope_fingerprint", "coverage", "findings"}
    if not isinstance(value, dict) or set(value) != keys:
        raise CommerceError("invalid_summary_fields")
    if (value["schema_version"] != SUMMARY_SCHEMA or value["product"] != PRODUCT
            or value["profile"] != PROFILE or value["ruleset_version"] != RULESET):
        raise CommerceError("unsupported_report_version")
    _fingerprint(value["input_fingerprint"])
    _fingerprint(value["scope_fingerprint"])
    coverage = value["coverage"]
    families = {"repository", "python", "fastapi", "docker", "github_actions", "compose", "kubernetes", "dependencies", "runtime_behavior", "secret_values"}
    states = {"analyzed", "not_detected", "syntax_only", "analyzed_subset", "not_supported", "not_analyzed"}
    if not isinstance(coverage, dict) or set(coverage) != families or any(not isinstance(item, str) or item not in states for item in coverage.values()) or coverage["repository"] != "analyzed":
        raise CommerceError("incomplete_or_invalid_coverage")
    findings = value["findings"]
    if not isinstance(findings, list) or len(findings) > 2000:
        raise CommerceError("finding_count_limit")
    seen = set()
    for item in findings:
        if not isinstance(item, dict) or set(item) != {"rule_id", "rule_version", "instance_id", "path", "line"}:
            raise CommerceError("invalid_finding_fields")
        rule = item["rule_id"]
        if not isinstance(rule, str) or rule not in RULES or item["rule_version"] != RULES[rule][0]:
            raise CommerceError("unsupported_rule")
        instance = _fingerprint(item["instance_id"])
        if instance in seen:
            raise CommerceError("duplicate_finding_instance")
        seen.add(instance)
        path = item["path"]
        if not isinstance(path, str) or not path or len(path.encode()) > 512 or path.startswith(("/", "\\")) or ".." in path.split("/") or "\\" in path or any(ord(char) < 32 or ord(char) == 127 for char in path) or SECRET.search(path):
            raise CommerceError("invalid_or_sensitive_path")
        if type(item["line"]) is not int or not 1 <= item["line"] <= 10_000_000:
            raise CommerceError("invalid_line")
    # A JSON round-trip prevents caller mutation after validation.
    return json.loads(json.dumps(value, sort_keys=True))


def summarize_report(report: dict) -> dict:
    if not isinstance(report, dict) or report.get("product") != PRODUCT or report.get("verdict") not in {"ready", "needs_review"}:
        raise CommerceError("complete_inspector_report_required")
    metadata = report.get("metadata", {})
    if not isinstance(metadata, dict) or metadata.get("complete") is not True or metadata.get("issues"):
        raise CommerceError("complete_inspector_report_required")
    try:
        summary = {"schema_version": SUMMARY_SCHEMA, "product": PRODUCT,
                   "profile": metadata["profile"], "ruleset_version": metadata["ruleset_version"],
                   "input_fingerprint": report["input_fingerprint"], "scope_fingerprint": metadata["scope_fingerprint"],
                   "coverage": report["coverage"],
                   "findings": [{"rule_id": item["id"], "rule_version": item["metadata"]["rule_version"],
                                 "instance_id": item["metadata"]["instance_id"], "path": item["metadata"]["path"],
                                 "line": item["metadata"]["line"]} for item in report["findings"]]}
    except (KeyError, TypeError) as exc:
        raise CommerceError("invalid_local_report") from exc
    return validate_summary(summary)


class ReportStore:
    def __init__(self, path: str | Path, mode: str):
        if mode not in {"test", "live"}:
            raise CommerceError("invalid_mode")
        self.path, self.mode = Path(path), mode
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY,key_hash TEXT UNIQUE NOT NULL,created REAL NOT NULL,classification TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY,workspace TEXT NOT NULL,delta INTEGER NOT NULL,reason TEXT NOT NULL,reference TEXT UNIQUE NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS purchases (id TEXT PRIMARY KEY,workspace TEXT NOT NULL,idempotency TEXT NOT NULL,session TEXT UNIQUE,payment_intent TEXT UNIQUE,status TEXT NOT NULL DEFAULT 'pending',granted INTEGER NOT NULL DEFAULT 0,revoked INTEGER NOT NULL DEFAULT 0,refunded_cents INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,classification TEXT NOT NULL DEFAULT 'customer',UNIQUE(workspace,idempotency));
                CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,kind TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS qualification_receipts (id TEXT PRIMARY KEY,kind TEXT NOT NULL,session TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY,workspace TEXT NOT NULL,project TEXT NOT NULL,idempotency TEXT NOT NULL,payload_hash TEXT NOT NULL,summary TEXT,comparison TEXT,created REAL NOT NULL,UNIQUE(workspace,idempotency));
                CREATE INDEX IF NOT EXISTS report_history ON reports(workspace,project,created);
                CREATE TABLE IF NOT EXISTS rate_limits (bucket TEXT PRIMARY KEY,count INTEGER NOT NULL,expires REAL NOT NULL);
            """)
            if "classification" not in {row[1] for row in db.execute("PRAGMA table_info(purchases)")}:
                db.execute("ALTER TABLE purchases ADD COLUMN classification TEXT NOT NULL DEFAULT 'customer'")
            db.execute("INSERT OR IGNORE INTO settings VALUES ('mode',?)", (mode,))
            if db.execute("SELECT value FROM settings WHERE name='mode'").fetchone()[0] != mode:
                raise CommerceError("database_mode_mismatch")
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA secure_delete=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def capacity(self):
        size = sum(path.stat().st_size for path in self.path.parent.glob(self.path.name + "*") if path.is_file())
        if size > 256 * 1024 * 1024:
            raise CommerceError("temporary_report_capacity_limit", 503)

    def rate(self, bucket: str, count: int, period: int):
        current = time.time()
        with self.transaction() as db:
            db.execute("DELETE FROM rate_limits WHERE expires<?", (current,))
            db.execute("INSERT OR IGNORE INTO rate_limits VALUES (?,0,?)", (bucket, current + period))
            db.execute("UPDATE rate_limits SET count=count+1 WHERE bucket=?", (bucket,))
            if db.execute("SELECT count FROM rate_limits WHERE bucket=?", (bucket,)).fetchone()[0] > count:
                raise CommerceError("rate_limit", 429)

    def create_workspace(self, *, classification: str = "customer"):
        if classification not in {"customer", "internal"}:
            raise CommerceError("invalid_classification")
        self.capacity()
        workspace, token = "iw_" + secrets.token_hex(16), "ipk_" + secrets.token_urlsafe(32)
        with self.transaction() as db:
            db.execute("INSERT INTO workspaces VALUES (?,?,?,?)", (workspace, opaque_hash(token), time.time(), classification))
            db.execute("INSERT INTO ledger(workspace,delta,reason,reference,created) VALUES (?,?,?,?,?)", (workspace, TRIAL, "trial", "trial:" + workspace, time.time()))
        return {"workspace_id": workspace, "api_key": token, "trial_reports": TRIAL, "mode": self.mode}

    def authenticate(self, token: str) -> str:
        if not isinstance(token, str) or not re.fullmatch(r"ipk_[A-Za-z0-9_-]{43}", token):
            raise CommerceError("unauthorized", 401)
        with self.connect() as db:
            row = db.execute("SELECT id FROM workspaces WHERE key_hash=?", (opaque_hash(token),)).fetchone()
        if row is None:
            raise CommerceError("unauthorized", 401)
        return row["id"]

    @staticmethod
    def _balance(db, workspace):
        return db.execute("SELECT COALESCE(SUM(delta),0) FROM ledger WHERE workspace=?", (workspace,)).fetchone()[0]

    def balance(self, workspace):
        with self.connect() as db:
            balance = self._balance(db, workspace)
        return {"reports_remaining": max(0, balance), "revoked_credit_debt": max(0, -balance), "mode": self.mode}

    @staticmethod
    def _idempotency(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,100}", value):
            raise CommerceError("invalid_idempotency_key")

    def purchase(self, workspace, key):
        self._idempotency(key)
        self.capacity()
        with self.transaction() as db:
            row = db.execute("SELECT classification FROM workspaces WHERE id=?", (workspace,)).fetchone()
            if row is None:
                raise CommerceError("unauthorized", 401)
            db.execute("INSERT OR IGNORE INTO purchases(id,workspace,idempotency,created,classification) VALUES (?,?,?,?,?)", ("ib_" + secrets.token_hex(16), workspace, key, time.time(), row["classification"]))
            return dict(db.execute("SELECT * FROM purchases WHERE workspace=? AND idempotency=?", (workspace, key)).fetchone())

    def bind_session(self, purchase_id, session):
        with self.transaction() as db:
            row = db.execute("SELECT session FROM purchases WHERE id=?", (purchase_id,)).fetchone()
            if row is None or row["session"] not in {None, session}:
                raise CommerceError("purchase_session_mismatch")
            db.execute("UPDATE purchases SET session=? WHERE id=?", (session, purchase_id))

    def get_purchase(self, purchase_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM purchases WHERE id=?", (purchase_id,)).fetchone()
        if row is None:
            raise CommerceError("unknown_purchase", 404)
        return dict(row)

    def apply_payment(self, purchase_id: str, session: str, payment_intent: str, refunded: int, event_id: str, event_hash: str, event_type: str):
        if type(refunded) is not int or not 0 <= refunded <= AMOUNT:
            raise CommerceError("invalid_refund_amount")
        with self.transaction() as db:
            previous = db.execute("SELECT payload_hash FROM events WHERE id=?", (event_id,)).fetchone()
            if previous:
                if previous[0] != event_hash:
                    raise CommerceError("event_identity_conflict", 409)
                return {"duplicate": True}
            row = db.execute("SELECT * FROM purchases WHERE id=?", (purchase_id,)).fetchone()
            if row is None or row["session"] not in {None, session} or row["payment_intent"] not in {None, payment_intent}:
                raise CommerceError("purchase_identity_mismatch")
            if not row["granted"]:
                db.execute("INSERT INTO ledger(workspace,delta,reason,reference,created) VALUES (?,?,?,?,?)", (row["workspace"], CREDITS, "purchase", "paid:" + purchase_id, time.time()))
            # Provider snapshots can arrive out of order. Never restore refunded credit.
            refunded = max(refunded, row["refunded_cents"])
            revoked = math.ceil(CREDITS * refunded / AMOUNT)
            if revoked > row["revoked"]:
                db.execute("INSERT INTO ledger(workspace,delta,reason,reference,created) VALUES (?,?,?,?,?)", (row["workspace"], row["revoked"] - revoked, "refund_revocation", f"refund:{purchase_id}:{refunded}", time.time()))
            db.execute("UPDATE purchases SET session=?,payment_intent=?,status=?,granted=1,revoked=?,refunded_cents=? WHERE id=?", (session, payment_intent, "refunded" if refunded == AMOUNT else "paid", revoked, refunded, purchase_id))
            db.execute("INSERT INTO events VALUES (?,?,?,?)", (event_id, event_hash, event_type, time.time()))
        return {"duplicate": False, "granted_reports": CREDITS, "revoked_reports": revoked}

    def submit(self, workspace: str, project: str, key: str, summary: dict):
        self._idempotency(key)
        if not isinstance(project, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", project):
            raise CommerceError("invalid_project")
        summary = validate_summary(summary)
        fingerprint = digest([project, summary])
        self.capacity()
        with self.transaction() as db:
            now = time.time()
            db.execute("UPDATE reports SET summary=NULL,comparison=NULL WHERE created<? AND summary IS NOT NULL", (now - RETENTION,))
            existing = db.execute("SELECT * FROM reports WHERE workspace=? AND idempotency=?", (workspace, key)).fetchone()
            if existing:
                if existing["payload_hash"] != fingerprint:
                    raise CommerceError("idempotency_payload_conflict", 409)
                return self._report(existing, duplicate=True)
            if self._balance(db, workspace) <= 0:
                raise CommerceError("insufficient_report_credits", 402)
            prior = db.execute("SELECT * FROM reports WHERE workspace=? AND project=? AND summary IS NOT NULL ORDER BY created DESC LIMIT 1", (workspace, project)).fetchone()
            old = json.loads(prior["summary"]) if prior else None
            if old and (old["scope_fingerprint"] != summary["scope_fingerprint"] or old["ruleset_version"] != summary["ruleset_version"]):
                raise CommerceError("baseline_policy_changed_use_new_project")
            previous_ids = {item["instance_id"] for item in old["findings"]} if old else set()
            current_ids = {item["instance_id"] for item in summary["findings"]}
            comparison = {"baseline_id": prior["id"] if prior else None, "new": sorted(current_ids - previous_ids), "unchanged": sorted(current_ids & previous_ids), "resolved": sorted(previous_ids - current_ids)}
            report_id = "ir_" + secrets.token_hex(16)
            db.execute("INSERT INTO reports VALUES (?,?,?,?,?,?,?,?)", (report_id, workspace, project, key, fingerprint, json.dumps(summary, sort_keys=True), json.dumps(comparison, sort_keys=True), now))
            db.execute("INSERT INTO ledger(workspace,delta,reason,reference,created) VALUES (?,?,?,?,?)", (workspace, -1, "report", report_id, now))
            row = db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            return self._report(row)

    @staticmethod
    def _report(row, *, duplicate=False):
        expired = row["summary"] is None or row["created"] < time.time() - RETENTION
        return {"id": row["id"], "project": row["project"], "created": row["created"], "expired": expired,
                "duplicate": duplicate, "billed_reports": 0 if duplicate else 1,
                "summary": None if expired else json.loads(row["summary"]),
                "comparison": None if expired else json.loads(row["comparison"]),
                "provenance": "Caller-submitted static evidence; source and deployment were not independently verified."}

    def report(self, workspace, report_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM reports WHERE workspace=? AND id=?", (workspace, report_id)).fetchone()
        if row is None:
            raise CommerceError("report_not_found", 404)
        return self._report(row, duplicate=True)

    def history(self, workspace, project=None):
        with self.connect() as db:
            rows = db.execute("SELECT id,project,created FROM reports WHERE workspace=? AND (? IS NULL OR project=?) ORDER BY created DESC LIMIT 100", (workspace, project, project)).fetchall()
        return [dict(row) for row in rows]

    def delete_report(self, workspace, report_id):
        with self.transaction() as db:
            db.execute("UPDATE reports SET summary=NULL,comparison=NULL WHERE workspace=? AND id=?", (workspace, report_id))
        return {"deleted": True, "receipt_retained_for_idempotency": True}

    def backup(self, target: Path):
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db, sqlite3.connect(target) as destination:
            db.backup(destination)
        target.chmod(0o600)

    def maintain(self):
        from datetime import UTC, datetime
        with self.transaction() as db:
            db.execute("UPDATE reports SET summary=NULL,comparison=NULL WHERE created<? AND summary IS NOT NULL", (time.time() - RETENTION,))
            db.execute("DELETE FROM rate_limits WHERE expires<?", (time.time(),))
            db.execute("DELETE FROM qualification_receipts WHERE created<?", (time.time() - RETENTION,))
        with self.connect() as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        folder = self.path.parent / "backups"
        target = folder / (datetime.now(UTC).strftime("%Y-%m-%d") + ".sqlite")
        if not target.exists():
            self.backup(target)
        for path in folder.glob("*.sqlite"):
            if path.stat().st_mtime < time.time() - 7 * 86400:
                path.unlink()
