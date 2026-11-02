"""Aggregate read-only Inspector acquisition snapshots without exporting workspace keys."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from .commerce import AMOUNT, TRIAL


def report(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        mode = db.execute("SELECT value FROM settings WHERE name='mode'").fetchone()[0]
        acquisition = {r['workspace']: r['campaign'] for r in db.execute('SELECT * FROM acquisition')} if db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='acquisition'").fetchone() else {}
        channels = defaultdict(lambda: {'accounts': 0, 'activated_accounts': 0, 'paying_accounts': 0,
            'settled_purchases': 0, 'gross_cents': 0, 'refund_cents': 0, 'repeat_paid_accounts': 0})
        for workspace in db.execute("SELECT * FROM workspaces WHERE classification='customer'"):
            c = channels[acquisition.get(workspace['id'], 'unknown')]
            c['accounts'] += 1
            reports = list(db.execute('SELECT created FROM reports WHERE workspace=? ORDER BY created', (workspace['id'],)))
            c['activated_accounts'] += bool(reports)
            purchases = list(db.execute("SELECT p.*,l.created AS settled FROM purchases p JOIN ledger l ON l.reference='paid:'||p.id WHERE p.workspace=? AND p.granted=1 AND p.classification='customer'", (workspace['id'],))) if mode == 'live' else []
            gross, refund = len(purchases) * AMOUNT, sum(p['refunded_cents'] for p in purchases)
            c['settled_purchases'] += len(purchases)
            c['gross_cents'] += gross
            c['refund_cents'] += refund
            c['paying_accounts'] += gross > refund
            funded = min((p['settled'] for p in purchases), default=float('inf'))
            days = {datetime.fromtimestamp(r['created'], UTC).date().isoformat()
                    for i, r in enumerate(reports) if i >= TRIAL and r['created'] >= funded}
            c['repeat_paid_accounts'] += gross > refund and len(days) >= 2
        rows = [{'campaign': k, **v, 'cash_after_refunds_cents': v['gross_cents'] - v['refund_cents']} for k, v in sorted(channels.items())]
        totals = {key: sum(row[key] for row in rows) for key in channels.default_factory()}
        return {'product': 'production-readiness-inspector', 'mode': mode, 'by_campaign': rows,
                **totals, 'cash_after_refunds_cents': totals['gross_cents'] - totals['refund_cents'],
                'hold_expansion': totals['activated_accounts'] >= 20 and totals['paying_accounts'] == 0,
                'fees': 'unknown; cash after refunds is not profit',
                'repeat_definition': 'reports on separate UTC days after settled funding and the first three trial reports',
                'attribution': 'recorded campaign, not proof an AI agent made the request'}
    finally:
        db.close()
