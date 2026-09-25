"""Small durable JSON store for redacted journey records."""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional


class RunStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, run: Dict) -> None:
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
