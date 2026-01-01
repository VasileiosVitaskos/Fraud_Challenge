import uuid
import random
import os
import redis
import sys
from datetime import datetime
from dotenv import load_dotenv
from collections import deque
from collections import defaultdict


# --- IMPORTS ΒΑΣΙΣΜΕΝΑ ΣΤΟ FILE STRUCTURE ---
try:
    # Εισαγωγή του Governor (Pure Logic)
    from src.blue_team.Governor import Governor
    # Εισαγωγή του Reporter (Redis Communication)
    from src.blue_team.send_to_redis import FraudReporter
except ImportError as e:
    print(f"⚠️ Import Error: {e}")
    print("Running in simulation-only mode (No detection).")
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
            print(f"[SYSTEM] Connected to Redis at {self.redis_host}:{self.redis_port}")
        except redis.ConnectionError:
            print(f"[SYSTEM] Redis Connection Failed! Logs will only appear in console.")
            self.redis_client = None

        # --- 2. BLUE TEAM INITIALIZATION ---
        # Αρχικοποιούμε τον Governor και τον Reporter
        self.governor = Governor() if Governor else None
        self.reporter = FraudReporter(self.redis_client) if (FraudReporter and self.redis_client) else None

        self.users = {}
        self.balances = {
            "student": 3000, "entrepreneur": 10000, "worker": 7000,
            "bot": 0, "fraud_dirty": 150000, "fraud_clean": 0
        }
        self._setup_accounts(total_normal, num_bots)
        self.last_stream_id = "0-0"
        self.stream_window = deque(maxlen=20000)
                # --- LOGGING CONTROL ---
        self.log_level = os.getenv("LOG_LEVEL", "FRAUD_ONLY").upper()
        # counters ανά tick/turn (θα τα μηδενίζουμε κάθε turn)
        self.turn_stats = defaultdict(float)  # counts & totals


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

    def log_transaction(self, sender, receiver, amount):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sender_type = self.users[sender]["type"]

        is_fraud = sender_type in ["fraud_dirty", "fraud_clean", "bot"]
        tx_type = "FRAUD" if is_fraud else "CIVIL"


        # --- 1) Collect per-turn stats (για summary) ---
        if tx_type == "CIVIL":
            self.turn_stats["civil_tx_count"] += 1
            self.turn_stats["civil_total_amount"] += float(amount)
        else:
            self.turn_stats["fraud_tx_count"] += 1
            self.turn_stats["fraud_total_amount"] += float(amount)

        # --- 2) Console output based on LOG_LEVEL ---
        msg = f"[{timestamp}] {sender} sent ${amount:.2f} to {receiver}"

        if self.log_level == "FULL":
            print(("🚨 [FRAUD] " if is_fraud else "🛒 [CIVIL] ") + msg)

        elif self.log_level == "SUMMARY":
            # τύπωσε fraud live, civil όχι
            if is_fraud:
                print("🚨 [FRAUD] " + msg)

        else:  # FRAUD_ONLY (default)
            if is_fraud:
                print("🚨 [FRAUD] " + msg)

        # --- 3) Redis Stream Push (μένει όπως ήταν) ---
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


    # --- TOOLS ---
    def smurf_split(self):
        dirty_data = self.users[self.dirty_id]
        if dirty_data['balance'] <= 0: 
            return "Failed: Dirty account is empty."
        
        active_bots = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active']
        if not active_bots: 
            return "Failed: No active bots available."
        
        total_moved = 0
        transactions_count = 0
        
        for bot_id in active_bots:
            amount = round(random.uniform(100.0, 300.0), 2)
            if dirty_data['balance'] < amount: break
            
            self.users[self.dirty_id]['balance'] -= amount
            self.users[bot_id]['balance'] += amount
            self.log_transaction(self.dirty_id, bot_id, amount)
            total_moved += amount
            transactions_count += 1
            
        return f"Success: Smurfed ${total_moved:.2f} across {transactions_count} bots."

    def mix_chain(self):
        chain_len = random.randint(3, 6)
        eligible = [u for u, d in self.users.items() 
                    if d['type'] == 'bot' and d['state'] == 'active' and d['balance'] > 50]
        
        if len(eligible) < chain_len: 
            return "Failed: Not enough eligible bots for chain."
        
        chain = random.sample(eligible, chain_len)
        hops = 0
        total_moved = 0
        
        for i in range(len(chain) - 1):
            sender, receiver = chain[i], chain[i+1]
            sender_bal = self.users[sender]['balance']
            
            keep_strategy = random.choice(['fixed_dust', 'percent_fee'])
            if keep_strategy == 'fixed_dust':
                leave_behind = round(random.uniform(1.50, 12.50), 2)
                transfer_amt = sender_bal - leave_behind
            else:
                retention_rate = random.uniform(0.01, 0.04) 
                transfer_amt = round(sender_bal * (1 - retention_rate), 2)
            
            transfer_amt = min(transfer_amt, 800.0)

            if transfer_amt <= 0: continue

            self.users[sender]['balance'] -= transfer_amt
            self.users[receiver]['balance'] += transfer_amt
            self.log_transaction(sender, receiver, transfer_amt)
            hops += 1
            total_moved += transfer_amt
            
        return f"Success: Layered approx ${total_moved:.2f} over {hops} hops."

    def fake_commerce(self):
        bots = [u for u, d in self.users.items() if d['type'] == 'bot' and d['state'] == 'active']
        if len(bots) < 2: return "Failed: Not enough bots."
        
        tx_count = random.randint(1, 4)
        logs = []
        
        for _ in range(tx_count):
            buyer, seller = random.sample(bots, 2)
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
            if self.users[buyer]['balance'] >= amount:
                self.users[buyer]['balance'] -= amount
                self.users[seller]['balance'] += amount
                self.log_transaction(buyer, seller, amount)
                logs.append(f"${amount}")
                
        if not logs: return "Failed: Bots too poor for commerce."
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

    def generate_background_noise(self):
        civilians = [uid for uid, d in self.users.items() if d['type'] in ['student', 'worker', 'entrepreneur']]
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
    def end_turn_summary(self, turn_idx=None):
        """
        Τυπώνει summary στο τέλος κάθε turn και μηδενίζει counters.
        """
        if self.log_level in ("SUMMARY", "FRAUD_ONLY"):
            c_n = int(self.turn_stats.get("civil_tx_count", 0))
            c_sum = self.turn_stats.get("civil_total_amount", 0.0)
            f_n = int(self.turn_stats.get("fraud_tx_count", 0))
            f_sum = self.turn_stats.get("fraud_total_amount", 0.0)

            prefix = f"[TURN {turn_idx}] " if turn_idx is not None else ""
            # 1 γραμμή = smooth terminal
            print(f"{prefix}CIVIL noise: {c_n} tx, total ${c_sum:,.2f} | FRAUD: {f_n} tx, total ${f_sum:,.2f}")

        self.turn_stats.clear()


    def ban_user(self, uid):
        if uid in self.users:
            if self.users[uid]['state'] != "banned":
                self.users[uid]['state'] = "banned"
                self.users[uid]['balance'] = 0.0 
                print(f"🚫 [BAN HAMMER] User {uid} detected and BANNED. Assets frozen.")
                # Ενημερώνουμε και το Redis ότι έγινε ban (προαιρετικό, αλλά χρήσιμο)
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
        """
        Incremental defense check:
        - Διαβάζει ΜΟΝΟ νέα Redis stream entries
        - Κρατά sliding window
        - Καλεί Governor μόνο σε bounded δεδομένα
        """

        # --- SAFETY CHECK ---
        if not self.governor or not self.reporter or not self.redis_client:
            return

        # --- 1. Incremental read από Redis Stream ---
        try:
            response = self.redis_client.xread(
                {"money_flow": self.last_stream_id},
                count=5000,   # max νέα events ανά tick
                block=1       # ~non-blocking
            )
        except Exception:
            return

        # Αν δεν υπάρχουν νέα δεδομένα → δεν κάνουμε τίποτα
        if not response:
            return

        # response format: [(stream_name, [(id, fields), ...])]
        _, entries = response[0]

        for entry_id, fields in entries:
            self.stream_window.append(fields)
            self.last_stream_id = entry_id

        # Αν δεν έχουμε αρκετά δεδομένα, δεν τρέχουμε detection
        if len(self.stream_window) < 50:
            return

        analysis_data = list(self.stream_window)

        # --- 2. Ανάλυση από Governor ---
        try:
            suspicious, big_fish, triangles = self.governor.transactions_analyzer(analysis_data)
        except Exception as e:
            print(f"[DEFENSE ERROR] Governor failed: {e}")
            return

        # --- 3. Αναφορά ---
        try:
            self.reporter.publish_report(suspicious, big_fish, triangles)
        except Exception:
            pass  # reporting failure ≠ simulation failure

        # --- 4. Συλλογή IDs για Ban ---
        users_to_ban = set()

        # A. Layering
        for case in suspicious or []:
            for uid in case.get("users", []):
                users_to_ban.add(uid)

        # B. Smurfing / Big Fish (ανεκτικό parsing)
        for fish_group in big_fish or []:
            # 1) Αν υπάρχουν cases με u1/u2
            for incident in fish_group.get("cases", []):
                if isinstance(incident, dict):
                    if "u1" in incident:
                        users_to_ban.add(incident["u1"])
                    if "u2" in incident:
                        users_to_ban.add(incident["u2"])

            # 2) Αν υπάρχουν users σαν list
            for u in fish_group.get("users", []):
                if isinstance(u, (list, tuple)) and len(u) >= 2:
                    users_to_ban.add(u[0])
                    users_to_ban.add(u[1])
                elif isinstance(u, str):
                    users_to_ban.add(u)

        # C. Structuring / Triangles
        for tri in triangles or []:
            for uid in tri.get("users", []):
                users_to_ban.add(uid)

        # --- 5. Εκτέλεση Bans ---
        for uid in users_to_ban:
            # Δεν μπανάρουμε τα “ταμεία”
            if uid not in {self.dirty_id, self.clean_id}:
                self.ban_user(uid)


sim = FraudEnvironment()