from threading import Event, Thread
import json
from pathlib import Path


class HealingScheduler:
    """Small optional daemon for periodic graph healing; safe to stop in tests."""
    def __init__(self, heal_callable, interval_seconds=900, config_path="data/healing_schedule.json"):
        self.heal_callable = heal_callable
        self.interval_seconds = interval_seconds
        self._stop = Event()
        self._thread = None
        self.config_path = Path(config_path)
        self._load_config()

    def _load_config(self):
        if self.config_path.exists():
            try: self.interval_seconds = int(json.loads(self.config_path.read_text()).get("interval_seconds", self.interval_seconds))
            except Exception: pass

    def save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps({"interval_seconds": self.interval_seconds, "enabled": True}, indent=2), encoding="utf-8")

    def run_once(self):
        return self.heal_callable()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        def loop():
            while not self._stop.wait(self.interval_seconds):
                self.heal_callable()
        self.save_config(); self._stop.clear(); self._thread = Thread(target=loop, daemon=True, name="graph-healer")
        self._thread.start()

    def stop(self):
        self._stop.set()
