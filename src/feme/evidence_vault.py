from __future__ import annotations

import json
import shutil
from pathlib import Path

from .utils import new_id, now_iso


class EvidenceVault:
    """Filesystem evidence vault for raw immutable-ish source capture.

    The SQLite DB stores metadata and extracted text. The vault stores raw bytes
    in content-addressed paths so the original file can be re-read and hashed.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.manifests = self.root / "manifests"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.manifests.mkdir(parents=True, exist_ok=True)

    def store_file(self, path: str | Path, sha256_hex: str, metadata: dict | None = None) -> dict:
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(src)
        dest = self._object_path(sha256_hex, suffix=src.suffix)
        if not dest.exists():
            shutil.copy2(src, dest)
        manifest = {
            "id": new_id("manifest"),
            "sha256": sha256_hex,
            "source_path": str(src.resolve()),
            "vault_path": str(dest.resolve()),
            "filename": src.name,
            "metadata": metadata or {},
            "stored_at": now_iso(),
        }
        (self.manifests / f"{manifest['id']}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def _object_path(self, sha256_hex: str, suffix: str = "") -> Path:
        shard = sha256_hex[:2]
        d = self.objects / shard
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{sha256_hex}{suffix}"
