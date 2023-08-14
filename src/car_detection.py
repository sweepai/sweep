import cv2
import numpy as np

def detect_cars(image):
    # Convert the image to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Load the car classifier
    car_cascade = cv2.CascadeClassifier('cars.xml')

    # Detect cars
    cars = car_cascade.detectMultiScale(gray, 1.1, 1)

    # Return the list of bounding boxes
    return cars

