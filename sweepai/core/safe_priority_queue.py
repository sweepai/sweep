import heapq
from queue import Queue

class SafePriorityQueue(Queue):
    def __init__(self):
        super().__init__()
        self.queue = []

    def put(self, priority, item):
        heapq.heappush(self.queue, (-priority, item))

    def get(self):
        _, item = heapq.heappop(self.queue)
        return item
