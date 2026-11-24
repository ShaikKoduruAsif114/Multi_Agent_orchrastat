class TaskQueue:
    def __init__(self):
        self._items = []

    def push(self, item) -> None:
        self._items.append(item)

    def pop(self):
        # BUG: LIFO instead of FIFO
        if not self._items:
            return None
        return self._items.pop()

    def peek(self):
        # BUG: raises on empty
        return self._items[-1]

    def __len__(self):
        return len(self._items)
