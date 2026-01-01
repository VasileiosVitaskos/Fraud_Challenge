import redis
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class FraudReporter:
    def __init__(self, redis_client=None):
        
        self.alert_channel = "governor:alerts"
        
        if redis_client:
            self.redis = redis_client
        else:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", 6379))
            try:
                self.redis = redis.Redis(host=host, port=port, db=0, decode_responses=True)
                self.redis.ping()
            except redis.ConnectionError:
                print("[REPORTER] Redis connection failed.")
                self.redis = None

    def publish_report(self, suspicious, big_fish, triangles):
       
        if not self.redis:
            return

        # 1. Layering Alerts
        if suspicious:
            self._send_single_type("Layering", suspicious)
            
        # 2. Smurfing Alerts
        if big_fish:
            self._send_single_type("Smurfing", big_fish)
            
        # 3. Structuring Alerts
        if triangles:
            self._send_single_type("Structuring", triangles)

    def _send_single_type(self, alert_type, data):
        payload = {
            "timestamp": datetime.now().isoformat(),
            "type": alert_type,
            "count": len(data),
            "details": data
        }
        try:
            self.redis.lpush(self.alert_channel, json.dumps(payload))
            print(f"📡 [REPORTER] Sent {len(data)} {alert_type} alerts to Redis.")
        except Exception as e:
            print(f"[REPORTER] Failed to push to Redis: {e}")