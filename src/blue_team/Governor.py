import numpy as np
import redis
from ripser import ripser
from datetime import datetime
import os
from collections import deque
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

try:
    from src.common.config import Config
except ImportError:
    import config as Config

class Governor:
    def __init__(self):
        self.memory = deque() 
        self.window_size = (Config.TOTAL_TICKS * Config.TICK_DURATION)

    def transactions_analyzer(self, new_data: list[dict]):
        for d in new_data:
            try:
                dt_obj = datetime.strptime(d['timestamp'], "%Y-%m-%d %H:%M:%S")
                epoch = dt_obj.timestamp()
                entry = d.copy()
                entry['epoch'] = epoch
                self.memory.append(entry)
            except ValueError:
                continue

        if not self.memory:
            return [], [], []

        current_sim_time = self.memory[-1]['epoch']
        while self.memory and (current_sim_time - self.memory[0]['epoch'] > self.window_size):
            self.memory.popleft()

        recent_data = list(self.memory)

        if len(recent_data) < 5:
            return [], [], []

        user_volumes = Counter()
        users_set = set()
        
        for d in recent_data:
            amt = float(d['amount'])
            user_volumes[d['sender_id']] += amt
            user_volumes[d['receiver_id']] += amt
            users_set.add(d['sender_id'])
            users_set.add(d['receiver_id'])

        unique_users = list(users_set)
        N = len(unique_users)
        user_to_idx = {u: i for i, u in enumerate(unique_users)}

        dist_matrix = np.full((N, N), np.inf)
        np.fill_diagonal(dist_matrix, 0)
        epsilon = 1e-10

        all_transaction_pairs = [
            tuple(sorted((d['sender_id'], d['receiver_id'])))
            for d in recent_data
        ]
        adjacency_matrix = np.zeros((N, N), dtype=int)
        np.fill_diagonal(adjacency_matrix, 0)
        
        counts = Counter(all_transaction_pairs)

        for d in recent_data:
            i = user_to_idx[d['sender_id']]
            j = user_to_idx[d['receiver_id']]
            amount = float(d['amount'])
            
            distance = 1.0 / (amount + epsilon)
            dist_matrix[i][j] = min(dist_matrix[i][j], distance)
            dist_matrix[j][i] = min(dist_matrix[j][i], distance)
            
            pair_key = tuple(sorted((d['sender_id'], d['receiver_id'])))
            frequency = counts[pair_key]
            if amount > 2000:
                adjacency_matrix[i][j] = 1
            elif amount > 300 and frequency >= 3:
                adjacency_matrix[i][j] = 1
            elif amount > 100 and frequency >= 6:
                adjacency_matrix[i][j] = 1

        result = ripser(dist_matrix, distance_matrix=True, maxdim=1, do_cocycles=True)
        h1_features = result['dgms'][1]
        cocycles = result['cocycles'][1]

        suspicious_cases = []
        big_fish_net = []
        triangle_cases = []

        user_outgoing = Counter()
        user_outgoing_volume = Counter()

        for d in recent_data:
            if float(d['amount']) > 100:
                user_outgoing[d['sender_id']] += 1
                user_outgoing_volume[d['sender_id']] += float(d['amount'])

        smurfing_suspects = []
        for user, tx_count in user_outgoing.items():
            if tx_count > 12:
                total_sent = user_outgoing_volume[user]
                recipients = set([d['receiver_id'] for d in recent_data 
                        if d['sender_id'] == user and float(d['amount']) > 100])
                
                if len(recipients) > 7:
                    avg_per_recipient = total_sent / len(recipients) if len(recipients) > 0 else 0
                    if avg_per_recipient > 3000:
                        for recipient in recipients:
                            smurfing_suspects.append({
                            "user": recipient,
                            "hub": user,
                            "tx_count": tx_count,
                            "recipient_count": len(recipients),
                            "total_volume": total_sent
                        })

        if smurfing_suspects:
            big_fish_net.append({
                "type": "Smurfing",
                "cases": smurfing_suspects
            })
      
        for i, (birth, death) in enumerate(h1_features):
            persistence = death - birth
            if persistence < 0.005:
                cycle_indices = cocycles[i]
                involved_users = list(set([unique_users[indx] for sublist in cycle_indices for indx in sublist[:2] if indx < N]))
                total_cycle_volume = sum([user_volumes[u] for u in involved_users])
                min_volume = len(involved_users) * 3500  # Increased from 3000 to reduce FPs

                if total_cycle_volume < min_volume:
                    continue
                     
                cycle_txs = [d for d in recent_data 
                     if d['sender_id'] in involved_users 
                     and d['receiver_id'] in involved_users]
        
                if cycle_txs:
                    # Require minimum transaction count (fraud cycles have many txs)
                    if len(cycle_txs) < 5:
                        continue
                    
                    amounts = [float(d['amount']) for d in cycle_txs]
                    avg_amount = sum(amounts) / len(amounts)
                    std_dev = (sum((x - avg_amount)**2 for x in amounts) / len(amounts)) ** 0.5
                    cv = std_dev / avg_amount if avg_amount > 0 else 0
            
                    if cv > 0.3:  # Tightened from 0.5 (fraud patterns are consistent)
                        continue

                suspicious_cases.append({
                    "type": "Layering",
                    "persistence": persistence,
                    "users": involved_users,
                    "volume": total_cycle_volume
                })

        adjacency_square = np.dot(adjacency_matrix, adjacency_matrix)
        adjacency_cube = np.dot(adjacency_square, adjacency_matrix)
        seen_triangles = set()

        if adjacency_cube.diagonal().sum() > 0:
            triangle_indices = np.where(adjacency_cube.diagonal() > 0)[0]
            for idx in triangle_indices:
                for j in range(N):
                    if adjacency_matrix[idx][j] == 1 and adjacency_square[j][idx] > 0:
                        for k in range(N):
                            if adjacency_matrix[j][k] == 1 and adjacency_matrix[k][idx] == 1:
                                triangle_users = [unique_users[idx], unique_users[j], unique_users[k]]
                                current_triangle = tuple(sorted(triangle_users))
                                if current_triangle not in seen_triangles:
                                    seen_triangles.add(current_triangle)
                                    triangle_cases.append({"type": "Triangle", "users": triangle_users})

        return suspicious_cases, big_fish_net, triangle_cases