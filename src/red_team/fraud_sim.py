import uuid
import random
import os
import redis
import sys
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from collections import deque
from collections import defaultdict

# --- IMPORTS ---
try:
    from src.blue_team.Governor import Governor
    from src.blue_team.send_to_redis import FraudReporter
except ImportError as e:
    Governor = None
    FraudReporter = None

load_dotenv()

class FraudEnvironment:
    def __init__(self, total_normal=50, num_bots=15):
        # Redis Setup
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        try:
            self.redis_client = redis.Redis(host=self.redis_host, port=self.redis_port, db=0, decode_responses=True)
            self.redis_client.ping()
        except redis.ConnectionError:
            self.redis_client = None

        # Components
        self.governor = Governor() if Governor else None
        self.reporter = FraudReporter(self.redis_client) if (FraudReporter and self.redis_client) else None

        # Data Structures
        self.users = {}
        self.balances = {"student": 3000, "entrepreneur": 10000, "worker": 7000, "bot": 0, "fraud_dirty": 150000, "fraud_clean": 0}
        self.frozen_assets = 0.0
        self.frozen_from_bots = 0.0  # NEW: Track only bot frozen assets for win condition
        
        # Stats tracker
        self.stats = defaultdict(float)
        
        # FP tracking and bot counting for win conditions
        self.false_positives = 0
        self.total_bots = num_bots
        
        # LAYERING TRACKER: Ensure all smurfed funds are layered before cash out
        self.total_smurfed = 0.0   # Total amount sent via smurf_split
        self.total_layered = 0.0   # Total amount sent through mix_chain
        
        self._setup_accounts(total_normal, num_bots)
        self.last_stream_id = "0-0"
        self.stream_window = deque(maxlen=20000)

    def _generate_id(self):
        u = str(uuid.uuid4())
        return f"{u[:4]}-{u[9:13]}-{u[14:18]}-{u[19:23]}"

    def _setup_accounts(self, total_normal, num_bots):
        self.dirty_id = self._generate_id()
        self.clean_id = self._generate_id()
        self.users[self.dirty_id] = {"type": "fraud_dirty", "balance": 150000.0, "state": "active", "group_id": -1}
        self.users[self.clean_id] = {"type": "fraud_clean", "balance": 0.0, "state": "active", "group_id": -1}

        types = ["student", "entrepreneur", "worker"]
        remaining = total_normal
        for i, t in enumerate(types):
            count = remaining if i == 2 else random.randint(0, remaining)
            remaining -= count
            for _ in range(count):
                uid = self._generate_id()
                self.users[uid] = {"type": t, "balance": float(self.balances[t]), "state": "active", "group_id": random.randint(0, 4)}

        for _ in range(num_bots):
            self.users[self._generate_id()] = {"type": "bot", "balance": 0.0, "state": "active", "group_id": -2}

    # ========== REALISTIC TRANSACTION AMOUNT GENERATORS ==========
    
    def _generate_peer_amount(self):
        """
        Peer-to-peer transactions (students, friends)
        Examples: coffee, meals, small loans, splitting bills
        
        Distribution: Lognormal (μ=3.2, σ=0.8)
        - Median: ~$24
        - Mean: ~$45
        - 70% of txs: $5-$60
        - 20% of txs: $60-$200
        - 10% of txs: $200-$500
        """
        μ, σ = 3.2, 0.8
        amt = np.random.lognormal(μ, σ)
        amt = np.clip(amt, 5, 500)
        return round(amt, 2)
    
    def _generate_business_amount(self):
        """
        Business transactions (entrepreneurs)
        Examples: supplier payments, contractor fees, inventory purchases
        
        Distribution: Lognormal (μ=5.0, σ=1.0)
        - Median: ~$150
        - Mean: ~$380
        - Range: $50-$5000
        """
        μ, σ = 5.0, 1.0
        amt = np.random.lognormal(μ, σ)
        amt = np.clip(amt, 50, 5000)
        return round(amt, 2)
    
    def _generate_bills_amount(self):
        """
        Bills and recurring payments (workers)
        Examples: rent, utilities, phone, internet, car payment
        
        Distribution: Discrete choice from common bill amounts + small variation
        - Common amounts: $50, $75, $100, $150, $250, $500, $750, $1000, $1200
        - Variation: ±8% to simulate real-world fluctuations
        """
        common_bills = [
            50,    # Utilities (low)
            75,    # Phone bill
            100,   # Internet
            150,   # Utilities (medium)
            250,   # Car payment / insurance
            500,   # Rent split (2-3 people)
            750,   # Rent split or partial rent
            1000,  # Rent (solo) or mortgage
            1200,  # Rent + utilities
        ]
        
        base = np.random.choice(common_bills)
        # Add realistic variation (bills aren't exactly the same each month)
        variation = np.random.uniform(0.92, 1.08)
        amt = base * variation
        
        return round(amt, 2)

    # ========== END REALISTIC GENERATORS ==========

    def log_transaction(self, sender, receiver, amount, category="GENERIC"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sender_type = self.users[sender]["type"]
        is_fraud = sender_type in ["fraud_dirty", "fraud_clean", "bot"]
        tx_type = "FRAUD" if is_fraud else "CIVIL"

        if is_fraud:
            self.stats["fraud_tx_count"] += 1
            self.stats["fraud_volume"] += amount
            if category == "SMURF": self.stats["vol_smurf"] += amount
            if category == "LAYER": self.stats["vol_layer"] += amount
            if category == "COMMERCE": self.stats["vol_commerce"] += amount
            if category == "CASHOUT": self.stats["vol_cashout"] += amount
        else:
            self.stats["civil_tx_count"] += 1
            self.stats["civil_volume"] += amount

        if self.redis_client:
            try:
                data = {"timestamp": timestamp, "sender_id": str(sender), "receiver_id": str(receiver), "amount": float(amount), "type": tx_type}
                self.redis_client.xadd("money_flow", data)
            except: pass

    # ========== ENHANCED FRAUD TOOLS ==========
    
    def smurf_split(self, num_bots=None, amount_per_bot=None):
        """
        Enhanced strategic smurfing with batch and amount control
        
        Args:
            num_bots: Number of bots to smurf to (None = all active bots)
            amount_per_bot: Tuple (min, max) for amount range (None = default $100-$300)
        
        Returns:
            Status message with transfer details
        
        Examples:
            smurf_split(num_bots=3, amount_per_bot=(10000, 15000))
            → Smurfs to 3 random bots with $10k-$15k each
            
            smurf_split()
            → Legacy behavior: all bots, $100-$300 each
        """
        dirty = self.users[self.dirty_id]
        bots = [u for u, d in self.users.items() 
                if d['type'] == 'bot' and d['state'] == 'active']
        
        if not bots or dirty['balance'] <= 0: 
            return "Failed: No bots or funds."
        
        # STRATEGIC CONTROL: Limit number of recipients
        if num_bots and len(bots) > num_bots:
            bots = random.sample(bots, num_bots)
        
        # STRATEGIC CONTROL: Amount range
        if amount_per_bot:
            min_amt, max_amt = amount_per_bot
        else:
            # Default: backward compatible small amounts
            min_amt, max_amt = 100.0, 300.0
        
        total = 0
        recipients_count = 0
        
        for bot in bots:
            amt = round(random.uniform(min_amt, max_amt), 2)
            
            # Don't overdraw dirty account
            if dirty['balance'] < amt: 
                break
            
            self.users[self.dirty_id]['balance'] -= amt
            self.users[bot]['balance'] += amt
            self.log_transaction(self.dirty_id, bot, amt, "SMURF")
            total += amt
            recipients_count += 1
        
        # TRACK total smurfed amount
        self.total_smurfed += total
        
        if recipients_count > 0:
            avg = total / recipients_count
            return f"Smurfed ${total:,.2f} to {recipients_count} bot(s) (avg: ${avg:,.0f}/bot)"
        else:
            return "Failed: Insufficient funds for smurfing."

    def mix_chain(self):
        """
        Gradual layering with realistic small amounts
        
        Strategy: Layer SLOWLY over many rounds (40-60 rounds total)
        - Small amounts: $500-$1,000 per transaction
        - Few transactions: 5-8 per round
        - Looks like normal business activity
        - AI should alternate: mix_chain → fake_commerce → mix_chain
        
        This creates a natural-looking pattern that's harder to detect
        """
        bots = [u for u, d in self.users.items() 
                if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] > 500]
        
        if len(bots) < 3: 
            return "Failed: Low bot funds (need >$500 balances)."
        
        # Select 5-8 random bots for this round's mixing
        num_transfers = random.randint(5, 8)
        selected_bots = random.sample(bots, min(len(bots), num_transfers + 1))
        
        total = 0
        total_txs = 0
        
        # Create a chain through selected bots
        for i in range(len(selected_bots) - 1):
            s, r = selected_bots[i], selected_bots[i + 1]
            
            sender_balance = self.users[s]['balance']
            
            if sender_balance < 500:
                continue
            
            # Random amount between $500-$1000
            # This looks like normal business transactions
            min_amt = 500
            max_amt = min(1000, sender_balance * 0.9)
            
            if max_amt < min_amt:
                continue
            
            amt = round(random.uniform(min_amt, max_amt), 2)
            
            self.users[s]['balance'] -= amt
            self.users[r]['balance'] += amt
            self.log_transaction(s, r, amt, "LAYER")
            total += amt
            total_txs += 1
        
        # TRACK total layered amount
        self.total_layered += total
        
        return f"Layered ${total:,.2f} ({total_txs} txs, gradual)"

    def fake_commerce(self):
        bots = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active']
        if len(bots) < 2: return "Failed"
        total = 0
        for _ in range(random.randint(1, 4)):
            b, s = random.sample(bots, 2)
            amt = round(random.uniform(10, 150), 2)
            if self.users[b]['balance'] >= amt:
                self.users[b]['balance'] -= amt
                self.users[s]['balance'] += amt
                self.log_transaction(b, s, amt, "COMMERCE")
                total += amt
        return f"Commerce ${total:,.2f}"

    def cash_out(self):
        """
        Cash out layered funds to clean account
        
        CRITICAL: Only allows cash out if funds have been properly layered!
        Prevents direct smurf → cash out (instant detection)
        """
        if self.users[self.clean_id]['state'] == 'banned': 
            return "Failed: Clean banned."
        
        # CHECK: Has enough layering happened?
        unlayered = self.total_smurfed - self.total_layered
        
        if unlayered > 5000:  # More than $5k unlayered
            unlayered_pct = (unlayered / self.total_smurfed * 100) if self.total_smurfed > 0 else 0
            return (f"Failed: ${unlayered:,.0f} ({unlayered_pct:.0f}%) still unlayered! "
                   f"Need more mix_chain. (Smurfed: ${self.total_smurfed:,.0f}, "
                   f"Layered: ${self.total_layered:,.0f})")
        
        # Proceed with cash out
        bots = [u for u, d in self.users.items() 
                if d['type']=='bot' and d['state']=='active' and d['balance']>700]
        
        if not bots:
            return "Failed: No bots with sufficient funds (>$700)"
        
        total = 0
        for bot in bots:
            bal = self.users[bot]['balance']
            self.users[bot]['balance'] = 0
            self.users[self.clean_id]['balance'] += bal
            self.log_transaction(bot, self.clean_id, bal, "CASHOUT")
            total += bal
        
        return f"Cleaned ${total:,.2f}"

    def generate_background_noise(self):
        """
        Generate realistic civilian transactions using appropriate distributions
        based on user type (student/worker/entrepreneur)
        """
        civilians = [u for u, d in self.users.items() 
                     if d['type'] in ['student', 'worker', 'entrepreneur']
                     and d['state'] == 'active']
        if not civilians: return
        
        groups = defaultdict(list)
        for u in civilians: 
            groups[self.users[u]['group_id']].append(u)
        
        for _ in range(random.randint(15, 30)):
            s = random.choice(civilians)
            sender_type = self.users[s]['type']
            
            # Pick recipient (80% friends, 20% random)
            if random.random() < 0.8 and len(groups[self.users[s]['group_id']]) > 1:
                r = random.choice([u for u in groups[self.users[s]['group_id']] if u != s])
            else:
                r = random.choice([u for u in civilians if u != s])
            
            # Generate realistic amount based on sender type
            if sender_type == "student":
                amt = self._generate_peer_amount()
            elif sender_type == "entrepreneur":
                amt = self._generate_business_amount()
            elif sender_type == "worker":
                if random.random() < 0.6:
                    amt = self._generate_bills_amount()
                else:
                    amt = self._generate_peer_amount()
            else:
                amt = self._generate_peer_amount()
            
            # Execute transaction if sufficient balance
            if self.users[s]['balance'] >= amt:
                self.users[s]['balance'] -= amt
                self.users[r]['balance'] += amt
                self.log_transaction(s, r, amt, "CIVIL")

    def end_turn_summary(self, turn):
        print(f"   [ACTIVITY REPORT]")
        print(f"   🛒 Civil Noise:   {int(self.stats['civil_tx_count'])} txs (${self.stats['civil_volume']:,.0f})")
        print(f"   🎭 Fraud Total:   {int(self.stats['fraud_tx_count'])} txs (${self.stats['fraud_volume']:,.0f})")
        
        details = []
        if self.stats['vol_smurf']: details.append(f"Smurfed: ${self.stats['vol_smurf']:,.0f}")
        if self.stats['vol_layer']: details.append(f"Layered: ${self.stats['vol_layer']:,.0f}")
        if self.stats['vol_cashout']: details.append(f"Cashed Out: ${self.stats['vol_cashout']:,.0f}")
        
        if details:
            print(f"   👉 Breakdown:     {' | '.join(details)}")
        
        self.stats.clear()

    def ban_user(self, uid):
        if uid in self.users and self.users[uid]['state'] != "banned":
            frozen = self.users[uid]['balance']
            self.frozen_assets += frozen
            self.users[uid]['state'] = "banned"
            self.users[uid]['balance'] = 0.0
            
            # Track False Positives vs Bot Bans
            if self.users[uid]['type'] in ['student', 'worker', 'entrepreneur']:
                self.false_positives += 1
                print(f"⚠️ [FP #{self.false_positives}] BANNED {self.users[uid]['type']} {uid[:4]}.. Frozen: ${frozen:,.2f}")
            elif self.users[uid]['type'] == 'bot':
                # Track bot-specific frozen for win condition
                self.frozen_from_bots += frozen
                print(f"🚫 [GOVERNOR] BANNED {uid[:4]}.. Frozen: ${frozen:,.2f}")
            else:
                print(f"🚫 [GOVERNOR] BANNED {uid[:4]}.. Frozen: ${frozen:,.2f}")
            
            if self.redis_client: self.redis_client.sadd("sim:banned", uid)

    def execute_instruction(self, decision):
        """
        Execute AI decision with support for strategic parameters
        
        Args:
            decision: Dict with 'selected_tool' and optional 'parameters'
        
        Returns:
            Status message from executed tool
        """
        tool = decision.get("selected_tool")
        params = decision.get("parameters", {})
        
        if tool == "smurf_split":
            # Extract strategic parameters
            num_bots = params.get("num_bots", None)
            amount_range = params.get("amount_range", None)
            
            # Convert amount_range list to tuple if provided
            if amount_range and isinstance(amount_range, list) and len(amount_range) == 2:
                amount_range = tuple(amount_range)
            
            return self.smurf_split(num_bots=num_bots, amount_per_bot=amount_range)
        
        if tool == "mix_chain": 
            return self.mix_chain()
        if tool == "fake_commerce": 
            return self.fake_commerce()
        if tool == "cash_out": 
            return self.cash_out()
        
        return "Error: Unknown tool"

    def check_for_bans(self):
        if not self.governor or not self.redis_client: return
        try:
            res = self.redis_client.xread({"money_flow": self.last_stream_id}, count=5000, block=1)
        except: return
        if not res: return
        _, entries = res[0]
        data = []
        for eid, fields in entries:
            data.append(fields)
            self.last_stream_id = eid
        if not data: return
        
        try:
            sus, big, tri = self.governor.transactions_analyzer(data)
            self.reporter.publish_report(sus, big, tri)
            
            to_ban = set()
            for c in sus or []: 
                [to_ban.add(u) for u in c.get("users", [])]
            for g in big or []:
                for case in g.get("cases", []):
                    if "user" in case:
                        to_ban.add(case["user"])
                    else:
                        to_ban.add(case.get("u1"))
                        to_ban.add(case.get("u2"))
            for t in tri or []: 
                [to_ban.add(u) for u in t.get("users", [])]
            
            for u in to_ban:
                if u not in {self.dirty_id, self.clean_id}: 
                    self.ban_user(u)
        
        except Exception as e:
            print(f"⚠️ [GOVERNOR] Detection error: {type(e).__name__}: {str(e)[:80]}")

sim = FraudEnvironment()