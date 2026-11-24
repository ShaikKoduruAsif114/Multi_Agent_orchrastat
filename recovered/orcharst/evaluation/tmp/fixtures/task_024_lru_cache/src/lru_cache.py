class LRUCache:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._data = {}
        self._order = []

    def get(self, key):
        # BUG: no recency refresh on access
        return self._data.get(key)

    def put(self, key, value):
        if key in self._data:
            self._data[key] = value
            return
        if len(self._data) >= self.capacity:
            # BUG: evicts most recently used (front of order list)
            victim = self._order.pop(0)
            del self._data[victim]
        self._data[key] = value
        self._order.append(key)

    def __len__(self):
        return len(self._data)

    def keys_snapshot(self):
        return list(self._order)
