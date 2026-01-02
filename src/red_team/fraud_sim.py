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
        
        # --- NEW: DETAILED STATS TRACKER ---
        self.stats = defaultdict(float) # volume_smurf, volume_layer, count_fraud, count_civil
        
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

    def log_transaction(self, sender, receiver, amount, category="GENERIC"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sender_type = self.users[sender]["type"]
        is_fraud = sender_type in ["fraud_dirty", "fraud_clean", "bot"]
        tx_type = "FRAUD" if is_fraud else "CIVIL"

        # --- STATS ACCUMULATION (NO PRINTING) ---
        if is_fraud:
            self.stats["fraud_tx_count"] += 1
            self.stats["fraud_volume"] += amount
            # Κατηγορίες για το Summary
            if category == "SMURF": self.stats["vol_smurf"] += amount
            if category == "LAYER": self.stats["vol_layer"] += amount
            if category == "COMMERCE": self.stats["vol_commerce"] += amount
            if category == "CASHOUT": self.stats["vol_cashout"] += amount
        else:
            self.stats["civil_tx_count"] += 1
            self.stats["civil_volume"] += amount

        # Redis Logging (Silent)
        if self.redis_client:
            try:
                data = {"timestamp": timestamp, "sender_id": str(sender), "receiver_id": str(receiver), "amount": float(amount), "type": tx_type}
                self.redis_client.xadd("money_flow", data)
            except: pass

    # --- TOOLS WITH CATEGORIES ---
    def smurf_split(self):
        dirty = self.users[self.dirty_id]
        bots = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active']
        if not bots or dirty['balance'] <= 0: return "Failed: No bots or funds."
        
        total = 0
        for bot in bots:
            amt = round(random.uniform(100.0, 300.0), 2)
            if dirty['balance'] < amt: break
            self.users[self.dirty_id]['balance'] -= amt
            self.users[bot]['balance'] += amt
            self.log_transaction(self.dirty_id, bot, amt, "SMURF")
            total += amt
        return f"Smurfed ${total:,.2f}"

    def mix_chain(self):
        bots = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] > 50]
        if len(bots) < 3: return "Failed: Low bot funds."
        chain = random.sample(bots, min(len(bots), 6))
        total = 0
        for i in range(len(chain)-1):
            s, r = chain[i], chain[i+1]
            amt = min(self.users[s]['balance'] * 0.9, 800.0)
            if amt <= 0: continue
            self.users[s]['balance'] -= amt
            self.users[r]['balance'] += amt
            self.log_transaction(s, r, amt, "LAYER")
            total += amt
        return f"Layered ${total:,.2f}"

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
        if self.users[self.clean_id]['state'] == 'banned': return "Failed: Clean banned."
        bots = [u for u, d in self.users.items() if d['type']=='bot' and d['state']=='active' and d['balance']>700]
        total = 0
        for bot in bots:
            bal = self.users[bot]['balance']
            self.users[bot]['balance'] = 0
            self.users[self.clean_id]['balance'] += bal
            self.log_transaction(bot, self.clean_id, bal, "CASHOUT")
            total += bal
        return f"Cleaned ${total:,.2f}"

    def generate_background_noise(self):
        civilians = [u for u, d in self.users.items() if d['type'] in ['student', 'worker', 'entrepreneur']]
        groups = defaultdict(list)
        for u in civilians: groups[self.users[u]['group_id']].append(u)
        
        for _ in range(random.randint(15, 30)):
            s = random.choice(civilians)
            # Logic: 80% Friends, 20% Random
            if random.random() < 0.8 and len(groups[self.users[s]['group_id']]) > 1:
                r = random.choice([u for u in groups[self.users[s]['group_id']] if u != s])
            else:
                r = random.choice([u for u in civilians if u != s])
            
            amt = round(random.uniform(5, 150), 2)
            if self.users[s]['balance'] >= amt:
                self.users[s]['balance'] -= amt
                self.users[r]['balance'] += amt
                self.log_transaction(s, r, amt, "CIVIL")

    # --- THE CLEAN SUMMARY ---
    def end_turn_summary(self, turn):
        # Εδώ τυπώνουμε ΜΟΝΟ τα συγκεντρωτικά
        print(f"   [ACTIVITY REPORT]")
        print(f"   🛒 Civil Noise:   {int(self.stats['civil_tx_count'])} txs (${self.stats['civil_volume']:,.0f})")
        print(f"   🎭 Fraud Total:   {int(self.stats['fraud_tx_count'])} txs (${self.stats['fraud_volume']:,.0f})")
        
        # Details only if non-zero
        details = []
        if self.stats['vol_smurf']: details.append(f"Smurfed: ${self.stats['vol_smurf']:,.0f}")
        if self.stats['vol_layer']: details.append(f"Layered: ${self.stats['vol_layer']:,.0f}")
        if self.stats['vol_cashout']: details.append(f"Cashed Out: ${self.stats['vol_cashout']:,.0f}")
        
        if details:
            print(f"   👉 Breakdown:     {' | '.join(details)}")
        
        # Reset stats for next turn
        self.stats.clear()

    def ban_user(self, uid):
        if uid in self.users and self.users[uid]['state'] != "banned":
            frozen = self.users[uid]['balance']
            self.frozen_assets += frozen
            self.users[uid]['state'] = "banned"
            self.users[uid]['balance'] = 0.0 
            # Μόνο τα Bans τυπώνονται γιατί είναι σημαντικά events
            print(f"🚫 [GOVERNOR] BANNED {uid[:4]}.. Frozen: ${frozen:,.2f}")
            if self.redis_client: self.redis_client.sadd("sim:banned", uid)

    def execute_instruction(self, decision):
        tool = decision.get("selected_tool")
        if tool == "smurf_split": return self.smurf_split()
        if tool == "mix_chain": return self.mix_chain()
        if tool == "fake_commerce": return self.fake_commerce()
        if tool == "cash_out": return self.cash_out()
        return "Error"

    def check_for_bans(self):
        # (Ίδιος κώδικας με πριν - incremental read)
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
            for c in sus or []: [to_ban.add(u) for u in c.get("users", [])]
            for g in big or []: [to_ban.add(x) for c in g.get("cases", []) for x in [c.get("u1"),c.get("u2")]]
            for t in tri or []: [to_ban.add(u) for u in t.get("users", [])]
            
            for u in to_ban:
                if u not in {self.dirty_id, self.clean_id}: self.ban_user(u)
        except: pass

sim = FraudEnvironment()