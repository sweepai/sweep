import cv2
import numpy as np

def track_cars(cars, frame):
    # Initialize the tracker
    tracker = cv2.TrackerMOSSE_create()

    # Initialize a list to hold the bounding boxes
    bboxes = []

    # Initialize the tracker with the bounding boxes of the detected cars and the initial frame
    for car in cars:
        bbox = (car.x, car.y, car.w, car.h)
        tracker.init(frame, bbox)
        bboxes.append(bbox)

    while True:
        # Read a new frame
        ret, frame = cap.read()
        if not ret:
            break

        # Update the tracker and get the new bounding boxes
        for i in range(len(bboxes)):
            ret, bbox = tracker.update(frame)
            if ret:
                bboxes[i] = bbox

    return bboxes

