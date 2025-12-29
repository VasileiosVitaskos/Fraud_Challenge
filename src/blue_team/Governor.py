import numpy as np
import redis 
from ripser import ripser
from datetime import datetime 
import os
from collections import deque
from dotenv import load_dotenv

load_dotenv()

class Governor:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        try:
            self.redis_client = redis.Redis(host=self.redis_host, port=self.redis_port,db=0,decode_responses=True)
            # Test the connection immediately
            self.redis_client.ping()
            print(f"[SYSTEM] Connected to Redis at {self.redis_host}:{self.redis_port}")
        except redis.ConnectionError:
            print(f"[SYSTEM] Redis Connection Failed! Logs will only appear in console.")
            self.redis_client = None
        self.second_chance = deque()

    def transactions_analyzer(self,data: list[dict]):
        recent_data = []    
        timestamps = []
        window_size = 3600
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
            if  window_size > recent_transaction - current_transaction: 
                recent_data.append(d)

        users_set = set()
        for d in recent_data:
            users_set.add(d['sender_id'])
            users_set.add(d['receiver_id'])

        unique_users = list(users_set)
        N = len(unique_users)
        user_to_idx = {u: i for i, u in enumerate(unique_users)}

        #Apostaseis se pinaka me diagonio 0 
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

        result = ripser(dist_matrix, distance_matrix=True, maxdim=1, do_cocycles=True)
        h1_features = result['dgms'][1]
        cocycles = result['cocycles'][1]
        suspicious_cases = []

        for i, (birth, death) in enumerate(h1_features):

            persistence = death - birth
            if persistence > 1.0:
                cycle_indices = cocycles[i]
                # Μετατροπή indices se onomata
                involved_users = list(set([unique_users[indx] for sublist in cycle_indices for indx in sublist[:2] if indx < N]))
                suspicious_cases.append({
                        "type": "Layering",
                        "persistence": persistence,
                        "users": involved_users
                    })
        return suspicious_cases