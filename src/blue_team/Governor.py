import numpy as np
import redis
from ripser import ripser
from datetime import datetime
import os
from collections import deque
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

class Governor:
    def __init__(self):
      
        self.memory = deque() 
        self.window_size = 3600 

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
            
            if amount > 2000:
                adjacency_matrix[i][j] = 1

     
        result = ripser(dist_matrix, distance_matrix=True, maxdim=1, do_cocycles=True)
        h1_features = result['dgms'][1]
        cocycles = result['cocycles'][1]

        suspicious_cases = []
        big_fish_net = []
        triangle_cases = []

        pairs_of_fish = [(i,j,dist) for i, row in enumerate (dist_matrix) for j, dist in enumerate(row[i+1:], start=i+1) if dist < 0.01]
        big_fish_suspects = [(unique_users[i], unique_users[j], dist) for i,j,dist in pairs_of_fish]
        
        bf_transaction_counts = []
        for item in big_fish_suspects:
            u1, u2 = item[0], item[1]
            key = tuple(sorted((u1, u2)))
            freq = counts[key]
            bf_transaction_counts.append((u1, u2, item[2], freq))
        
        bf_transaction_counts = [t for t in bf_transaction_counts if t[3] > 6]
        
        if bf_transaction_counts:
            big_fish_net.append({
                "type": "Smurfing",
                "cases": [{"u1": u1, "u2": u2, "freq": freq, "score": dist} for (u1, u2, dist, freq) in bf_transaction_counts]
            })

      
        for i, (birth, death) in enumerate(h1_features):
            persistence = death - birth
            if persistence < 0.005:
                cycle_indices = cocycles[i]
                involved_users = list(set([unique_users[indx] for sublist in cycle_indices for indx in sublist[:2] if indx < N]))
                
                total_cycle_volume = sum([user_volumes[u] for u in involved_users])
                
                if total_cycle_volume < 15000:
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
