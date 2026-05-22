from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from ..db import Database


@contextmanager
def sqlite_immediate_transaction(db: Database) -> Iterator[object]:
    """Open a SQLite BEGIN IMMEDIATE transaction.

    This is useful for grouped governance writes where a normal deferred
    transaction may discover write contention too late.
    """

    with db.connect() as con:
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
