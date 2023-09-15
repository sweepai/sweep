import queue
import threading


class SafePriorityQueue:
    def __init__(self):
        self.q = queue.PriorityQueue()
        self.lock = threading.Lock()

    def put(self, priority, event):
        with self.lock:
            self.q.put((priority, event))
            self.invalidate_lower_priority(priority)

    def get(self):
        with self.lock:
            return self.q.get()[1]  # Only return the event, not the priority

    def invalidate_lower_priority(self, priority):
        temp_q = queue.PriorityQueue()
        while not self.q.empty():
            p, e = self.q.get()
            if p <= priority:
                temp_q.put((p, e))
        self.q = temp_q
