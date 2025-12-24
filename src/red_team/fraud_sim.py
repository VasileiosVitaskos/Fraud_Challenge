import uuid
import random
import os
import redis
import sys
from dotenv import load_dotenv

load_dotenv()

class FraudEnvironment:
    def __init__(self, total_normal=50, num_bots=15):
        # 1. Setup Redis & Verify Connection
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=0,
                decode_responses=True
            )
            # Test the connection immediately
            self.redis_client.ping()
            print(f"✅ [SYSTEM] Connected to Redis at {self.redis_host}:{self.redis_port}")
        except redis.ConnectionError:
            print(f"❌ [SYSTEM] Redis Connection Failed! Logs will only appear in console.")
            self.redis_client = None

        self.users = {}
        # Starting balances
        self.balances = {
            "student": 3000, "entrepreneur": 10000, "worker": 7000,
            "bot": 0, "fraud_dirty": 150000, "fraud_clean": 0
        }
        self._setup_accounts(total_normal, num_bots)

    def _generate_id(self):
        u = str(uuid.uuid4())
        return f"{u[:4]}-{u[9:13]}-{u[14:18]}-{u[19:23]}"

    def _setup_accounts(self, total_normal, num_bots):
        # Setup Fraud & Bots
        self.dirty_id = self._generate_id()
        self.clean_id = self._generate_id()
        self.users[self.dirty_id] = {"type": "fraud_dirty", "balance": 150000.0, "state": "active"}
        self.users[self.clean_id] = {"type": "fraud_clean", "balance": 0.0, "state": "active"}

        # Setup Civilians
        types = ["student", "entrepreneur", "worker"]
        remaining = total_normal
        for i, t in enumerate(types):
            count = remaining if i == 2 else random.randint(0, remaining)
            remaining -= count
            for _ in range(count):
                self.users[self._generate_id()] = {"type": t, "balance": float(self.balances[t]), "state": "active"}

        # Setup Bots
        for _ in range(num_bots):
            self.users[self._generate_id()] = {"type": "bot", "balance": 0.0, "state": "active"}

    # --- ENHANCED LOGGING ---
    def log_transaction(self, sender, receiver, amount):
        """
        Logs to Redis AND prints to Console with context-aware formatting.
        """
        msg = f"{sender} sent {amount:.2f}$ to {receiver}"
        
        # 1. Determine Type for Visuals
        sender_type = self.users[sender]['type']
        
        if sender_type in ['fraud_dirty', 'fraud_clean', 'bot']:
            # Highlight Agent moves with RED/Alert icon
            console_msg = f"🚨 [FRAUD] {msg}"
        else:
            # Dimmer/Different icon for Background Noise
            console_msg = f"🛒 [CIVIL] {msg}"

        # 2. Print to Console
        print(console_msg)
        
        # 3. Save to Redis
        if self.redis_client:
            try:
                self.redis_client.lpush("fraud_logs", msg)
            except redis.ConnectionError:
                pass 

    # --- TOOLS ---
    def smurf_split(self):
        """
        Distributes random amounts ($100-$300) to each active bot.
        This prevents creating a suspicious 'fixed pattern' of transactions.
        """
        dirty_data = self.users[self.dirty_id]
        if dirty_data['balance'] <= 0: 
            return "Failed: Dirty account is empty."
        
        active_bots = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active']
        if not active_bots: 
            return "Failed: No active bots available."
        
        total_moved = 0
        transactions_count = 0
        
        # Loop through every active bot and give them a unique random amount
        for bot_id in active_bots:
            # 1. Generate random amount between $100 and $300
            amount = round(random.uniform(100.0, 300.0), 2)
            
            # 2. Stop if we run out of dirty money
            if dirty_data['balance'] < amount:
                break
            
            # 3. Execute Transfer
            self.users[self.dirty_id]['balance'] -= amount
            self.users[bot_id]['balance'] += amount
            
            # 4. Log individual transaction
            self.log_transaction(self.dirty_id, bot_id, amount)
            
            total_moved += amount
            transactions_count += 1
            
        return f"Success: Smurfed ${total_moved:.2f} across {transactions_count} bots."

    # --- DYNAMIC LAYERING TOOL ---
    def mix_chain(self):
        """
        Creates a transaction chain with variable length and variable 'leakage' (fees/dust).
        This mimics irregular payments rather than a robotic 1% commission.
        """
        # 1. Dynamic Chain Length (3 to 6 hops)
        chain_len = random.randint(3, 6)
        
        # Filter: Bots must have at least $50 to be worth layering
        eligible = [u for u, d in self.users.items() 
                    if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] > 50]
        
        if len(eligible) < chain_len: 
            return "Failed: Not enough eligible bots for chain."
        
        # 2. Select random chain path
        chain = random.sample(eligible, chain_len)
        hops = 0
        total_moved = 0
        
        for i in range(len(chain) - 1):
            sender, receiver = chain[i], chain[i+1]
            sender_bal = self.users[sender]['balance']
            
            # 3. Dynamic Transfer Logic
            # Instead of always moving 99%, we randomize what gets sent.
            # "Dust" strategy: Leave behind a random small amount ($1 - $15) 
            # or a random percentage (1% - 4%) to make it look like a fee/expense.
            
            keep_strategy = random.choice(['fixed_dust', 'percent_fee'])
            
            if keep_strategy == 'fixed_dust':
                leave_behind = round(random.uniform(1.50, 12.50), 2)
                transfer_amt = sender_bal - leave_behind
            else:
                retention_rate = random.uniform(0.01, 0.04) # 1% to 4%
                transfer_amt = round(sender_bal * (1 - retention_rate), 2)
            
            # Safety Check: Ensure we don't try to send negative money
            if transfer_amt <= 0:
                continue

            # Execute
            self.users[sender]['balance'] -= transfer_amt
            self.users[receiver]['balance'] += transfer_amt
            self.log_transaction(sender, receiver, transfer_amt)
            
            hops += 1
            total_moved += transfer_amt
            
        return f"Success: Layered approx ${total_moved:.2f} over {hops} hops."

    # --- DYNAMIC EVASION TOOL ---
    def fake_commerce(self):
        """
        Executes a random number of 'purchase' simulations with realistic pricing 
        (e.g., $19.99 instead of $20.00).
        """
        bots = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active']
        if len(bots) < 2: return "Failed: Not enough bots."
        
        # 1. Dynamic Volume: Do 1 to 4 transactions per call
        tx_count = random.randint(1, 4)
        logs = []
        
        for _ in range(tx_count):
            buyer, seller = random.sample(bots, 2)
            
            # 2. Dynamic Pricing Models
            # - Coffee/Food: $5 - $25
            # - Services/Software: $50 - $150
            # - Retail psychology: Prices ending in .99 or .95
            
            price_model = random.choice(['micro', 'small', 'medium'])
            
            if price_model == 'micro':
                base = random.randint(5, 20)
                cents = random.choice([.99, .50, .25, .00])
            elif price_model == 'small':
                base = random.randint(20, 60)
                cents = random.choice([.99, .95, .00])
            else:
                base = random.randint(60, 150)
                cents = random.choice([.00, .99])
                
            amount = base + cents
            
            # Execute only if buyer has funds
            if self.users[buyer]['balance'] >= amount:
                self.users[buyer]['balance'] -= amount
                self.users[seller]['balance'] += amount
                self.log_transaction(buyer, seller, amount)
                logs.append(f"${amount}")
                
        if not logs:
            return "Failed: Bots too poor for commerce."
            
        return f"Success: Simulated {len(logs)} purchases ({', '.join(logs)})."

    def cash_out(self):
        total = 0
        ready = [u for u, d in self.users.items() if d['type']=='bot' and d['state']=='active' and d['balance']>500]
        for bot in ready:
            bal = self.users[bot]['balance']
            self.users[bot]['balance'] = 0
            self.users[self.clean_id]['balance'] += bal
            self.log_transaction(bot, self.clean_id, bal)
            total += bal
        return f"Success: Cleaned ${total}."

    # --- NOISE GENERATOR ---
    def generate_background_noise(self):
        civilians = [uid for uid, d in self.users.items() 
                     if d['type'] in ['student', 'worker', 'entrepreneur']]
        if len(civilians) < 2: return 0

        tx_count = random.randint(10, 25)
        for _ in range(tx_count):
            sender, receiver = random.sample(civilians, 2)
            amt = round(random.uniform(5.0, 300.0), 2)
            if self.users[sender]['balance'] >= amt:
                self.users[sender]['balance'] -= amt
                self.users[receiver]['balance'] += amt
                self.log_transaction(sender, receiver, amt)
        return tx_count

    def check_for_bans(self):
        for uid, data in self.users.items():
            if data['type'] == 'bot' and data['state'] == 'active':
                if data['balance'] > 5000 and random.random() < 0.25:
                    data['state'] = 'banned'
                    print(f"🚫 [GOVERNOR] BAN: {uid} blocked.")

    def execute_instruction(self, decision):
        tool = decision.get("selected_tool")
        if tool == "smurf_split": return self.smurf_split()
        if tool == "mix_chain": return self.mix_chain()
        if tool == "fake_commerce": return self.fake_commerce()
        if tool == "cash_out": return self.cash_out()
        return "Error: Unknown tool"

sim = FraudEnvironment()