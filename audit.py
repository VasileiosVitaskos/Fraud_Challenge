import redis
import os
import json
from dotenv import load_dotenv

load_dotenv()

def audit_bans():
    # Σύνδεση στο Redis (Localhost)
    host = "localhost"
    port = int(os.getenv("REDIS_PORT", 6379))
    
    try:
        r = redis.Redis(host=host, port=port, db=0, decode_responses=True)
        r.ping()
    except redis.ConnectionError:
        print("❌ Could not connect to Redis. Ensure Docker is running.")
        return

    print("\n--- 🕵️‍♂️ FRAUD SIMULATION AUDIT (POST-MORTEM) ---")

    # 1. Λήψη Banned Users
    banned_users = r.smembers("sim:banned")
    if not banned_users:
        print("✅ No bans found yet.")
        return

    print(f"📦 Total Banned Users: {len(banned_users)}")

    # 2. Ανάλυση Ρόλων (Fraud vs Civil) από το Money Flow
    user_roles = {}
    try:
        stream_data = r.xrange("money_flow", min="-", max="+")
        for _, entry in stream_data:
            sender = entry.get('sender_id')
            user_type = entry.get('type')
            if sender and user_type:
                user_roles[sender] = user_type
    except Exception:
        print("⚠️ No transaction history found.")

    # 3. Ανάλυση Αιτίας (Reason) από τα Alerts
    # Διαβάζουμε όλη τη λίστα governor:alerts
    user_reasons = {}
    try:
        # lrange 0 -1 φέρνει όλα τα στοιχεία της λίστας
        alerts = r.lrange("governor:alerts", 0, -1)
        for alert_json in alerts:
            alert = json.loads(alert_json)
            alert_type = alert.get("type") # Layering, Smurfing, Triangle
            
            # Βρίσκουμε ποιους χρήστες αφορούσε αυτό το alert
            involved_ids = []
            
            # Τα alerts έχουν διαφορετική δομή details
            details = alert.get("details", [])
            
            if alert_type == "Smurfing":
                # Smurfing details format: {'cases': [{'u1': X, 'u2': Y}, ...]}
                for case_group in details:
                    for case in case_group.get('cases', []):
                        involved_ids.append(case.get('u1'))
                        involved_ids.append(case.get('u2'))
            
            elif alert_type in ["Layering", "Structuring", "Triangle"]:
                 # Layering/Triangle details format: [{'users': [X, Y, Z]}, ...]
                 for case in details:
                     for uid in case.get('users', []):
                         involved_ids.append(uid)
            
            # Καταγράφουμε τον λόγο για κάθε χρήστη
            for uid in involved_ids:
                if uid not in user_reasons:
                    user_reasons[uid] = set()
                user_reasons[uid].add(alert_type)
                
    except Exception as e:
        print(f"⚠️ Error reading alerts: {e}")

    # 4. Εκτύπωση Αναφοράς
    true_positives = 0
    false_positives = 0
    
    print("\n📝 DETAILED REPORT:")
    print(f"{'USER ID':<20} | {'ROLE':<8} | {'REASON (Why?)':<25} | {'STATUS'}")
    print("-" * 75)

    for uid in banned_users:
        role = user_roles.get(uid, "UNKNOWN")
        reasons = list(user_reasons.get(uid, ["Unknown"]))
        reason_str = ", ".join(reasons)
        
        status = ""
        if role == "FRAUD":
            true_positives += 1
            status = "✅ CAUGHT"
        elif role == "CIVIL":
            false_positives += 1
            status = "❌ MISTAKE"
        else:
            status = "❓ UNKNOWN"

        print(f"{uid:<20} | {role:<8} | {reason_str:<25} | {status}")

    # 5. Scorecard
    print("\n--- 📊 SCORECARD ---")
    print(f"🦁 CAUGHT FRAUDSTERS: {true_positives}")
    print(f"🤕 INNOCENT VICTIMS:  {false_positives}")
    
    total = true_positives + false_positives
    if total > 0:
        precision = (true_positives / total) * 100
        print(f"🎯 PRECISION: {precision:.1f}%")
        
        if precision > 90:
            print("🏆 EXCELLENT! The Governor is smart now.")
        elif precision < 50:
            print("⚠️ STILL AGGRESSIVE. Tune amounts higher.")

if __name__ == "__main__":
    audit_bans()