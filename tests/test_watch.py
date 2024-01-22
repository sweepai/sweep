import os
import pickle

from sweepai.watch import handle_event

event_pickle_paths = [
    "pull_request_opened_34875324597.pkl",
    "issue_labeled_11503901425.pkl",
]
for path in event_pickle_paths:
    event = pickle.load(open(os.path.join("tests/events", path), "rb"))
    handle_event(event, do_async=False)
