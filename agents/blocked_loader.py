import json
from pathlib import Path


def load_blocked_ids(path: str = "data/blocked_inference.json") -> set[str]:
    file_path = Path(path)
    if not file_path.exists():
        return set()
    with file_path.open(encoding="utf-8") as file:
        return {str(item) for item in json.load(file)}


def save_blocked_ids(ids: set[str], path: str = "data/blocked_inference.json") -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as file:
        json.dump(list(ids), file, indent=2)
