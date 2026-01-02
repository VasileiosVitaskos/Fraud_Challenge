import uuid
import random
import os
import redis
import sys
from datetime import datetime
from dotenv import load_dotenv
from collections import deque
from collections import defaultdict

# --- IMPORTS ---
try:
    from src.blue_team.Governor import Governor
    from src.blue_team.send_to_redis import FraudReporter
except ImportError as e:
    print(f"⚠️ Import Error: {e}")
    Governor = None
    FraudReporter = None

load_dotenv()

class FraudEnvironment:
    def __init__(self, total_normal=50, num_bots=15):
        # 1. Setup Redis
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=0,
                decode_responses=True
            )
            self.redis_client.ping()
        except redis.ConnectionError:
            self.redis_client = None

        # --- BLUE TEAM INIT ---
        self.governor = Governor() if Governor else None
        self.reporter = FraudReporter(self.redis_client) if (FraudReporter and self.redis_client) else None

        self.users = {}
        self.balances = {
            "student": 3000, "entrepreneur": 10000, "worker": 7000,
            "bot": 0, "fraud_dirty": 150000, "fraud_clean": 0
        }
        
        # --- NEW: STATS TRACKING ---
        self.frozen_assets = 0.0  # Λεφτά που κατάσχεσε ο Governor
        
        self._setup_accounts(total_normal, num_bots)
        self.last_stream_id = "0-0"
        self.stream_window = deque(maxlen=20000)
        self.log_level = os.getenv("LOG_LEVEL", "FRAUD_ONLY").upper()
        self.turn_stats = defaultdict(float)

    def _generate_id(self):
        u = str(uuid.uuid4())
        return f"{u[:4]}-{u[9:13]}-{u[14:18]}-{u[19:23]}"

    def _setup_accounts(self, total_normal, num_bots):
        self.dirty_id = self._generate_id()
        self.clean_id = self._generate_id()
        self.users[self.dirty_id] = {"type": "fraud_dirty", "balance": 150000.0, "state": "active", "group_id": -1}
        self.users[self.clean_id] = {"type": "fraud_clean", "balance": 0.0, "state": "active", "group_id": -1}

        # Setup Civilians (Clusters)
        types = ["student", "entrepreneur", "worker"]
        remaining = total_normal
        num_groups = 5 
        
        for i, t in enumerate(types):
            count = remaining if i == 2 else random.randint(0, remaining)
            remaining -= count
            for _ in range(count):
                uid = self._generate_id()
                group = random.randint(0, num_groups - 1)
                self.users[uid] = {
                    "type": t, 
                    "balance": float(self.balances[t]), 
                    "state": "active",
                    "group_id": group
                }

        # Setup Bots
        for _ in range(num_bots):
            self.users[self._generate_id()] = {
                "type": "bot", 
                "balance": 0.0, 
                "state": "active",
                "group_id": -2
            }

    def log_transaction(self, sender, receiver, amount):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sender_type = self.users[sender]["type"]
        is_fraud = sender_type in ["fraud_dirty", "fraud_clean", "bot"]
        tx_type = "FRAUD" if is_fraud else "CIVIL"

        if tx_type == "CIVIL":
            self.turn_stats["civil_tx_count"] += 1
            self.turn_stats["civil_total_amount"] += float(amount)
        else:
            self.turn_stats["fraud_tx_count"] += 1
            self.turn_stats["fraud_total_amount"] += float(amount)

        msg = f"[{timestamp}] {sender} sent ${amount:.2f} to {receiver}"
        if self.log_level == "FULL":
            print(("🚨 " if is_fraud else "🛒 ") + msg)
        elif self.log_level == "SUMMARY" or self.log_level == "FRAUD_ONLY":
            if is_fraud: print("🚨 " + msg)

        if self.redis_client:
            try:
                data = {
                    "timestamp": timestamp,
                    "sender_id": str(sender),
                    "receiver_id": str(receiver),
                    "amount": float(amount),
                    "type": tx_type,
                }
                self.redis_client.xadd("money_flow", data)
            except redis.ConnectionError:
                pass

    # --- TOOLS (Ίδια λογική με πριν) ---
    def smurf_split(self):
        dirty_data = self.users[self.dirty_id]
        if dirty_data['balance'] <= 0: return "Failed: Dirty account empty."
        active_bots = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active']
        if not active_bots: return "Failed: No bots."
        
        total = 0
        count = 0
        for bot_id in active_bots:
            amount = round(random.uniform(100.0, 300.0), 2)
            if dirty_data['balance'] < amount: break
            self.users[self.dirty_id]['balance'] -= amount
            self.users[bot_id]['balance'] += amount
            self.log_transaction(self.dirty_id, bot_id, amount)
            total += amount
            count += 1
        return f"Smurfed ${total:.2f} to {count} bots."

    def mix_chain(self):
        chain_len = random.randint(3, 6)
        eligible = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] > 50]
        if len(eligible) < chain_len: return "Failed: Not enough rich bots."
        
        chain = random.sample(eligible, chain_len)
        total = 0
        for i in range(len(chain) - 1):
            sender, receiver = chain[i], chain[i+1]
            amt = min(self.users[sender]['balance'] * 0.9, 800.0)
            if amt <= 0: continue
            self.users[sender]['balance'] -= amt
            self.users[receiver]['balance'] += amt
            self.log_transaction(sender, receiver, amt)
            total += amt
        return f"Layered ${total:.2f} via {chain_len} hops."

    def fake_commerce(self):
        bots = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active']
        if len(bots) < 2: return "Failed: Not enough bots."
        
        count = random.randint(1, 4)
        total = 0
        for _ in range(count):
            b, s = random.sample(bots, 2)
            amt = round(random.uniform(10, 150), 2)
            if self.users[b]['balance'] >= amt:
                self.users[b]['balance'] -= amt
                self.users[s]['balance'] += amt
                self.log_transaction(b, s, amt)
                total += amt
        return f"Commerce noise generated (${total:.2f})."

    def cash_out(self):
        if self.users[self.clean_id]['state'] == 'banned': return "Failed: Clean acct banned."
        bots = [u for u, d in self.users.items() if d['type']=='bot' and d['state']=='active' and d['balance']>500]
        total = 0
        for bot in bots:
            bal = self.users[bot]['balance']
            self.users[bot]['balance'] = 0
            self.users[self.clean_id]['balance'] += bal
            self.log_transaction(bot, self.clean_id, bal)
            total += bal
        return f"Cleaned ${total:.2f}."

    def generate_background_noise(self):
        civilians = [u for u, d in self.users.items() if d['type'] in ['student', 'worker', 'entrepreneur']]
        if len(civilians) < 2: return
        
        groups = defaultdict(list)
        for u in civilians: groups[self.users[u]['group_id']].append(u)

        for _ in range(random.randint(10, 25)):
            sender = random.choice(civilians)
            if random.random() < 0.8 and len(groups[self.users[sender]['group_id']]) > 1:
                receiver = random.choice([u for u in groups[self.users[sender]['group_id']] if u != sender])
            else:
                receiver = random.choice([u for u in civilians if u != sender])
            
            amt = round(random.uniform(5, 150), 2)
            if self.users[sender]['balance'] >= amt:
                self.users[sender]['balance'] -= amt
                self.users[receiver]['balance'] += amt
                self.log_transaction(sender, receiver, amt)

    def end_turn_summary(self, turn_idx=None):
        if self.log_level in ("SUMMARY", "FRAUD_ONLY"):
            c_n = int(self.turn_stats.get("civil_tx_count", 0))
            f_n = int(self.turn_stats.get("fraud_tx_count", 0))
            f_sum = self.turn_stats.get("fraud_total_amount", 0.0)
            prefix = f"[TURN {turn_idx}] " if turn_idx else ""
            print(f"{prefix}Noise: {c_n} tx | Fraud Activity: {f_n} tx (${f_sum:,.2f})")
        self.turn_stats.clear()

    def ban_user(self, uid):
        if uid in self.users and self.users[uid]['state'] != "banned":
            # --- NEW: TRACKING FROZEN ASSETS ---
            frozen_amount = self.users[uid]['balance']
            self.frozen_assets += frozen_amount
            # -----------------------------------
            
            self.users[uid]['state'] = "banned"
            self.users[uid]['balance'] = 0.0 
            print(f"🚫 [GOVERNOR] BANNED {uid}. Frozen: ${frozen_amount:,.2f}")
            
            if self.redis_client:
                self.redis_client.sadd("sim:banned", uid)

    def execute_instruction(self, decision):
        tool = decision.get("selected_tool")
        if tool == "smurf_split": return self.smurf_split()
        if tool == "mix_chain": return self.mix_chain()
        if tool == "fake_commerce": return self.fake_commerce()
        if tool == "cash_out": return self.cash_out()
        return "Error: Unknown tool"

    def check_for_bans(self):
        if not self.governor or not self.reporter or not self.redis_client: return
        try:
            response = self.redis_client.xread({"money_flow": self.last_stream_id}, count=5000, block=1)
        except Exception: return
        if not response: return

        _, entries = response[0]
        new_data = []
        for eid, fields in entries:
            new_data.append(fields)
            self.last_stream_id = eid
        
        if not new_data: return

        try:
            suspicious, big_fish, triangles = self.governor.transactions_analyzer(new_data)
        except Exception as e:
            print(f"Governor Error: {e}")
            return

        try:
            self.reporter.publish_report(suspicious, big_fish, triangles)
        except Exception: pass

        to_ban = set()
        for case in suspicious or []: 
            for u in case.get("users", []): to_ban.add(u)
        for grp in big_fish or []:
            for c in grp.get("cases", []): 
                if isinstance(c, dict): to_ban.update([c.get("u1"), c.get("u2")])
        for tri in triangles or []: 
            for u in tri.get("users", []): to_ban.add(u)

        for uid in to_ban:
            if uid not in {self.dirty_id, self.clean_id} and uid:
                self.ban_user(uid)

sim = FraudEnvironment()