from queue import PriorityQueue
import threading

class SafePriorityQueue:
    def __init__(self):
        self.q = PriorityQueue()
        self.lock = threading.Lock()

    def put(self, priority: int, event):
        """
        Add an event to the queue with a specified priority.

        Args:
            priority (int): The priority of the event.
            event: The event to be added to the queue.
        """
        with self.lock:
            self.q.put((priority, event))
            self.invalidate_lower_priority(priority)

    def get(self):
        """
        Retrieve and return the next event from the queue.

        Returns:
            The next event from the queue.
        """
        with self.lock:
            return self.q.get()[1]

    def invalidate_lower_priority(self, priority: int):
        """
        Remove events with lower or equal priority from the queue.

        Args:
            priority (int): The priority to invalidate.
        """
        temp_q = PriorityQueue()
        while not self.q.empty():
            p, e = self.q.get()
            if p <= priority:
                temp_q.put((p, e))
        self.q = temp_q
