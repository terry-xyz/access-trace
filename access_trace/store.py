"""Small durable JSON store for redacted journey records."""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

from .evidence import attach_evidence_handoff


class RunStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, run: Dict) -> None:
        attach_evidence_handoff(run)
        destination = self.directory / (run["id"] + ".json")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".run-", suffix=".json", dir=str(self.directory)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(run, temporary, indent=2, sort_keys=True)
                temporary.write("\n")
            os.replace(temporary_name, destination)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    def get(self, run_id: str) -> Optional[Dict]:
        if not run_id or any(character not in "0123456789abcdef-" for character in run_id):
            return None
        path = self.directory / (run_id + ".json")
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as source:
            return json.load(source)

    def latest(self) -> Optional[Dict]:
        """Return the most recently saved terminal run, skipping partial records."""
        terminal_statuses = {"BLOCKED", "CANCELLED", "COMPLETED", "INCONCLUSIVE"}
        candidates = sorted(
            self.directory.glob("*.json"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for path in candidates:
            try:
                with path.open("r", encoding="utf-8") as source:
                    run = json.load(source)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(run, dict) and run.get("status") in terminal_statuses:
                return run
        return None
