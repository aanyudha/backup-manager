"""JSON-backed runtime state for the internal scheduler."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile


class SchedulerStateRepository:
    """Persist last scheduled run timestamps by profile id."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.state_path = self.config_dir / "scheduler_state.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the state file with a stable default shape if needed."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self.save({})

    def _atomic_write_json(self, payload: object) -> None:
        """Write the scheduler state file atomically."""
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.state_path.parent,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, ensure_ascii=True)
            temp_file.flush()
            temp_path = Path(temp_file.name)
        temp_path.replace(self.state_path)

    def load(self) -> dict[str, datetime]:
        """Load last-run timestamps keyed by profile id."""
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        items = data.get("last_runs", {}) if isinstance(data, dict) else {}
        return {
            profile_id: datetime.fromisoformat(value)
            for profile_id, value in items.items()
            if isinstance(value, str) and value.strip()
        }

    def save(self, state: dict[str, datetime]) -> None:
        """Replace the stored scheduler state."""
        payload = {
            "last_runs": {
                profile_id: value.isoformat()
                for profile_id, value in state.items()
            }
        }
        self._atomic_write_json(payload)

    def get_last_run(self, profile_id: str) -> datetime | None:
        """Return the last recorded scheduled run attempt for one profile."""
        return self.load().get(profile_id)

    def set_last_run(self, profile_id: str, run_time: datetime) -> datetime:
        """Persist one last-run timestamp."""
        state = self.load()
        state[profile_id] = run_time
        self.save(state)
        return run_time
