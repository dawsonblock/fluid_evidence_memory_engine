from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StoreCapabilities:
    backend: str
    transactions: bool
    full_text_search: bool
    vector_search: bool
    concurrent_writes: bool
    advisory_locks: bool = False


@dataclass(frozen=True)
class StoreHealth:
    backend: str
    ok: bool
    schema_version: str | None
    details: dict[str, Any]


class MemoryStore(Protocol):
    """Backend-neutral storage contract for FEME runtime adapters.

    The SQLite implementation is the default local runtime. The PostgreSQL
    implementation uses the same public shape so ingestion/retrieval logic can
    move away from direct sqlite3 calls over time.
    """

    def capabilities(self) -> StoreCapabilities: ...

    def health(self) -> StoreHealth: ...

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]: ...

    def execute_write(self, sql: str, params: tuple[Any, ...] = ()) -> int: ...

    def transaction(self): ...
