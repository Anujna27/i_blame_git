from threading import Event, Thread


class HealingScheduler:
    """Small optional daemon for periodic graph healing; safe to stop in tests."""
    def __init__(self, heal_callable, interval_seconds=900):
        self.heal_callable = heal_callable
        self.interval_seconds = interval_seconds
        self._stop = Event()
        self._thread = None

    def run_once(self):
        return self.heal_callable()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        def loop():
            while not self._stop.wait(self.interval_seconds):
                self.heal_callable()
        self._stop.clear(); self._thread = Thread(target=loop, daemon=True, name="graph-healer")
        self._thread.start()

    def stop(self):
        self._stop.set()
