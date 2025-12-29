import numpy as np
import redis 
from ripser import ripser
from datetime import datetime 
import os
import time
from collections import deque
from dotenv import load_dotenv

load_dotenv()

class Governor:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        try:
            self.redis_client = redis.Redis(host=self.redis_host, port=self.redis_port, db=0, decode_responses=True)
            self.redis_client.ping()
            print(f"[GOVERNOR] Connected to Redis at {self.redis_host}:{self.redis_port}")
        except redis.ConnectionError:
            print(f"[GOVERNOR] Redis Connection Failed! Cannot monitor transactions.")
            self.redis_client = None
            raise
        
        self.second_chance = deque()
        self.transaction_buffer = []
        self.last_stream_id = '0-0'  # Start from beginning
        self.banned_users = set()
        
    def read_transactions_from_stream(self):
        """Read new transactions from Redis Stream"""
        if not self.redis_client:
            return []
        
        try:
            # Read from the money_flow stream
            messages = self.redis_client.xread(
                {'money_flow': self.last_stream_id}, 
                count=100,
                block=1000  # Wait 1 second for new messages
            )
            
            new_transactions = []
            if messages:
                for stream_name, stream_messages in messages:
                    for msg_id, msg_data in stream_messages:
                        self.last_stream_id = msg_id
                        new_transactions.append(msg_data)
            
            return new_transactions
            
        except Exception as e:
            print(f"[GOVERNOR] Error reading from stream: {e}")
            return []
    
    def transactions_analyzer(self, data: list[dict]):
        """Analyze transactions for suspicious patterns using TDA"""
        if len(data) < 3:
            return []
            
        recent_data = []    
        timestamps = []
        window_size = 3600  # 1 hour window
        
        for d in data:
            timestamp_str = d['timestamp'] 
            dt_obj = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            epoch = dt_obj.timestamp()
            timestamps.append(epoch) 

        recent_transaction = max(timestamps)
        for d in data:
            timestamp_str = d['timestamp']
            current_transaction = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            current_transaction = current_transaction.timestamp()
            if window_size > recent_transaction - current_transaction: 
                recent_data.append(d)

        if len(recent_data) < 3:
            return []

        users_set = set()
        for d in recent_data:
            users_set.add(d['sender_id'])
            users_set.add(d['receiver_id'])

        unique_users = list(users_set)
        N = len(unique_users)
        
        if N < 3:
            return []
            
        user_to_idx = {u: i for i, u in enumerate(unique_users)}

        # Create distance matrix
        dist_matrix = np.full((N, N), np.inf)
        np.fill_diagonal(dist_matrix, 0)
        epsilon = 1e-10

        for d in recent_data:
            i = user_to_idx[d['sender_id']]
            j = user_to_idx[d['receiver_id']]
            amount = float(d['amount'])
        
            distance = 1.0 / (amount + epsilon)
            dist_matrix[i][j] = min(dist_matrix[i][j], distance)
            dist_matrix[j][i] = min(dist_matrix[j][i], distance)

        # Run topological data analysis
        result = ripser(dist_matrix, distance_matrix=True, maxdim=1, do_cocycles=True)
        h1_features = result['dgms'][1]
        cocycles = result['cocycles'][1]
        suspicious_cases = []

        for i, (birth, death) in enumerate(h1_features):
            persistence = death - birth
            
            if persistence > 0.05:  # Lowered threshold for better detection
                cycle_indices = cocycles[i]
                involved_users = list(set([unique_users[indx] for sublist in cycle_indices for indx in sublist[:2] if indx < N]))
                suspicious_cases.append({
                    "type": "Layering",
                    "persistence": persistence,
                    "users": involved_users
                })
                
        return suspicious_cases
    
    def ban_user(self, user_id):
        """Ban a user by publishing to Redis"""
        if user_id in self.banned_users:
            return  # Already banned
            
        self.banned_users.add(user_id)
        
        if self.redis_client:
            try:
                # Publish ban command to Redis
                ban_data = {
                    'user_id': user_id,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'reason': 'Detected in suspicious transaction pattern'
                }
                self.redis_client.xadd('ban_commands', ban_data)
                print(f"[GOVERNOR] 🚨 BANNED USER: {user_id}")
            except Exception as e:
                print(f"[GOVERNOR] Error banning user: {e}")
    
    def monitor_loop(self, analysis_interval=10, min_transactions=10):
        """Main monitoring loop"""
        print(f"[GOVERNOR] Starting fraud detection monitoring...")
        print(f"[GOVERNOR] Analysis interval: every {analysis_interval} transactions")
        print(f"[GOVERNOR] Minimum transactions for analysis: {min_transactions}")
        
        analysis_counter = 0
        
        while True:
            try:
                # Read new transactions
                new_transactions = self.read_transactions_from_stream()
                
                if new_transactions:
                    self.transaction_buffer.extend(new_transactions)
                    analysis_counter += len(new_transactions)
                    print(f"[GOVERNOR] Received {len(new_transactions)} new transactions (Total buffered: {len(self.transaction_buffer)})")
                
                # Perform analysis periodically
                if analysis_counter >= analysis_interval and len(self.transaction_buffer) >= min_transactions:
                    print(f"\n[GOVERNOR] 🔍 Running analysis on {len(self.transaction_buffer)} transactions...")
                    
                    suspicious = self.transactions_analyzer(self.transaction_buffer)
                    
                    if suspicious:
                        print(f"[GOVERNOR] ⚠️ Found {len(suspicious)} suspicious patterns!")
                        for case in suspicious:
                            print(f"  - Type: {case['type']}, Persistence: {case['persistence']:.4f}")
                            print(f"    Involved users: {case['users']}")
                            
                            # Ban all users involved in suspicious pattern
                            for user in case['users']:
                                self.ban_user(user)
                    else:
                        print(f"[GOVERNOR] ✅ No suspicious patterns detected")
                    
                    # Keep last 200 transactions for sliding window analysis
                    if len(self.transaction_buffer) > 200:
                        self.transaction_buffer = self.transaction_buffer[-200:]
                    
                    analysis_counter = 0
                    print()
                
                # Small delay to avoid spinning
                time.sleep(0.5)
                
            except KeyboardInterrupt:
                print("\n[GOVERNOR] Shutting down monitoring...")
                break
            except Exception as e:
                print(f"[GOVERNOR] Error in monitoring loop: {e}")
                time.sleep(1)

if __name__ == "__main__":
    governor = Governor()
    governor.monitor_loop(analysis_interval=15, min_transactions=10)