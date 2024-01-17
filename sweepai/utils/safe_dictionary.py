from threading import Lock


class SafeDictionary:
    def __init__(self):
        self._dict = {}
        self._lock = Lock()

    def get(self, key, default=None):
        with self._lock:
            return self._dict.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._dict[key] = value

    def delete(self, key):
        with self._lock:
            if key in self._dict:
                del self._dict[key]

    def contains(self, key):
        with self._lock:
            return key in self._dict

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)

    def __delitem__(self, key):
        self.delete(key)

    def __contains__(self, key):
        return self.contains(key)

    def __iter__(self):
        with self._lock:
            return iter(self._dict)

    def keys(self):
        with self._lock:
            return self._dict.keys()

    def values(self):
        with self._lock:
            return self._dict.values()

    def items(self):
        with self._lock:
            return self._dict.items()
