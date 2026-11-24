class Ledger:
    def __init__(self):
        self.balances = {}

    def open_account(self, name: str, amount: float = 0.0):
        if name in self.balances:
            raise ValueError("account exists")
        self.balances[name] = amount
        return amount

    def balance(self, name: str) -> float:
        return self.balances.get(name, 0.0)

    def _apply(self, sender: str, receiver: str, amount: float):
        if self.balances.get(sender, 0.0) < amount:
            raise ValueError("insufficient funds")
        self.balances[sender] = self.balances.get(sender, 0.0) - amount
        self.balances[receiver] = self.balances.get(receiver, 0.0) + amount

    def commit_batch(self, transfers: list):
        # BUG: no rollback -> partial application
        for sender, receiver, amount in transfers:
            self._apply(sender, receiver, amount)
        return len(transfers)
