import queue
import threading


class SafePriorityQueue:
    def __init__(self):
        self.q = queue.PriorityQueue()
        self.lock = threading.Lock()

    def put(self, priority: int, event):
        try:
            with self.lock:
                self.q.put((priority, event))
                self._invalidate_lower_priority(priority)
        except Exception:
            pass

    def get(self):
        with self.lock:
            return self.q.get()[1]  # Only return the event, not the priority

    def empty(self):
        with self.lock:
            return self.q.empty()

    def _invalidate_lower_priority(self, priority: int):
        temp_q = queue.PriorityQueue()
        while not self.q.empty():
            p, e = self.q.get()
            if p <= priority:
                temp_q.put((p, e))
        self.q = temp_q
