import numpy as np
import redis
from ripser import ripser
from datetime import datetime
import os
from collections import deque
from dotenv import load_dotenv
from collections import Counter

load_dotenv()
# Κλάση Governor για την ανάλυση συναλλαγών και την ανίχνευση ύποπτων δραστηριοτήτων
class Governor:
    def __init__(self):
        self.second_chance = deque()
    
    def transactions_analyzer(self, data: list[dict]):
        recent_data = []
        timestamps = []
        window_size = 3600
        # Μετατροπή timestamps σε epoch time για ευκολότερους υπολογισμούς για  φιλτραρισμα πρόσφατων συναλλαγών
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

        users_set = set() #συλλογή μοναδικών χρηστών 
        for d in recent_data:
            users_set.add(d['sender_id'])   #συλλογή μοναδικών χρηστών
            users_set.add(d['receiver_id']) #συλλογή μοναδικών χρηστών
        
        unique_users = list(users_set)  #δημιουργία λίστας μοναδικών χρηστών
        N = len(unique_users)           #αριθμός μοναδικών χρηστών
        user_to_idx = {u: i for i, u in enumerate(unique_users)} # λεξικό για γρήγορη αντιστοίχιση χρήστη σε index
        
        # Apostaseis se pinaka me diagonio 0
        dist_matrix = np.full((N, N), np.inf)  #αρχικα απειρη απόσταση
        np.fill_diagonal(dist_matrix, 0)   #η αποσταση απο τον εαυτό του είναι 0
        epsilon = 1e-10  # μικρή σταθερά για αποφυγή διαίρεσης με το μηδέν
        # Γεμίζουμε τον πίνακα αποστάσεων κανοντας iterate τα δεδομένα των πρόσφατων συναλλαγών ψάχνουμε  id αποστολέα και παραλήπτη και το ποσό
        # Φτιάχνουμε λίστα με ταξινομημένα ζευγάρια (tuple) από τα raw data
        all_transaction_pairs = [
            tuple(sorted((d['sender_id'], d['receiver_id'])))
            for d in recent_data
        ]
        adjacency_matrix = np.zeros((N, N), dtype=int)  # Αρχικοποίηση adjacency matrix για τον έλεγχο τριγώνων
        np.fill_diagonal(adjacency_matrix, 0)  # διαγώνιος 0
        # Μετράμε τις εμφανίσεις κάθε ζεύγους συναλλαγών
        counts = Counter(all_transaction_pairs)

        for d in recent_data:
            i = user_to_idx[d['sender_id']]  #index αποστολέα
            j = user_to_idx[d['receiver_id']]  #index παραλήπτη
            amount = float(d['amount'])       #ποσό συναλλαγής
            
            distance = 1.0 / (amount + epsilon) # αποφυγή διαίρεσης με το μηδέν
            dist_matrix[i][j] = min(dist_matrix[i][j], distance)  # μη κατευθυνώμενος γράφος
            dist_matrix[j][i] = min(dist_matrix[j][i], distance)  # αυτή την λογική θα ακολουθήσουμε και για i j και j i 
            if amount > 400:
                adjacency_matrix[i][j] = 1 # ΓΙΑ ΝΑ ΦΤΙΑΞΟΥΜΕ ΤΟ ADJACENCY MATRIX ΓΙΑ ΤΑ ΤΡΙΓΩΝΑ

        result = ripser(dist_matrix, distance_matrix=True, maxdim=1, do_cocycles=True)  # Υπολογισμός των persistence diagrams και cocycles με ripser η οποία κανει τις εξής μαθηματικές πραξεις χρησιμοποιώντας την τοπολογία  και συγκεκριμένα το filtration των Vietoris-Rips
        # H1 features αντιστοιχούν σε κύκλους, H0 σε συνδεδεμένα συστατικά 
        # cocycles περιέχουν πληροφορίες για τους κύκλους που ανιχνεύθηκαν όπως ποιοι κόμβοι συμμετέχουν σε κάθε κύκλο
        
        
        h1_features = result['dgms'][1]  # Λίστα με τα persistence pairs για H1 (κύκλοι)
        cocycles = result['cocycles'][1]  # Λίστα με cocycles για H1

        suspicious_cases = []
        big_fish_net = []
        
        # Ανίχνευση big fish smurfing εδω το όριο είναι 5000 ευρώ => απόσταση 0.0002 γιατι παμε να βρούμε ποσά πάνω από 5000 λογω 1/5000 = 0.0002 
        pairs_οf_fish = [(i,j,dist) for i, row in enumerate (dist_matrix) for j, dist in enumerate(row[i+1:], start=i+1) if dist < 0.0002] #κάνουμε enumerate για να πάρουμε και τα indices των χρηστών αλλα μονο το πάνω τριγωνο του πίνακα και αποφεύγουμε και το dist !=0 που είναι η διαγώνιος
        big_fish_suspects = [(unique_users[i], unique_users[j], dist) for i,j,dist in pairs_οf_fish] #μετατροπή των indices σε ονόματα χρηστών κανοντας iterate στην λίστα unique_users
        # Υπολογισμός συχνοτήτων για τους ύποπτους
        transaction_counts = []
        for item in big_fish_suspects:
            u1 = item[0]
            u2 = item[1]

            # Φτιάχνουμε το κλειδί όπως ακριβώς και στο all_transaction_pairs
            key = tuple(sorted((u1, u2)))
    
            # Βρίσκουμε τη συχνότητα
            freq = counts[key]
    
            # Αποθηκεύουμε το αποτέλεσμα (μπορούμε να βάλουμε και το frequency δίπλα στο item)
            transaction_counts.append((u1, u2, item[2], freq))
        # θελουμε το freq > 3 για να θεωρηθεί smurfing
        transaction_counts = [t for t in transaction_counts if t[3] > 3]
        if transaction_counts:
            big_fish_net.append({"type": "Smurfing","cases": [{"u1": u1, "u2": u2, "freq": freq, "score": dist}for (u1, u2, dist, freq) in transaction_counts]})  #αποθήκευση των αποτελεσμάτων σε λεξικό


        for i, (birth, death) in enumerate(h1_features):
            persistence = death - birth
            # Ελέγχουμε για layering κύκλους 500 θεωρουμε το ελάχιστο ποσο που μπορεί να υπάρχει
            if persistence < 0.002:
                cycle_indices = cocycles[i]
                # Μετατροπή indices se onomata με τεχνικη sublist που είναι μεθοδος για να παρουμε μικρότερα υποσύνολα της αρχικής λίστας
                involved_users = list(set([unique_users[indx] for sublist in cycle_indices for indx in sublist[:2] if indx < N]))
                
                suspicious_cases.append({
                    "type": "Layering",
                    "persistence": persistence,
                    "users": involved_users
                })

        # Αρχικοποίηση λιστών και set
        triangle_cases = []
        seen_triangles = set()  # Εδώ θα αποθηκεύουμε τα "υπογραφές" των τριγώνων

        # Δημιουργία adjacency matrix για τον έλεγχο τριγώνων
        adjacency_square = np.dot(adjacency_matrix, adjacency_matrix)
        adjacency_cube = np.dot(adjacency_square, adjacency_matrix)

        # Έλεγχος αν υπάρχουν τρίγωνα
        if adjacency_cube.diagonal().sum() > 0:
            triangle_indices = np.where(adjacency_cube.diagonal() > 0)[0]
    
            for idx in triangle_indices:  # idx = User A
                for j in range(N):  # j = User B
                    # Έλεγχος 1: A->B και ο B επιστρέφει στον A σε 2 βήματα
                    if adjacency_matrix[idx][j] == 1 and adjacency_square[j][idx] > 0:
                        for k in range(N):  # k = User C
                        # Έλεγχος 2: B->C και C->A
                            if adjacency_matrix[j][k] == 1 and adjacency_matrix[k][idx] == 1:
                            # Βρήκαμε τους χρήστες
                                triangle_users = [unique_users[idx], unique_users[j], unique_users[k]]
                        
                        # Δημιουργία μοναδικής "υπογραφής" για το set
                        current_triangle = tuple(sorted(triangle_users))
                        
                        if current_triangle not in seen_triangles:
                            seen_triangles.add(current_triangle)
                            triangle_cases.append({
                                "type": "Triangle",
                                "users": triangle_users
                            })

        # Επιστροφή των αποτελεσμάτων ως λεξικα για 0(1) πρόσβαση        
        return suspicious_cases, big_fish_net, triangle_cases


