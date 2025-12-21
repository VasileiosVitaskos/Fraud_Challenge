import uuid
import random

class FraudEnvironment:
    def __init__(self, total_normal=50, num_bots=15):
        self.users = {}
        self.balances = {
            "student": 3000, "entrepreneur": 10000, "worker": 7000,
            "bot": 0, "fraud_dirty": 150000, "fraud_clean": 0
        }
        self._setup_accounts(total_normal, num_bots)

    def _generate_id(self):
        u = str(uuid.uuid4())
        # Formats to xxxx-xxxx-xxxx-xxxx as requested
        return f"{u[:4]}-{u[9:13]}-{u[14:18]}-{u[19:23]}"

    def _setup_accounts(self, total_normal, num_bots):
        # 1. Setup Fraud Accounts
        self.dirty_id = self._generate_id()
        self.clean_id = self._generate_id()
        self.users[self.dirty_id] = {"type": "fraud_dirty", "balance": 150000.0, "state": "active"}
        self.users[self.clean_id] = {"type": "fraud_clean", "balance": 0.0, "state": "active"}

        # 2. Setup Normal Users
        types = ["student", "entrepreneur", "worker"]
        remaining = total_normal
        for i, t in enumerate(types):
            count = remaining if i == 2 else random.randint(0, remaining)
            remaining -= count
            for _ in range(count):
                self.users[self._generate_id()] = {"type": t, "balance": float(self.balances[t]), "state": "active"}

        # 3. Setup Bots
        for _ in range(num_bots):
            self.users[self._generate_id()] = {"type": "bot", "balance": 0.0, "state": "active"}

    def check_for_bans(self):
        """The 'Governor' detection logic: Bans bots with high suspicious activity."""
        for uid, data in self.users.items():
            if data['type'] == 'bot' and data['state'] == 'active':
                # Higher balance increases ban risk
                if data['balance'] > 5000:
                    if random.random() < 0.25: # 25% chance to get banned
                        data['state'] = 'banned'
                        print(f">>> GOVERNOR ALERT: Account {uid} has been BANNED.")

# Global instance for the Agent to import
sim = FraudEnvironment()

if __name__ == "__main__":
    print(f"Environment initialized with {len(sim.users)} accounts.")