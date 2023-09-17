from sweepai.utils.safe_pqueue import SafePriorityQueue


spq = SafePriorityQueue()

spq.put(1,"a")
spq.put(0,"b")
assert spq.get() == "b"