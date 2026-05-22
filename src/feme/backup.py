from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import Database
from .utils import now_iso


class BackupManager:
    def __init__(self, db: Database):
        self.db = db

    def backup(self, out_path: str | Path) -> dict:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with self.db.connect() as source:
            dest = sqlite3.connect(str(out))
            try:
                source.backup(dest)
            finally:
                dest.close()
        return {"backup_path": str(out), "created_at": now_iso()}

    def vacuum_into(self, out_path: str | Path) -> dict:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with self.db.connect() as con:
            con.execute(f"VACUUM INTO {str(out)!r}")
        return {"vacuum_backup_path": str(out), "created_at": now_iso()}
