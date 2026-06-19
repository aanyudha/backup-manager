"""JSON-backed repository for backup verification metadata."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.models.backup_metadata import BackupMetadata


class BackupMetadataRepository:
    """Persist backup verification metadata in a dedicated JSON file."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.metadata_path = self.config_dir / "backup_metadata.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the metadata file with a stable default shape if needed."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.metadata_path.exists():
            self._atomic_write_json({"backups": []})

    def _atomic_write_json(self, payload: object) -> None:
        """Write the repository file atomically."""
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.metadata_path.parent,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, ensure_ascii=True, default=str)
            temp_file.flush()
            temp_path = Path(temp_file.name)
        temp_path.replace(self.metadata_path)

    @staticmethod
    def _key(metadata: BackupMetadata) -> tuple[str, str, str]:
        """Return a stable identity tuple for one metadata entry."""
        return (
            metadata.profile_id,
            metadata.output_file,
            metadata.finished_at.isoformat(),
        )

    def list(self) -> list[BackupMetadata]:
        """Return all stored metadata entries."""
        data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        items = data.get("backups", []) if isinstance(data, dict) else data
        return [BackupMetadata.model_validate(item) for item in items]

    def add(self, metadata: BackupMetadata) -> BackupMetadata:
        """Append a new metadata entry."""
        items = self.list()
        items.append(metadata)
        self.save_all(items)
        return metadata

    def update(self, metadata: BackupMetadata) -> BackupMetadata:
        """Replace an existing metadata entry."""
        items = self.list()
        target_key = self._key(metadata)
        updated = False
        for index, existing in enumerate(items):
            if self._key(existing) == target_key:
                items[index] = metadata
                updated = True
                break
        if not updated:
            raise KeyError(f"Backup metadata entry not found for {metadata.output_file}.")
        self.save_all(items)
        return metadata

    def save_all(self, items: list[BackupMetadata]) -> None:
        """Replace the stored metadata collection."""
        payload = {"backups": [item.model_dump(mode="json") for item in items]}
        self._atomic_write_json(payload)
