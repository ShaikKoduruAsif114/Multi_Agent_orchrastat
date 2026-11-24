class Inventory:
    def __init__(self):
        self.stock = {}

    def restock(self, name: str, qty: int) -> None:
        # BUG: KeyError when item not already present
        self.stock[name] = self.stock[name] + qty

    def sell(self, name: str, qty: int) -> None:
        if name not in self.stock or self.stock[name] < qty:
            raise ValueError("insufficient stock")
        self.stock[name] -= qty

    def get_stock(self, name: str) -> int:
        return self.stock.get(name, 0)

    def get_low_stock(self, threshold: int):
        # BUG: uses > threshold, so items exactly AT threshold are missed
        return {k: v for k, v in self.stock.items() if v > threshold and v <= threshold * 2}
