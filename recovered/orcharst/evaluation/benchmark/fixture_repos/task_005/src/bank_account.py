class BankAccount:
    def __init__(self, owner: str, initial_balance: float = 0.0):
        self.owner = owner
        self.balance = initial_balance
        self.transactions = []

    def deposit(self, amount: float) -> float:
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        self.balance += amount
        self.transactions.append(("deposit", amount))
        return self.balance

    def withdraw(self, amount: float) -> float:
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        # BUG: no check for sufficient funds - balance can go negative
        self.balance -= amount
        self.transactions.append(("withdraw", amount))
        return self.balance

    def get_balance(self) -> float:
        return self.balance

    def transfer(self, target_account: "BankAccount", amount: float) -> bool:
        # BUG: does not check sender has sufficient funds
        self.balance -= amount
        target_account.balance += amount
        return True

    def apply_interest(self, rate: float, years: int) -> float:
        # BUG: applies simple interest instead of compound interest
        original = self.balance
        self.balance = original + (original * rate * years)
        return self.balance

    def transaction_count(self) -> int:
        return len(self.transactions)
