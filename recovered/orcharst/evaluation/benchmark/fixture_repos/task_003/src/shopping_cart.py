class ShoppingCart:
    def __init__(self):
        self.items = []

    def add_item(self, name: str, price: float, quantity: int = 1):
        self.items.append({"name": name, "price": price, "quantity": quantity})

    def remove_item(self, name: str):
        # BUG: crashes with StopIteration if item is not present
        item = next(i for i in self.items if i["name"] == name)
        self.items.remove(item)

    def get_total(self) -> float:
        # BUG: ignores quantity
        return sum(item["price"] for item in self.items)

    def apply_discount(self, discount_percent: float) -> float:
        total = self.get_total()
        # BUG: subtracts the raw percent number instead of applying a percentage
        return total - discount_percent

    def item_count(self) -> int:
        return len(self.items)

    def clear(self):
        self.items = []
