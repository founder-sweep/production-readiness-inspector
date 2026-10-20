#!/usr/bin/env python3
"""Restore only an Inspector SQLite snapshot, leaving the active store intact."""
import json
import subprocess
from pathlib import Path

from deploy import remote
from setup_stripe import private_write


def main():
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    code = """import json,os
from pathlib import Path
from mcp_products.inspector.commerce import ReportStore
source=ReportStore(Path(os.environ['INSPECTOR_DATABASE']),os.environ['INSPECTOR_MODE'])
target=source.path.parent/'restore-qualification.sqlite'
assert target.is_relative_to(source.path.parent)
tables=['workspaces','ledger','reports','purchases']
with source.connect() as db: before={name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in tables}
source.backup(target)
restored=ReportStore(target,os.environ['INSPECTOR_MODE'])
with restored.connect() as db:
 after={name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in tables}
 integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
assert before==after and integrity=='ok'
print(json.dumps({'restore_passed':True,'integrity_check':integrity,'retained_row_counts':after,'active_database_unchanged':True}))
"""
    script = "import subprocess\np=subprocess.run(['docker','exec','--user','10001','contentsweep-inspector-api','python','-c'," + repr(code) + "],capture_output=True,text=True,check=True)\nprint(p.stdout)"
    result = json.loads(remote(root, script))
    private_write(root / ".mcp-products/inspector/qualification/restore.private.json", json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
