import numpy as np

class Vector:
    def __init__(self, elements):
        self.elements = np.array(elements)

    def add(self, other):
        return Vector(self.elements + other.elements)

    def subtract(self, other):
        return Vector(self.elements - other.elements)

    def dot(self, other):
        return np.dot(self.elements, other.elements)

    def norm(self):
        return np.linalg.norm(self.elements)

